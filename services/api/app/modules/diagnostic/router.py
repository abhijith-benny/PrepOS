from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.deps import get_current_user
from app.shared.events import DiagnosticCompleted
from app.shared.learner_model import EVENT_BUS, apply_evidence
from app.shared.repositories.retry import retry_supabase

from .adaptive import AdaptiveDiagnostic
from .profiling import assign_profile, load_profile_model

try:
    from supabase import Client, create_client
except ImportError:  # pragma: no cover
    Client = Any
    create_client = None


router = APIRouter(prefix="/diagnostic", tags=["diagnostic"])
PROFILE = load_profile_model()
SECTION_DEFINITIONS = [
    {"id": "aptitude", "label": "Aptitude", "description": "Quantitative and logical reasoning", "category": "aptitude"},
    {"id": "computer_aptitude", "label": "Computer Aptitude", "description": "Computer science fundamentals", "category": "CS core"},
    {"id": "english", "label": "English", "description": "Grammar, vocabulary, and reading comprehension", "category": "English"},
    {"id": "coding", "label": "Coding", "description": "Read code, predict output, and reason about complexity", "category": "DSA"},
]
SECTION_BY_ID = {section["id"]: section for section in SECTION_DEFINITIONS}
SECTION_BY_CATEGORY = {section["category"]: section for section in SECTION_DEFINITIONS}
DEFAULT_SECTION_COUNT = 10

TOPICS = [
    {"id": f"topic-{index}", "name": name, "category": category}
    for index, (name, category) in enumerate(
        [(f"Aptitude {i}", "aptitude") for i in range(1, 6)]
        + [(f"CS Core {i}", "CS core") for i in range(1, 6)]
        + [(f"English {i}", "English") for i in range(1, 6)]
        + [(f"Coding {i}", "DSA") for i in range(1, 6)]
    )
]
QUESTIONS = []
for index, topic in enumerate(TOPICS * 6):
    if topic["category"] == "DSA":
        body = "What does this code print? values = [2, 4, 6]; print(values[1])"
    elif topic["category"] == "English":
        body = "Choose the grammatically correct sentence."
    elif topic["category"] == "CS core":
        body = "Which statement about this computer science concept is correct?"
    else:
        body = "Which option is the best answer to this reasoning problem?"
    QUESTIONS.append({"id": f"diagnostic-{index}", "topic_id": topic["id"], "category": topic["category"], "difficulty": index % 5 + 1, "body": body, "options": ["A", "B", "C", "D"], "answer": "A"})


class AnswerCreate(BaseModel):
    question_id: str
    answer: str
    time_taken_s: float = Field(ge=0)


def _new_sections(counts: dict[str, int] | None = None) -> dict[str, dict[str, Any]]:
    counts = counts or {}
    sections = {}
    for index, definition in enumerate(SECTION_DEFINITIONS):
        sections[definition["id"]] = {
            "label": definition["label"],
            "category": definition["category"],
            "status": "in_progress" if index == 0 else "locked",
            "question_count": 0,
            "question_limit": int(counts.get(definition["id"], DEFAULT_SECTION_COUNT)),
            "correct_count": 0,
            "answers": [],
        }
    return sections


class SessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, Any]] = {}
        self.supabase: Client | None = None
        self.legacy_completion = False
        if settings.supabase_url and settings.supabase_service_role_key and create_client:
            self.supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    def _questions(self) -> list[dict[str, Any]]:
        if not self.supabase:
            return QUESTIONS
        rows = retry_supabase(lambda: self.supabase.table("questions").select("id,topic_id,difficulty,body,options,answer,topics(category)").execute()).data
        for row in rows:
            topic = row.pop("topics", None) or {}
            row["category"] = topic.get("category", "")
        return rows

    def start(self, user_id: str, config: dict[str, Any]) -> dict[str, Any]:
        existing = self._find_in_progress(user_id)
        if existing:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "A diagnostic session is already in progress",
                    "session_id": existing["id"],
                },
            )
        session = {
            "id": str(uuid4()), "user_id": user_id, "status": "in_progress",
            "started_at": datetime.now(timezone.utc).isoformat(), "completed_at": None,
            "config": config, "sections": _new_sections(config.get("section_counts")), "result": None, "answers": [],
        }
        self._save_local(session)
        if self.supabase:
            retry_supabase(lambda: self.supabase.table("diagnostic_sessions").insert({key: value for key, value in session.items() if key != "answers"}).execute())
        return _public_session(session)

    def _save_local(self, session: dict[str, Any]) -> None:
        for section in session["sections"].values():
            section["answers"] = [answer for answer in session["answers"] if answer.get("section") == section.get("id")]
        self.sessions[session["id"]] = session

    def _hydrate(self, session: dict[str, Any]) -> dict[str, Any]:
        session["sections"] = session.get("sections") or _new_sections()
        session["answers"] = session.get("answers") or [answer for section in session["sections"].values() for answer in section.get("answers", [])]
        return session

    def _find_in_progress(self, user_id: str) -> dict[str, Any] | None:
        local = next((session for session in self.sessions.values() if session["user_id"] == user_id and session["status"] == "in_progress"), None)
        if local:
            return local
        if self.supabase:
            rows = retry_supabase(lambda: self.supabase.table("diagnostic_sessions").select("*").eq("user_id", user_id).eq("status", "in_progress").limit(1).execute()).data
            if rows:
                return self.sessions.setdefault(rows[0]["id"], self._hydrate(rows[0]))
        return None

    def get(self, session_id: str, user_id: str) -> dict[str, Any]:
        session = self.sessions.get(session_id)
        if session and session["user_id"] == user_id:
            return session
        if self.supabase:
            rows = retry_supabase(lambda: self.supabase.table("diagnostic_sessions").select("*").eq("id", session_id).eq("user_id", user_id).limit(1).execute()).data
            if rows:
                return self.sessions.setdefault(session_id, self._hydrate(rows[0]))
        raise HTTPException(status_code=404, detail="Diagnostic session not found")

    def save(self, session: dict[str, Any]) -> None:
        self._save_local(session)
        if self.supabase:
            retry_supabase(lambda: self.supabase.table("diagnostic_sessions").update({key: session[key] for key in ("status", "completed_at", "sections", "result")}).eq("id", session["id"]).eq("user_id", session["user_id"]).execute())


STORE = SessionStore()


def _public_session(session: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in session.items() if key != "answers"}


def _user_id(current_user: dict[str, Any]) -> str:
    return str(current_user.get("id", current_user.get("sub")))


def _section_for_question(question: dict[str, Any]) -> dict[str, Any]:
    return SECTION_BY_CATEGORY.get(question.get("category", ""), SECTION_DEFINITIONS[0])


def _current_section(session: dict[str, Any]) -> dict[str, Any] | None:
    for definition in SECTION_DEFINITIONS:
        if session["sections"][definition["id"]]["status"] != "completed":
            return definition
    return None


def _section_engine(session: dict[str, Any], definition: dict[str, Any]) -> AdaptiveDiagnostic:
    questions = [question for question in STORE._questions() if _section_for_question(question)["id"] == definition["id"]]
    section_state = session["sections"][definition["id"]]
    answers = [answer for answer in session["answers"] if answer.get("section") == definition["id"]]
    return AdaptiveDiagnostic.from_answers(
        questions,
        sorted({question["topic_id"] for question in questions}),
        answers,
        max_questions=int(section_state["question_limit"]),
        min_topic_coverage=999,
        confidence_threshold=0.0,
    )


def _question_response(question: dict[str, Any], definition: dict[str, Any], progress: int, limit: int) -> dict[str, Any]:
    return {
        "done": False,
        "progress": progress,
        "section": {"id": definition["id"], "label": definition["label"], "description": definition["description"], "index": SECTION_DEFINITIONS.index(definition) + 1, "total": len(SECTION_DEFINITIONS), "question_count": progress, "question_limit": limit},
        "question": {key: value for key, value in question.items() if key not in {"answer", "category"}},
    }


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"module": "diagnostic", "status": "ready"}


