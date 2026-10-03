from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.shared.events import EventBus, SkillUpdated
from app.shared.repositories import skill_repository
from app.shared.schemas import SkillState

EVENT_BUS = EventBus()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_skill_vector(user_id: str) -> dict[str, SkillState]:
    return skill_repository.get_for_user(user_id)


def record_event(user_id: str, type_: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist an event entry through the configured event repository."""
    from app.shared.events import record_event as persist_event

    return persist_event(user_id, type_, payload)


def apply_evidence(
    user_id: str,
    topic_id: str,
    score: float,
    source: str,
    weight: float = 1.0,
) -> dict[str, SkillState]:
    """Simple placeholder evidence update using an exponential moving average.

    TODO: replace with the production learner model in M1.
    """
    current = skill_repository.get_for_user(user_id).get(topic_id)

    if current is None:
        next_state = SkillState(
            topic_id=topic_id,
            mastery=max(0.0, min(1.0, float(score))),
            confidence=max(0.0, min(1.0, float(weight))),
            updated_at=_utc_now(),
        )
    else:
        alpha = 0.35
        updated_mastery = current.mastery * (1 - alpha) + float(score) * alpha
        updated_confidence = current.confidence * (1 - alpha) + min(1.0, float(weight)) * alpha
        next_state = SkillState(
            topic_id=topic_id,
            mastery=max(0.0, min(1.0, updated_mastery)),
            confidence=max(0.0, min(1.0, updated_confidence)),
            updated_at=_utc_now(),
        )

    next_state = skill_repository.upsert(user_id, next_state)
    event = SkillUpdated(
        user_id=user_id,
        payload={
            "topic_id": topic_id,
            "mastery": next_state.mastery,
            "confidence": next_state.confidence,
            "source": source,
            "weight": weight,
        },
    )
    EVENT_BUS.emit(event)
    return {topic_id: next_state}
