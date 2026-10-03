from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.deps import get_current_user
from app.main import app
from app.modules.diagnostic.adaptive import AdaptiveDiagnostic
from app.modules.diagnostic.profiling import assign_profile, fit_profile_model
from app.modules.diagnostic.router import STORE


def test_selection_never_repeats_and_posterior_moves() -> None:
    questions = [
        {"id": "q1", "topic_id": "t1", "difficulty": 2, "answer": "A"},
        {"id": "q2", "topic_id": "t1", "difficulty": 4, "answer": "A"},
        {"id": "q3", "topic_id": "t2", "difficulty": 3, "answer": "A"},
    ]
    engine = AdaptiveDiagnostic(questions, ["t1", "t2"], min_topic_coverage=1)
    first = engine.next_question()
    assert first is not None
    before = engine.posteriors[first["topic_id"]].mastery
    engine.answer(first, "A")
    assert engine.posteriors[first["topic_id"]].mastery > before
    second = engine.next_question()
    assert second is not None
    assert second["id"] != first["id"]


def test_stopping_rule_triggers_after_coverage() -> None:
    questions = [
        {"id": "q1", "topic_id": "t1", "difficulty": 2, "answer": "A"},
        {"id": "q2", "topic_id": "t2", "difficulty": 2, "answer": "A"},
    ]
    engine = AdaptiveDiagnostic(questions, ["t1", "t2"], min_topic_coverage=1)
    engine.answer(engine.next_question(), "A")
    engine.answer(engine.next_question(), "A")
    assert engine.should_stop()
    assert engine.next_question() is None


def test_profile_assignment_is_deterministic() -> None:
    profile = fit_profile_model(seed=11)
    vector = [0.8] * 5 + [0.4] * 20
    assert assign_profile(vector, profile) == assign_profile(vector, profile)


def test_diagnostic_requires_auth() -> None:
    response = TestClient(app).post("/diagnostic/sessions")
    assert response.status_code == 401


def test_full_flow_and_session_ownership() -> None:
    app.dependency_overrides[get_current_user] = lambda: {"id": "diagnostic-user", "email": "demo@example.com"}
    try:
        STORE.sessions.clear()
        client = TestClient(app)
        started = client.post("/diagnostic/sessions")
        assert started.status_code == 201
        session_id = started.json()["id"]
        next_response = client.get(f"/diagnostic/sessions/{session_id}/next")
        question = next_response.json()["question"]
        assert "answer" not in question
        answered = client.post(
            f"/diagnostic/sessions/{session_id}/answer",
            json={"question_id": question["id"], "answer": "A", "time_taken_s": 4},
        )
        assert answered.status_code == 200
        completed = client.post(f"/diagnostic/sessions/{session_id}/complete")
        assert completed.status_code == 200
        assert "model_version" in completed.json()
        report = client.get(f"/diagnostic/sessions/{session_id}/report")
        assert report.status_code == 200
        assert report.json()["weak_topics"]
    finally:
        app.dependency_overrides.clear()

    app.dependency_overrides[get_current_user] = lambda: {"id": "other-user", "email": "other@example.com"}
    try:
        assert TestClient(app).get(f"/diagnostic/sessions/{session_id}/report").status_code == 404
    finally:
        app.dependency_overrides.clear()