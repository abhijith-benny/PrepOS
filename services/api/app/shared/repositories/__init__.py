from __future__ import annotations

from app.core.config import settings
from app.shared.repositories.in_memory import (
    InMemoryAttemptRepository,
    InMemoryEventRepository,
    InMemorySkillRepository,
)
from app.shared.repositories.interfaces import AttemptRepository, EventRepository, SkillRepository
from app.shared.repositories.supabase import create_supabase_repositories


if settings.supabase_url and settings.supabase_service_role_key:
    skill_repository, event_repository, attempt_repository = create_supabase_repositories(
        settings.supabase_url,
        settings.supabase_service_role_key,
    )
else:
    skill_repository = InMemorySkillRepository()
    event_repository = InMemoryEventRepository()
    attempt_repository = InMemoryAttemptRepository()


__all__ = [
    "AttemptRepository",
    "EventRepository",
    "SkillRepository",
    "InMemoryAttemptRepository",
    "InMemoryEventRepository",
    "InMemorySkillRepository",
    "attempt_repository",
    "event_repository",
    "skill_repository",
]