from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.core.deps import get_current_user


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_auth_rejected_for_protected_routes() -> None:
    response = client.get("/me")
    assert response.status_code == 401


def test_attempt_flow_updates_skill_vector() -> None:
    app.dependency_overrides[get_current_user] = lambda: {"id": "user-123", "email": "demo@example.com"}
    try:
        response = client.post(
            "/attempts",
            json={
                "question_id": "q-1",
                "topic_id": "topic-1",
                "correct": True,
                "time_taken_s": 18,
                "source": "quiz",
                "weight": 1.0,
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["user_id"] == "user-123"
        assert "topic-1" in data["skill_vector"]
        assert data["skill_vector"]["topic-1"]["mastery"] >= 0.0
    finally:
        app.dependency_overrides.clear()


def test_module_import_boundary() -> None:
    root = Path(__file__).resolve().parents[1]
    offenders: list[str] = []
    for path in sorted((root / "app").rglob("*.py")):
        if "app/modules" not in str(path):
            continue
        text = path.read_text(encoding="utf-8")
        if "from app.modules" in text or "import app.modules" in text:
            offenders.append(str(path.relative_to(root)))
    assert offenders == [], f"Modules import from each other: {offenders}"
