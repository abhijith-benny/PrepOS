from __future__ import annotations

from app.core.config import settings
from app.shared.repositories.in_memory import (
    InMemoryAttemptRepository,
    InMemoryEventRepository,
    InMemorySkillRepository,
)
from app.shared.repositories.interfaces import (
    AttemptRepository,
    EventRepository,
    ProfileRepository,
    SkillRepository,
    StudyPlanRepository,
    TopicRepository,
)
from app.shared.repositories.scheduler import (
    InMemoryProfileRepository,
    InMemoryStudyPlanRepository,
    InMemoryTopicRepository,
    create_scheduler_repositories,
)
from app.shared.repositories.coding import InMemoryCodingRepository, create_coding_repository
from app.shared.repositories.supabase import create_supabase_repositories


if settings.supabase_url and settings.supabase_service_role_key:
    skill_repository, event_repository, attempt_repository = create_supabase_repositories(
        settings.supabase_url,
        settings.supabase_service_role_key,
    )
    topic_repository, profile_repository, study_plan_repository = create_scheduler_repositories(
        settings.supabase_url,
        settings.supabase_service_role_key,
    )
    coding_repository = create_coding_repository(settings.supabase_url, settings.supabase_service_role_key)
else:
    skill_repository = InMemorySkillRepository()
    event_repository = InMemoryEventRepository()
    attempt_repository = InMemoryAttemptRepository()
    topic_repository = InMemoryTopicRepository()
    profile_repository = InMemoryProfileRepository()
    study_plan_repository = InMemoryStudyPlanRepository()
    coding_repository = InMemoryCodingRepository()


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
    "ProfileRepository",
    "StudyPlanRepository",
    "TopicRepository",
    "profile_repository",
    "study_plan_repository",
    "topic_repository",
    "coding_repository",
]