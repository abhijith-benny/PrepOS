from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.core.config import settings
from app.core.deps import get_current_user
from app.shared.events import InterviewScored
from app.shared.learner_model import EVENT_BUS, apply_evidence
from .audio import AudioTranscriptionService
from .evaluator import InterviewRubricEvaluator
from .generator import InterviewQuestionGenerator
from .schemas import (
    InterviewSessionCreate,
    NextQuestionResponse,
    QuestionItem,
    SessionSummaryResponse,
    TurnEvaluationResponse,
    TurnSubmitRequest,
)
from .ui import INTERVIEW_HTML

try:
    from supabase import Client, create_client
except ImportError:  # pragma: no cover
    Client = Any
    create_client = None


router = APIRouter(prefix="/interview", tags=["interview"])


@router.get("/ui", response_class=HTMLResponse)
def get_interview_ui() -> HTMLResponse:
    return HTMLResponse(content=INTERVIEW_HTML)


class InterviewStore:
    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, Any]] = {}
        self.turns: dict[str, list[dict[str, Any]]] = {}
        self.supabase: Client | None = None
        if settings.supabase_url and settings.supabase_service_role_key and create_client:
            self.supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    def start(self, user_id: str, round_type: str, target_role: str, total_questions: int) -> dict[str, Any]:
        # Check if user already has an active session
        existing = self._find_in_progress(user_id)
        if existing:
            return existing

        session_id = str(uuid4())
        session = {
            "id": session_id,
            "user_id": user_id,
            "round_type": round_type,
            "target_role": target_role,
            "status": "in_progress",
            "total_questions": total_questions,
            "current_question_index": 0,
            "overall_score": None,
            "summary_feedback": None,
            "strengths": [],
            "improvements": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
        }
        if self.supabase:
            self.supabase.table("interview_sessions").insert(session).execute()

        self.sessions[session_id] = session
        self.turns[session_id] = []
        return session

    def _find_in_progress(self, user_id: str) -> dict[str, Any] | None:
        local = next(
            (s for s in self.sessions.values() if s["user_id"] == user_id and s["status"] == "in_progress"),
            None,
        )
        if local:
            return local
        if self.supabase:
            rows = (
                self.supabase.table("interview_sessions")
                .select("*")
                .eq("user_id", user_id)
                .eq("status", "in_progress")
                .limit(1)
                .execute()
                .data
            )
            if rows:
                session = rows[0]
                self.sessions[session["id"]] = session
                self.turns.setdefault(session["id"], [])
                return session
        return None

    def get(self, session_id: str, user_id: str) -> dict[str, Any]:
        session = self.sessions.get(session_id)
        if session and session["user_id"] == user_id:
            return session
        if self.supabase:
            rows = (
                self.supabase.table("interview_sessions")
                .select("*")
                .eq("id", session_id)
                .eq("user_id", user_id)
                .limit(1)
                .execute()
                .data
            )
            if rows:
                session = rows[0]
                self.sessions[session_id] = session
                self.turns.setdefault(session_id, [])
                return session
        raise HTTPException(status_code=404, detail="Interview session not found")

    def get_turns(self, session_id: str) -> list[dict[str, Any]]:
        if session_id in self.turns:
            return self.turns[session_id]
        if self.supabase:
            rows = (
                self.supabase.table("interview_turns")
                .select("*")
                .eq("session_id", session_id)
                .order("turn_number")
                .execute()
                .data
            )
            self.turns[session_id] = rows
            return rows
        return []

    def record_turn(self, session_id: str, turn: dict[str, Any]) -> None:
        self.turns.setdefault(session_id, []).append(turn)
        if self.supabase:
            self.supabase.table("interview_turns").insert(turn).execute()

    def update_session(self, session_id: str, updates: dict[str, Any]) -> None:
        if session_id in self.sessions:
            self.sessions[session_id].update(updates)
        if self.supabase:
            self.supabase.table("interview_sessions").update(updates).eq("id", session_id).execute()


STORE = InterviewStore()


@router.post("/sessions", status_code=201)
def start_interview(
    payload: InterviewSessionCreate,
    current_user=Depends(get_current_user),
) -> dict[str, Any]:
    user_id = str(current_user.get("id", current_user.get("sub")))
    return STORE.start(
        user_id=user_id,
        round_type=payload.round_type,
        target_role=payload.target_role,
        total_questions=payload.total_questions,
    )


