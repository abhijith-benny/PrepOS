from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.shared.schemas import SkillState


class InMemorySkillRepository:
    def __init__(self) -> None:
        self.states: dict[str, dict[str, SkillState]] = {}

    def get_for_user(self, user_id: str) -> dict[str, SkillState]:
        return {
            topic_id: state.model_copy()
            for topic_id, state in self.states.get(user_id, {}).items()
        }

    def upsert(self, user_id: str, state: SkillState) -> SkillState:
        self.states.setdefault(user_id, {})[state.topic_id] = state.model_copy()
        return state.model_copy()


class InMemoryEventRepository:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def record(
        self,
        user_id: str,
        type_: str,
        payload: dict[str, Any],
        created_at: datetime | None = None,
    ) -> dict[str, Any]:
        entry = {
            "id": str(len(self.events) + 1),
            "user_id": user_id,
            "type": type_,
            "payload": payload,
            "created_at": (created_at or datetime.now(timezone.utc)).isoformat(),
        }
        self.events.append(entry)
        return dict(entry)


class InMemoryAttemptRepository:
    def __init__(self) -> None:
        self.attempts: list[dict[str, Any]] = []

    def create(self, user_id: str, attempt: dict[str, Any]) -> dict[str, Any]:
        entry = {"id": str(len(self.attempts) + 1), "user_id": user_id, **attempt}
        self.attempts.append(entry)
        return dict(entry)