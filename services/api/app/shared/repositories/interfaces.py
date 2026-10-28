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

    def save(self, user_id: str, profile: dict[str, Any]) -> dict[str, Any]: ...


class StudyPlanRepository(Protocol):
    def create(self, plan: dict[str, Any]) -> dict[str, Any]: ...

    def archive(self, user_id: str, plan_id: str) -> None: ...

    def current(self, user_id: str, week_start: Any) -> dict[str, Any] | None: ...

    def get(self, user_id: str, plan_id: str) -> dict[str, Any] | None: ...

    def history(self, user_id: str, limit: int, offset: int) -> list[dict[str, Any]]: ...

    def update_session(self, user_id: str, plan_id: str, session_id: str, status: str) -> dict[str, Any] | None: ...


class QuestionRepository(Protocol):
    def get(self, question_id: str) -> dict[str, Any] | None: ...

    def list_for_topics(
        self,
        topic_ids: list[str],
        limit: int = 10,
        exclude_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]: ...


class SRSRepository(Protocol):
    def get_card(self, user_id: str, card_id: str) -> dict[str, Any] | None: ...

    def get_card_by_question(self, user_id: str, question_id: str) -> dict[str, Any] | None: ...

    def list_cards(self, user_id: str, state: str | None = None) -> list[dict[str, Any]]: ...

    def create_card(self, card_data: dict[str, Any]) -> dict[str, Any]: ...

    def update_card(self, user_id: str, card_id: str, updates: dict[str, Any]) -> dict[str, Any] | None: ...

    def get_due_cards(
        self,
        user_id: str,
        now: datetime,
        limit: int = 20,
        new_card_limit: int = 10,
    ) -> list[dict[str, Any]]: ...

    def record_review(self, review_data: dict[str, Any]) -> dict[str, Any]: ...

    def get_stats(self, user_id: str, now: datetime) -> dict[str, Any]: ...