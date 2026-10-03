from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.deps import get_current_user
from .adaptive import AdaptiveDiagnostic
from .profiling import assign_profile, load_profile_model
from app.shared.events import DiagnosticCompleted
from app.shared.learner_model import EVENT_BUS, apply_evidence

try:
    from supabase import Client, create_client
except ImportError:  # pragma: no cover
    Client = Any
    create_client = None


router = APIRouter(prefix="/diagnostic", tags=["diagnostic"])
PROFILE = load_profile_model()

TOPICS = [
    {"id": f"topic-{index}", "name": name, "category": category}
    for index, (name, category) in enumerate(
        [(f"DSA {i}", "DSA") for i in range(1, 6)]
        + [(f"Aptitude {i}", "aptitude") for i in range(1, 6)]
        + [(f"CS Core {i}", "CS core") for i in range(1, 6)]
        + [(f"System Design {i}", "system design") for i in range(1, 6)]
        + [(f"Behavioral {i}", "behavioral") for i in range(1, 6)]
    )
]
QUESTIONS = [
    {
        "id": f"diagnostic-{index}",
        "topic_id": topic["id"],
        "difficulty": (index % 5) + 1,
        "body": f"Diagnostic question {index} for {topic['name']}",
        "options": ["A", "B", "C", "D"],
        "answer": "A",
    }
    for index, topic in enumerate(TOPICS * 6)
]


class AnswerCreate(BaseModel):
    question_id: str
    answer: str
    time_taken_s: float = Field(ge=0)


class SessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, Any]] = {}
        self.supabase: Client | None = None
        if settings.supabase_url and settings.supabase_service_role_key and create_client:
            self.supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    def _questions(self) -> list[dict[str, Any]]:
        if self.supabase:
            return self.supabase.table("questions").select("id,topic_id,difficulty,body,options,answer").execute().data
        return QUESTIONS

    def start(self, user_id: str, config: dict[str, Any]) -> dict[str, Any]:
        if self._find_in_progress(user_id):
            raise HTTPException(status_code=409, detail="A diagnostic session is already in progress")
        session = {
            "id": str(uuid4()), "user_id": user_id, "status": "in_progress",
            "started_at": datetime.now(timezone.utc).isoformat(), "completed_at": None,
            "config": config, "result": None, "answers": [],
        }
        if self.supabase:
            self.supabase.table("diagnostic_sessions").insert({key: value for key, value in session.items() if key != "answers"}).execute()
        self.sessions[session["id"]] = session
        return session

    def _find_in_progress(self, user_id: str) -> dict[str, Any] | None:
        local = next((session for session in self.sessions.values() if session["user_id"] == user_id and session["status"] == "in_progress"), None)
        if local:
            return local
        if self.supabase:
            rows = self.supabase.table("diagnostic_sessions").select("*").eq("user_id", user_id).eq("status", "in_progress").limit(1).execute().data
            if rows:
                rows[0]["answers"] = []
                self.sessions[rows[0]["id"]] = rows[0]
                return rows[0]
        return None

    def get(self, session_id: str, user_id: str) -> dict[str, Any]:
        session = self.sessions.get(session_id)
        if session and session["user_id"] == user_id:
            return session
        if self.supabase:
            rows = self.supabase.table("diagnostic_sessions").select("*").eq("id", session_id).eq("user_id", user_id).limit(1).execute().data
            if rows:
                rows[0]["answers"] = []
                self.sessions[session_id] = rows[0]
                return rows[0]
        raise HTTPException(status_code=404, detail="Diagnostic session not found")

    def save(self, session: dict[str, Any]) -> None:
        self.sessions[session["id"]] = session
        if self.supabase:
            self.supabase.table("diagnostic_sessions").update({key: session[key] for key in ("status", "completed_at", "result")}).eq("id", session["id"]).eq("user_id", session["user_id"]).execute()


STORE = SessionStore()
PROFILE = load_profile_model()


def _engine(session: dict[str, Any]) -> AdaptiveDiagnostic:
    questions = STORE._questions()
    return AdaptiveDiagnostic.from_answers(
        questions,
        sorted({question["topic_id"] for question in questions}),
        session.get("answers", []),
        max_questions=int((session.get("config") or {}).get("max_questions", 25)),
        min_topic_coverage=int((session.get("config") or {}).get("min_topic_coverage", 1)),
    )


def _user_id(current_user: dict[str, Any]) -> str:
    return str(current_user.get("id", current_user.get("sub")))


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"module": "diagnostic", "status": "ready"}


@router.post("/sessions", status_code=201)
def start_session(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return STORE.start(_user_id(current_user), {"max_questions": 25, "min_topic_coverage": 1})


@router.get("/sessions/{session_id}/next")
def next_question(session_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    session = STORE.get(session_id, _user_id(current_user))
    question = _engine(session).next_question()
    if question is None:
        return {"done": True, "question": None, "progress": len(session.get("answers", []))}
    return {"done": False, "progress": len(session.get("answers", [])), "max_questions": 25, "question": {key: value for key, value in question.items() if key != "answer"}}


@router.post("/sessions/{session_id}/answer")
def answer_question(session_id: str, payload: AnswerCreate, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    session = STORE.get(session_id, _user_id(current_user))
    if session["status"] != "in_progress":
        raise HTTPException(status_code=409, detail="Diagnostic session is not in progress")
    question = next((item for item in STORE._questions() if item["id"] == payload.question_id), None)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    engine = _engine(session)
    if payload.question_id in engine.answered_ids:
        raise HTTPException(status_code=409, detail="Question already answered")
    correct = engine.answer(question, payload.answer)
    session["answers"].append({"question_id": payload.question_id, "correct": correct, "time_taken_s": payload.time_taken_s})
    STORE.save(session)
    return {"correct": correct, "progress": len(session["answers"]), "should_stop": _engine(session).should_stop()}


@router.post("/sessions/{session_id}/complete")
def complete_session(session_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    session = STORE.get(session_id, _user_id(current_user))
    if session["status"] != "in_progress":
        raise HTTPException(status_code=409, detail="Diagnostic session is not in progress")
    engine = _engine(session)
    mastery = engine.mastery()
    for topic_id, value in mastery.items():
        apply_evidence(session["user_id"], topic_id, value, "diagnostic", 1.0)
    assignment = assign_profile([mastery[topic_id] for topic_id in sorted(mastery)], PROFILE)
    result = {"mastery": mastery, "confidence": engine.confidence(), **assignment}
    session.update({"status": "completed", "completed_at": datetime.now(timezone.utc).isoformat(), "result": result})
    STORE.save(session)
    if STORE.supabase:
        STORE.supabase.table("cluster_assignments").insert({"user_id": session["user_id"], "session_id": session_id, **assignment}).execute()
    EVENT_BUS.emit(DiagnosticCompleted(user_id=session["user_id"], payload=result))
    return result


@router.get("/sessions/{session_id}/report")
def session_report(session_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    session = STORE.get(session_id, _user_id(current_user))
    if not session.get("result"):
        raise HTTPException(status_code=409, detail="Diagnostic session is not complete")
    mastery = session["result"]["mastery"]
    return {**session["result"], "weak_topics": sorted(mastery, key=mastery.get)}


@router.get("/latest")
def latest_session(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any] | None:
    sessions = [session for session in STORE.sessions.values() if session["user_id"] == _user_id(current_user) and session["status"] == "completed"]
    return max(sessions, key=lambda session: session["completed_at"]) if sessions else None
