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


class TopicRepository(Protocol):
    def list_topics(self) -> list[dict[str, Any]]: ...


class ProfileRepository(Protocol):
    def get(self, user_id: str) -> dict[str, Any]: ...


class StudyPlanRepository(Protocol):
    def create(self, plan: dict[str, Any]) -> dict[str, Any]: ...

    def archive(self, user_id: str, plan_id: str) -> None: ...

    def current(self, user_id: str, week_start: Any) -> dict[str, Any] | None: ...

    def get(self, user_id: str, plan_id: str) -> dict[str, Any] | None: ...

    def history(self, user_id: str, limit: int, offset: int) -> list[dict[str, Any]]: ...

    def update_session(self, user_id: str, plan_id: str, session_id: str, status: str) -> dict[str, Any] | None: ...