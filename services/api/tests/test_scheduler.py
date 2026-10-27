from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.deps import get_current_user
from app.main import app
from app.modules.scheduler.scheduler_engine import build_weekly_plan
from app.modules.scheduler import router as scheduler_router
from app.shared.repositories.in_memory import InMemorySkillRepository
from app.shared.repositories.in_memory import InMemoryEventRepository
from app.shared.repositories.scheduler import InMemoryProfileRepository, InMemoryStudyPlanRepository, InMemoryTopicRepository


def _topics(count: int = 4) -> list[dict[str, str]]:
    return [{"id": f"t{index}", "name": f"Topic {index}", "category": "DSA"} for index in range(count)]


def test_solver_respects_hours_and_slot_constraints() -> None:
    topics = _topics()
    result = build_weekly_plan(topics, {topic["id"]: 0.2 for topic in topics}, 2.0)
    assert result.feasible
    assert sum(session["duration_minutes"] for session in result.sessions) <= 120
    slots = [(session["day_of_week"], session["start_time"]) for session in result.sessions]
    assert len(slots) == len(set(slots))
    assert {session["topic_id"] for session in result.sessions} == {topic["id"] for topic in topics}
    assert all(session["duration_minutes"] >= 30 for session in result.sessions)


def test_infeasible_plan_returns_minimum_hours() -> None:
    result = build_weekly_plan(_topics(), {f"t{index}": 0.1 for index in range(4)}, 1.0)
    assert not result.feasible
    assert result.minimum_hours_needed == 2.0
    assert result.reason


def test_scheduler_api_flow_and_regeneration_preserves_completed() -> None:
    user_id = "scheduler-user"
    app.dependency_overrides[get_current_user] = lambda: {"id": user_id, "email": "scheduler@example.com"}
    scheduler_router.profile_repository = InMemoryProfileRepository()
    scheduler_router.study_plan_repository = InMemoryStudyPlanRepository()
    scheduler_router.topic_repository = InMemoryTopicRepository()
    import app.shared.learner_model as learner_model
    learner_model.skill_repository = InMemorySkillRepository()
    import app.shared.events as events
    events.event_repository = InMemoryEventRepository()
    try:
        client = TestClient(app)
        generated = client.post("/schedule/generate")
        assert generated.status_code == 200, generated.text
        plan = generated.json()
        session = next(item for item in plan["sessions"] if item["status"] == "scheduled")
        completed = client.post(f"/schedule/sessions/{session['id']}/complete")
        assert completed.status_code == 200
        regenerated = client.post("/schedule/generate")
        assert regenerated.status_code == 200
        assert any(item["status"] == "completed" for item in regenerated.json()["sessions"])
        assert client.get("/schedule/current").status_code == 200
        assert client.get("/schedule/history").status_code == 200
    finally:
        app.dependency_overrides.clear()

    app.dependency_overrides[get_current_user] = lambda: {"id": "another-user", "email": "another@example.com"}
    try:
        assert TestClient(app).post(f"/schedule/sessions/{session['id']}/skip").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_scheduler_requires_auth() -> None:
    assert TestClient(app).get("/schedule/current").status_code == 401