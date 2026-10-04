from pathlib import Path

from dotenv import load_dotenv
import pytest

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@pytest.fixture(autouse=True)
def in_memory_repositories(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
	if request.node.get_closest_marker("integration"):
		yield
		return

	from app.main import app
	import app.main as main_module
	import app.modules.diagnostic.router as diagnostic_router
	import app.modules.scheduler.router as scheduler_router
	import app.shared.events as events_module
	import app.shared.learner_model as learner_model
	from app.shared.events import EventBus
	from app.shared.repositories.in_memory import InMemoryAttemptRepository, InMemoryEventRepository, InMemorySkillRepository
	from app.shared.repositories.scheduler import InMemoryProfileRepository, InMemoryStudyPlanRepository, InMemoryTopicRepository

	monkeypatch.setattr(main_module, "attempt_repository", InMemoryAttemptRepository())
	monkeypatch.setattr(main_module, "profile_repository", InMemoryProfileRepository())
	monkeypatch.setattr(events_module, "event_repository", InMemoryEventRepository())
	monkeypatch.setattr(learner_model, "skill_repository", InMemorySkillRepository())
	monkeypatch.setattr(learner_model, "EVENT_BUS", EventBus())
	monkeypatch.setattr(main_module, "EVENT_BUS", learner_model.EVENT_BUS)
	monkeypatch.setattr(diagnostic_router, "EVENT_BUS", learner_model.EVENT_BUS)
	monkeypatch.setattr(diagnostic_router.STORE, "supabase", None)
	monkeypatch.setattr(diagnostic_router.STORE, "legacy_completion", True)
	diagnostic_router.STORE.sessions.clear()
	monkeypatch.setattr(scheduler_router, "profile_repository", InMemoryProfileRepository())
	monkeypatch.setattr(scheduler_router, "study_plan_repository", InMemoryStudyPlanRepository())
	monkeypatch.setattr(scheduler_router, "topic_repository", InMemoryTopicRepository())
	monkeypatch.setattr(scheduler_router, "EVENT_BUS", learner_model.EVENT_BUS)
	app.dependency_overrides.clear()
	yield
	app.dependency_overrides.clear()
