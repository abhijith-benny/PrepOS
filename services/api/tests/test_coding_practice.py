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
        def recent_accepted_submissions(self, username, force_refresh=False):
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


def test_verification_epoch_string_and_datetime_conversion() -> None:
    """Test known epoch string vs known assigned_at datetime conversion and comparison."""
    # Known assigned_at: 2026-10-21 03:40:00 UTC (epoch = 1792554000.0)
    assigned_at_iso = "2026-10-21T03:40:00+00:00"
    assigned_epoch = coding_router._parse_assigned_at_epoch(assigned_at_iso)
    assert assigned_epoch == 1792554000.0

    # Submission solved AFTER assignment (epoch string "1792554077" > 1792554000)
    solved_after = {"titleSlug": "two-sum", "timestamp": "1792554077"}
    assert coding_router.is_submission_verified(solved_after, "two-sum", assigned_epoch) is True

    # Submission solved BEFORE assignment (epoch string "1789794787" < 1792554000)
    solved_before = {"titleSlug": "two-sum", "timestamp": "1789794787"}
    assert coding_router.is_submission_verified(solved_before, "two-sum", assigned_epoch) is False

    # Submission solved at EXACT same epoch second
    solved_exact = {"titleSlug": "two-sum", "timestamp": "1792554000"}
    assert coding_router.is_submission_verified(solved_exact, "two-sum", assigned_epoch) is True


def test_verification_slug_case_and_whitespace_normalization() -> None:
    """Test that slug comparison strips whitespace and ignores case."""
    assigned_epoch = 1000.0
    valid_sub = {"titleSlug": "  Two-Sum  ", "timestamp": "2000"}

    # Target slugs with varying casing and whitespace
    assert coding_router.is_submission_verified(valid_sub, "two-sum", assigned_epoch) is True
    assert coding_router.is_submission_verified(valid_sub, "Two-Sum", assigned_epoch) is True
    assert coding_router.is_submission_verified(valid_sub, " TWO-SUM ", assigned_epoch) is True


    # Non-matching slug
    assert coding_router.is_submission_verified(valid_sub, "valid-parentheses", assigned_epoch) is False


def test_ai_selection_rejects_invalid_id_and_retries_once() -> None:
    """Verify that an invalid LLM response ID is rejected and retried, and never assigned."""
    import json
    from app.modules.coding_practice.ai_selector import select_coding_problems

    catalog = [
        {"id": "p-1", "title": "Two Sum", "leetcode_slug": "two-sum", "difficulty": "Easy", "topic_id": "arrays"},
        {"id": "p-2", "title": "Add Two Numbers", "leetcode_slug": "add-two-numbers", "difficulty": "Medium", "topic_id": "linked-list"},
        {"id": "p-3", "title": "LRU Cache", "leetcode_slug": "lru-cache", "difficulty": "Medium", "topic_id": "hash-table"},
        {"id": "p-4", "title": "Median of Two Sorted Arrays", "leetcode_slug": "median-of-two-sorted-arrays", "difficulty": "Hard", "topic_id": "binary-search"},
    ]
    weak_topics = ["arrays", "hash-table"]

    # Scenario 1: Attempt 1 returns hallucinated ID; Attempt 2 corrects it with valid IDs
    calls = []

    def fake_llm_attempt_retry(prompt: str) -> str:
        calls.append(prompt)
        if len(calls) == 1:
            # First attempt: hallucinated ID not in catalog
            return json.dumps({
                "selected_ids": ["invented-leetcode-slug-999", "p-1", "p-3"],
                "rationale": "I invented a new problem for you.",
            })
        else:
            # Retry attempt: returns valid catalog IDs
            return json.dumps({
                "selected_ids": ["p-1", "p-2", "p-3"],
                "rationale": "Strengthens hash table and array manipulation.",
            })

    problems, rationale = select_coding_problems(
        weak_topics=weak_topics,
        problems=catalog,
        limit=3,
        llm_caller=fake_llm_attempt_retry,
    )

    assert len(calls) == 2, "LLM should have been retried exactly once"
    assert len(problems) == 3
    selected_ids = [p["id"] for p in problems]
    assert "invented-leetcode-slug-999" not in selected_ids
    assert selected_ids == ["p-1", "p-2", "p-3"]
    assert "Strengthens hash table" in rationale

    # Scenario 2: Both attempts return invalid IDs -> must fall back safely to catalog, NEVER assigning invalid IDs
    calls_2 = []

    def fake_llm_always_invalid(prompt: str) -> str:
        calls_2.append(prompt)
        return json.dumps({
            "selected_ids": ["fake-1", "fake-2", "fake-3"],
            "rationale": "Hallucinated problems.",
        })

    fallback_problems, fallback_rationale = select_coding_problems(
        weak_topics=weak_topics,
        problems=catalog,
        limit=3,
        llm_caller=fake_llm_always_invalid,
    )

    assert len(calls_2) == 2, "Must retry once before falling back"
    assert len(fallback_problems) == 3
    valid_catalog_ids = {p["id"] for p in catalog}
    for p in fallback_problems:
        assert p["id"] in valid_catalog_ids
        assert p["id"] not in {"fake-1", "fake-2", "fake-3"}
    assert fallback_rationale != ""


