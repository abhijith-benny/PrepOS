from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import get_current_user
from app.shared.events import AttemptRecorded, CardReviewed, EventBus, PlanGenerated, SkillUpdated
from app.shared.learner_model import EVENT_BUS, get_skill_vector
from app.shared.repositories import profile_repository, study_plan_repository, topic_repository

from .scheduler_engine import build_weekly_plan

router = APIRouter(prefix="/schedule", tags=["scheduler"])
WEEKLY_DEFAULT_HOURS = 20
MIN_BLOCK_MINUTES = 30
WEAK_THRESHOLD = 0.6
MASTERED_THRESHOLD = 0.8


class SchedulerSignals:
    evidence_since_generation: dict[tuple[str, str], int] = {}
    mastered_topics: dict[str, set[str]] = {}


SIGNALS = SchedulerSignals()


def _user_id(current_user: dict[str, Any]) -> str:
    return str(current_user.get("id", current_user.get("sub")))


def _week_start(today: date | None = None) -> date:
    value = today or date.today()
    return value - timedelta(days=value.weekday())


def _on_evidence(event: Any) -> None:
    topic_id = event.payload.get("topic_id")
    if topic_id:
        key = (event.user_id, topic_id)
        SIGNALS.evidence_since_generation[key] = SIGNALS.evidence_since_generation.get(key, 0) + 1


def _on_skill_updated(event: Any) -> None:
    if event.payload.get("mastery", 0.0) >= MASTERED_THRESHOLD:
        SIGNALS.mastered_topics.setdefault(event.user_id, set()).add(event.payload["topic_id"])


EVENT_BUS.subscribe(AttemptRecorded.__name__, _on_evidence)
EVENT_BUS.subscribe(CardReviewed.__name__, _on_evidence)
EVENT_BUS.subscribe(SkillUpdated.__name__, _on_skill_updated)


def _serialize(plan: dict[str, Any]) -> dict[str, Any]:
    return {**plan, "sessions": plan.get("sessions", [])}


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"module": "scheduler", "status": "ready"}


@router.post("/generate")
def generate_schedule(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    user_id = _user_id(current_user)
    today = date.today()
    week_start = _week_start(today)
    profile = profile_repository.get(user_id)
    weekly_hours = float(profile.get("weekly_hours") or WEEKLY_DEFAULT_HOURS)
    topics = topic_repository.list_topics()
    skill_vector = get_skill_vector(user_id)
    mastery = {topic_id: state.mastery for topic_id, state in skill_vector.items()}
    result = build_weekly_plan(
        topics,
        mastery,
        weekly_hours,
        profile.get("preferred_days"),
        profile.get("preferred_times"),
        MIN_BLOCK_MINUTES,
        WEAK_THRESHOLD,
        MASTERED_THRESHOLD,
        week_start=week_start,
    )
    if not result.feasible:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"reason": result.reason, "minimum_hours_needed": result.minimum_hours_needed},
        )

    previous = study_plan_repository.current(user_id, week_start)
    completed = [session for session in (previous or {}).get("sessions", []) if session.get("status") == "completed"]
    if previous:
        study_plan_repository.archive(user_id, previous["id"])
    plan_id = str(uuid4())
    sessions = [
        {**session, "id": str(uuid4()), "plan_id": plan_id, "user_id": user_id}
        for session in completed
    ]
    sessions.extend(
        {
            **session,
            "id": str(uuid4()),
            "plan_id": plan_id,
            "user_id": user_id,
            "optional": session["topic_id"] in SIGNALS.mastered_topics.get(user_id, set()),
        }
        for session in result.sessions
    )
    target_date = profile.get("target_date")
    horizon_weeks = max(1, math.ceil((date.fromisoformat(target_date) - today).days / 7)) if target_date else 1
    plan = {
        "id": plan_id,
        "user_id": user_id,
        "week_start_date": week_start.isoformat(),
        "status": "active",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "horizon_weeks": horizon_weeks,
        "config": {"weekly_hours": weekly_hours, "min_block_minutes": MIN_BLOCK_MINUTES, "weak_threshold": WEAK_THRESHOLD},
        "sessions": sessions,
    }
    study_plan_repository.create(plan)
    EventBus().emit(PlanGenerated(user_id=user_id, payload={"plan_id": plan_id, "session_count": len(sessions)}))
    return _serialize(plan)


@router.get("/current")
def current_schedule(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any] | None:
    plan = study_plan_repository.current(_user_id(current_user), _week_start())
    return _serialize(plan) if plan else None


@router.post("/sessions/{session_id}/complete")
def complete_session(session_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return _update_session(session_id, _user_id(current_user), "completed")


@router.post("/sessions/{session_id}/skip")
def skip_session(session_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return _update_session(session_id, _user_id(current_user), "skipped")


def _update_session(session_id: str, user_id: str, session_status: str) -> dict[str, Any]:
    current = study_plan_repository.current(user_id, _week_start())
    if not current:
        raise HTTPException(status_code=404, detail="Plan not found")
    session = study_plan_repository.update_session(user_id, current["id"], session_id, session_status)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/history")
def schedule_history(
    current_user: dict[str, Any] = Depends(get_current_user),
    limit: int = Query(default=10, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    return [_serialize(plan) for plan in study_plan_repository.history(_user_id(current_user), limit, offset)]