@router.post("/sessions", status_code=201)
def start_session(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return STORE.start(_user_id(current_user), {"section_counts": {section["id"]: DEFAULT_SECTION_COUNT for section in SECTION_DEFINITIONS}})


@router.get("/sessions/{session_id}/next")
def next_question(session_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    session = STORE.get(session_id, _user_id(current_user))
    definition = _current_section(session)
    if definition is None:
        return {"done": True, "question": None, "progress": len(session["answers"]), "sections": session["sections"]}
    state = session["sections"][definition["id"]]
    question = _section_engine(session, definition).next_question()
    if question is None:
        state["status"] = "completed"
        STORE.save(session)
        return {"done": False, "section_complete": True, "section": {"id": definition["id"], "label": definition["label"]}, "question": None, "progress": state["question_count"]}
    return _question_response(question, definition, state["question_count"], state["question_limit"])


@router.post("/sessions/{session_id}/answer")
def answer_question(session_id: str, payload: AnswerCreate, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    session = STORE.get(session_id, _user_id(current_user))
    if session["status"] != "in_progress":
        raise HTTPException(status_code=409, detail="Diagnostic session is not in progress")
    question = next((item for item in STORE._questions() if item["id"] == payload.question_id), None)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    definition = _current_section(session)
    question_section = _section_for_question(question)
    if definition is None:
        raise HTTPException(status_code=409, detail="Diagnostic session is complete")
    if question_section["id"] != definition["id"]:
        raise HTTPException(status_code=409, detail=f"Complete {definition['label']} before starting {question_section['label']}")
    engine = _section_engine(session, definition)
    if payload.question_id in engine.answered_ids:
        raise HTTPException(status_code=409, detail="Question already answered")
    correct = engine.answer(question, payload.answer)
    answer = {"question_id": payload.question_id, "correct": correct, "time_taken_s": payload.time_taken_s, "section": definition["id"]}
    session["answers"].append(answer)
    state = session["sections"][definition["id"]]
    state["question_count"] += 1
    state["correct_count"] += int(correct)
    state.setdefault("answers", []).append(answer)
    section_complete = state["question_count"] >= state["question_limit"] or engine.next_question() is None
    if section_complete:
        state["status"] = "completed"
        next_index = SECTION_DEFINITIONS.index(definition) + 1
        if next_index < len(SECTION_DEFINITIONS):
            session["sections"][SECTION_DEFINITIONS[next_index]["id"]]["status"] = "in_progress"
    STORE.save(session)
    next_definition = _current_section(session)
    return {"correct": correct, "progress": len(session["answers"]), "section_complete": section_complete, "section": {"id": definition["id"], "label": definition["label"]}, "next_section": {"id": next_definition["id"], "label": next_definition["label"]} if section_complete and next_definition else None}


def _profile_vector(mastery: dict[str, float], questions: list[dict[str, Any]]) -> list[float]:
    by_category: dict[str, list[float]] = {}
    for question in questions:
        if question["topic_id"] in mastery:
            by_category.setdefault(question.get("category", ""), []).append(mastery[question["topic_id"]])
    aptitude = by_category.get("aptitude", []) + by_category.get("English", [])
    groups = [by_category.get("DSA", []), aptitude, by_category.get("CS core", []), [], []]
    return [sum(values) / len(values) if values else 0.5 for values in groups for _ in range(5)]


def _section_reports(session: dict[str, Any], mastery: dict[str, float], questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    topic_names = {question["topic_id"]: question["topic_id"] for question in questions}
    reports = []
    for definition in SECTION_DEFINITIONS:
        state = session["sections"][definition["id"]]
        topic_ids = {question["topic_id"] for question in questions if _section_for_question(question)["id"] == definition["id"]}
        section_mastery = {topic: mastery.get(topic, 0.5) for topic in topic_ids}
        ranked = sorted(section_mastery, key=section_mastery.get)
        reports.append({"id": definition["id"], "label": definition["label"], "description": definition["description"], "question_count": state["question_count"], "question_limit": state["question_limit"], "correct_count": state["correct_count"], "score": state["correct_count"] / max(1, state["question_count"]), "strong_topics": [topic_names[topic] for topic in ranked[-2:]], "weak_topics": [topic_names[topic] for topic in ranked[:2]]})
    return reports


@router.post("/sessions/{session_id}/complete")
def complete_session(session_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    session = STORE.get(session_id, _user_id(current_user))
    if session["status"] != "in_progress":
        raise HTTPException(status_code=409, detail="Diagnostic session is not in progress")
    if _current_section(session) is not None and not STORE.legacy_completion:
        raise HTTPException(status_code=409, detail="Complete all diagnostic sections before submitting")
    questions = STORE._questions()
    mastery: dict[str, float] = {}
    for definition in SECTION_DEFINITIONS:
        mastery.update(_section_engine(session, definition).mastery())
    for topic_id, value in mastery.items():
        apply_evidence(session["user_id"], topic_id, value, "diagnostic", 1.0)
    assignment = assign_profile(_profile_vector(mastery, questions), PROFILE)
    result = {"mastery": mastery, "confidence": sum(_section_engine(session, definition).confidence() for definition in SECTION_DEFINITIONS) / len(SECTION_DEFINITIONS), "sections": _section_reports(session, mastery, questions), **assignment}
    session.update({"status": "completed", "completed_at": datetime.now(timezone.utc).isoformat(), "result": result})
    STORE.save(session)
    if STORE.supabase:
        retry_supabase(lambda: STORE.supabase.table("cluster_assignments").insert({"user_id": session["user_id"], "session_id": session_id, **assignment}).execute())
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
    return max((_public_session(session) for session in sessions), key=lambda session: session["completed_at"]) if sessions else None