@router.get("/sessions/{session_id}/next", response_model=NextQuestionResponse)
def get_next_question(
    session_id: str,
    current_user=Depends(get_current_user),
) -> NextQuestionResponse:
    user_id = str(current_user.get("id", current_user.get("sub")))
    session = STORE.get(session_id, user_id)

    curr_index = session["current_question_index"]
    total = session["total_questions"]

    if curr_index >= total or session["status"] == "completed":
        return NextQuestionResponse(
            session_id=session_id,
            turn_number=curr_index,
            total_questions=total,
            is_complete=True,
            question=None,
        )

    turn_number = curr_index + 1
    turns = STORE.get_turns(session_id)
    last_feedback = turns[-1].get("feedback") if turns else None

    q_data = InterviewQuestionGenerator.generate_question(
        round_type=session["round_type"],
        target_role=session["target_role"],
        turn_number=turn_number,
        previous_feedback=last_feedback,
    )

    return NextQuestionResponse(
        session_id=session_id,
        turn_number=turn_number,
        total_questions=total,
        is_complete=False,
        question=QuestionItem(
            turn_number=turn_number,
            topic=q_data["topic"],
            question=q_data["question"],
            context_hint=q_data.get("hint"),
        ),
    )


@router.post("/sessions/{session_id}/answer", response_model=TurnEvaluationResponse)
def submit_answer(
    session_id: str,
    payload: TurnSubmitRequest,
    current_user=Depends(get_current_user),
    x_gemini_key: str | None = Header(default=None, alias="X-Gemini-Key"),
    x_openai_key: str | None = Header(default=None, alias="X-OpenAI-Key"),
) -> TurnEvaluationResponse:
    user_id = str(current_user.get("id", current_user.get("sub")))
    session = STORE.get(session_id, user_id)

    if session["status"] == "completed":
        raise HTTPException(status_code=400, detail="Interview session is already completed")

    turn_num = payload.turn_number
    # Generate the question details that were asked for this turn
    q_data = InterviewQuestionGenerator.generate_question(
        round_type=session["round_type"],
        target_role=session["target_role"],
        turn_number=turn_num,
    )

    # Evaluate the student's answer using rubric criteria
    evaluation = InterviewRubricEvaluator.evaluate(
        round_type=session["round_type"],
        question=q_data["question"],
        topic=q_data["topic"],
        answer_transcript=payload.answer_transcript,
        model_answer=q_data["model_answer"],
        time_taken_s=payload.time_taken_s,
        custom_key=x_gemini_key or x_openai_key,
    )

    scores = evaluation["scores"]
    turn_record = {
        "id": str(uuid4()),
        "session_id": session_id,
        "turn_number": turn_num,
        "topic": q_data["topic"],
        "question": q_data["question"],
        "answer_transcript": payload.answer_transcript,
        "audio_url": None,
        "accuracy_score": scores.accuracy,
        "structure_score": scores.structure,
        "communication_score": scores.communication,
        "overall_turn_score": scores.overall,
        "feedback": evaluation["feedback"],
        "model_answer": q_data["model_answer"],
        "time_taken_s": payload.time_taken_s,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    STORE.record_turn(session_id, turn_record)

    next_idx = turn_num
    is_done = next_idx >= session["total_questions"]
    STORE.update_session(session_id, {"current_question_index": next_idx})

    next_q = None
    next_turn_no = None
    if not is_done:
        next_turn_no = next_idx + 1
        next_q_data = InterviewQuestionGenerator.generate_question(
            round_type=session["round_type"],
            target_role=session["target_role"],
            turn_number=next_turn_no,
            previous_feedback=evaluation["feedback"],
        )
        next_q = next_q_data["question"]

    return TurnEvaluationResponse(
        turn_number=turn_num,
        question=q_data["question"],
        topic=q_data["topic"],
        answer_transcript=payload.answer_transcript,
        scores=scores,
        feedback=evaluation["feedback"],
        model_answer=q_data["model_answer"],
        time_taken_s=payload.time_taken_s,
        is_complete=is_done,
        next_question=next_q,
        next_turn_number=next_turn_no,
    )


@router.post("/sessions/{session_id}/transcribe")
async def transcribe_audio(
    session_id: str,
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
) -> dict[str, str]:
    user_id = str(current_user.get("id", current_user.get("sub")))
    STORE.get(session_id, user_id)  # Validate ownership

    contents = await file.read()
    transcript = AudioTranscriptionService.transcribe(contents, filename=file.filename or "audio.wav")
    return {"transcript": transcript}


@router.post("/sessions/{session_id}/complete", response_model=SessionSummaryResponse)
def complete_interview(
    session_id: str,
    current_user=Depends(get_current_user),
) -> SessionSummaryResponse:
    user_id = str(current_user.get("id", current_user.get("sub")))
    session = STORE.get(session_id, user_id)
    turns = STORE.get_turns(session_id)

    if not turns:
        overall_score = 0.0
        feedback = "Interview session ended with no recorded answers."
        strengths = []
        improvements = ["Attempt at least one question to receive comprehensive evaluation."]
    else:
        overall_score = round(sum(t.get("overall_turn_score", 0.0) for t in turns) / len(turns), 1)
        feedback = (
            f"Completed {len(turns)} {session['round_type']} interview question(s) "
            f"with an overall performance score of {overall_score}/100."
        )
        avg_acc = sum(t.get("accuracy_score", 0.0) for t in turns) / len(turns)
        avg_struct = sum(t.get("structure_score", 0.0) for t in turns) / len(turns)
        avg_comm = sum(t.get("communication_score", 0.0) for t in turns) / len(turns)

        strengths = []
        improvements = []

        if avg_acc >= 7.0:
            strengths.append("Strong technical/situational knowledge base.")
        else:
            improvements.append("Deepen core topic fundamentals and algorithm time/space complexities.")

        if avg_struct >= 7.0:
            strengths.append("Structured problem solving and clear progression.")
        else:
            improvements.append("Use a more deliberate framework (e.g. STAR method or approach-tradeoff breakdown).")

        if avg_comm >= 7.0:
            strengths.append("Concise and articulate communication style.")
        else:
            improvements.append("Refine pacing and avoid overly brief or rambling responses.")

    completed_at = datetime.now(timezone.utc).isoformat()
    updates = {
        "status": "completed",
        "overall_score": overall_score,
        "summary_feedback": feedback,
        "strengths": strengths,
        "improvements": improvements,
        "completed_at": completed_at,
    }
    STORE.update_session(session_id, updates)

    # Emit InterviewScored event on the event bus
    event = InterviewScored(
        user_id=user_id,
        payload={
            "session_id": session_id,
            "round_type": session["round_type"],
            "target_role": session["target_role"],
            "overall_score": overall_score,
            "turns_count": len(turns),
        },
    )
    EVENT_BUS.emit(event)

    # Also apply evidence to learner model skill vector
    interview_topic = "System Design 1" if session["round_type"] == "technical" else "Behavioral 1"
    apply_evidence(
        user_id=user_id,
        topic_id=interview_topic,
        score=overall_score / 100.0,
        source="interview",
        weight=1.5,
    )

    return SessionSummaryResponse(
        session_id=session_id,
        user_id=user_id,
        round_type=session["round_type"],
        target_role=session["target_role"],
        status="completed",
        total_questions=session["total_questions"],
        completed_turns=len(turns),
        overall_score=overall_score,
        summary_feedback=feedback,
        strengths=strengths,
        improvements=improvements,
        turns=turns,
    )


@router.get("/sessions/{session_id}", response_model=SessionSummaryResponse)
def get_session_summary(
    session_id: str,
    current_user=Depends(get_current_user),
) -> SessionSummaryResponse:
    user_id = str(current_user.get("id", current_user.get("sub")))
    session = STORE.get(session_id, user_id)
    turns = STORE.get_turns(session_id)

    return SessionSummaryResponse(
        session_id=session_id,
        user_id=user_id,
        round_type=session["round_type"],
        target_role=session["target_role"],
        status=session["status"],
        total_questions=session["total_questions"],
        completed_turns=len(turns),
        overall_score=session.get("overall_score") or 0.0,
        summary_feedback=session.get("summary_feedback") or "In progress",
        strengths=session.get("strengths") or [],
        improvements=session.get("improvements") or [],
        turns=turns,
    )
