from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from app.shared.schemas import SkillState


class SkillRepository(Protocol):
    def get_for_user(self, user_id: str) -> dict[str, SkillState]: ...

    def upsert(self, user_id: str, state: SkillState) -> SkillState: ...


class EventRepository(Protocol):
    def record(
        self,
        user_id: str,
        type_: str,
        payload: dict[str, Any],
        created_at: datetime | None = None,
    ) -> dict[str, Any]: ...


class AttemptRepository(Protocol):
    def create(self, user_id: str, attempt: dict[str, Any]) -> dict[str, Any]: ...