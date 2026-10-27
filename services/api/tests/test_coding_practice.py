from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.core.deps import get_current_user
from app.main import app
from app.modules.coding_practice import leetcode_client
from app.modules.coding_practice import router as coding_router
from app.shared.repositories.coding import InMemoryCodingRepository
from app.shared.repositories.scheduler import InMemoryProfileRepository


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeHttp:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def post(self, *args, **kwargs):
        self.calls += 1
        return FakeResponse(self.payload)


def test_leetcode_client_parses_and_caches_submissions() -> None:
    http = FakeHttp({"data": {"recentAcSubmissionList": [{"title": "Two Sum", "titleSlug": "two-sum", "timestamp": "1"}]}})
    client = leetcode_client.LeetCodeClient(http_client=http)
    assert client.recent_accepted_submissions("public-user")[0]["titleSlug"] == "two-sum"
    client.recent_accepted_submissions("public-user")
    assert http.calls == 1


def test_leetcode_client_distinguishes_private_and_empty() -> None:
    from pytest import raises

    with raises(leetcode_client.PrivateProfileError):
        leetcode_client.LeetCodeClient(FakeHttp({"data": {"recentAcSubmissionList": None}})).recent_accepted_submissions("private")
    with raises(leetcode_client.EmptySubmissionError):
        leetcode_client.LeetCodeClient(FakeHttp({"data": {"recentAcSubmissionList": []}})).recent_accepted_submissions("empty")


def test_assign_verify_and_ownership(monkeypatch) -> None:
    profile = InMemoryProfileRepository()
    repository = InMemoryCodingRepository()
    user_id = "coding-user"
    profile.save(user_id, {"leetcode_username": "public-user"})
    monkeypatch.setattr(coding_router, "profile_repository", profile)
    monkeypatch.setattr(coding_router, "coding_repository", repository)

    class FakeLeetCode:
        def recent_accepted_submissions(self, username):
            return [{"titleSlug": "two-sum", "timestamp": str(int(datetime.now(timezone.utc).timestamp()) + 1)}]

    monkeypatch.setattr(coding_router, "CLIENT", FakeLeetCode())
    app.dependency_overrides[get_current_user] = lambda: {"id": user_id, "email": "coding@example.com"}
    try:
        client = TestClient(app)
        assignment = client.post("/coding/assign")
        assert assignment.status_code == 200
        assignment_id = assignment.json()["id"]
        verified = client.post(f"/coding/assignments/{assignment_id}/verify")
        assert verified.status_code == 200
        assert verified.json()["status"] == "verified"
    finally:
        app.dependency_overrides.clear()

    app.dependency_overrides[get_current_user] = lambda: {"id": "other-user", "email": "other@example.com"}
    try:
        assert TestClient(app).post(f"/coding/assignments/{assignment_id}/verify").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_missing_username_returns_422(monkeypatch) -> None:
    profile = InMemoryProfileRepository()
    monkeypatch.setattr(coding_router, "profile_repository", profile)
    monkeypatch.setattr(coding_router, "coding_repository", InMemoryCodingRepository())
    app.dependency_overrides[get_current_user] = lambda: {"id": "no-username", "email": "none@example.com"}
    try:
        assert TestClient(app).post("/coding/assign").status_code == 422
    finally:
        app.dependency_overrides.clear()
