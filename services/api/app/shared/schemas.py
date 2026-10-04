from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"


class UserProfile(BaseModel):
    id: str | None = None
    email: str | None = None
    full_name: str | None = None
    target_role: str | None = None
    target_date: str | None = None
    weekly_hours: int | None = None
    department: str | None = None
    year_or_semester: str | None = None
    known_languages: list[str] | None = None


class UserProfileUpdate(BaseModel):
    full_name: str | None = None
    target_role: str | None = None
    target_date: str | None = None
    weekly_hours: int | None = Field(default=None, ge=1, le=80)
    department: str | None = None
    year_or_semester: str | None = None
    known_languages: list[str] | None = None


class MeResponse(UserProfile):
    pass


class TopicRead(BaseModel):
    id: str
    name: str
    category: str
    parent_id: str | None = None


class SkillState(BaseModel):
    topic_id: str
    mastery: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    updated_at: datetime | None = None


class AttemptCreate(BaseModel):
    question_id: str
    topic_id: str
    correct: bool
    time_taken_s: int | float
    source: str = "quiz"
    weight: float = Field(default=1.0, ge=0.0, le=10.0)


class AttemptResponse(BaseModel):
    user_id: str
    topic_id: str
    score: float
    skill_vector: dict[str, SkillState]


class EventLogEntry(BaseModel):
    id: str
    user_id: str
    type: str
    payload: dict[str, Any]
    created_at: datetime
