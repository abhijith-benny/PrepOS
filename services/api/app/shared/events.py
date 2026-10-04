from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from pydantic import BaseModel, Field

from app.shared.repositories import event_repository
from app.shared.repositories.interfaces import EventRepository


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BaseEvent(BaseModel):
    user_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

    @property
    def type(self) -> str:
        return self.__class__.__name__


class AttemptRecorded(BaseEvent):
    pass


class SkillUpdated(BaseEvent):
    pass


class InterviewScored(BaseEvent):
    pass


class PlanGenerated(BaseEvent):
    pass


class CardReviewed(BaseEvent):
    pass


class DiagnosticCompleted(BaseEvent):
    pass


def record_event(user_id: str, type_: str, payload: dict[str, Any]) -> dict[str, Any]:
    return event_repository.record(user_id, type_, payload)


class EventBus:
    def __init__(self, repository: EventRepository | None = None) -> None:
        self._repository = repository or event_repository
        self._listeners: dict[str, list[Callable[[BaseEvent], None]]] = {}
        self._events: list[BaseEvent] = []

    def subscribe(self, event_type: str, listener: Callable[[BaseEvent], None]) -> None:
        self._listeners.setdefault(event_type, []).append(listener)

    def emit(self, event: BaseEvent) -> dict[str, Any]:
        self._events.append(event)
        for listener in self._listeners.get(event.type, []):
            listener(event)
        return self._repository.record(event.user_id, event.type, event.payload, event.created_at)

    @property
    def events(self) -> list[BaseEvent]:
        return list(self._events)
