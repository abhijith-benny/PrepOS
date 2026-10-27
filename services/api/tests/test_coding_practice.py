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


def test_assign_never_repeats_problem_id(monkeypatch) -> None:
    """Assign a problem, assign again, confirm second call never returns the same problem id as the first."""
    profile = InMemoryProfileRepository()
    repository = InMemoryCodingRepository()
    user_id = "test-no-repeat-user"
    profile.save(user_id, {"leetcode_username": "coder", "target_difficulty": "Easy"})
    monkeypatch.setattr(coding_router, "profile_repository", profile)
    monkeypatch.setattr(coding_router, "coding_repository", repository)

    app.dependency_overrides[get_current_user] = lambda: {"id": user_id, "email": "repeat@example.com"}
    try:
        client = TestClient(app)
        # Call 1
        res1 = client.post("/coding/assign")
        assert res1.status_code == 200, res1.text
        prob1_id = res1.json()["problem_id"]

        # Call 2
        res2 = client.post("/coding/assign")
        assert res2.status_code == 200, res2.text
        prob2_id = res2.json()["problem_id"]

        # Confirm second call never returns the same problem id
        assert prob1_id != prob2_id

        # Call 3
        res3 = client.post("/coding/assign")
        assert res3.status_code == 200, res3.text
        prob3_id = res3.json()["problem_id"]
        assert prob3_id not in (prob1_id, prob2_id)

        # Call 4 - bank exhausted (3 total problems in InMemoryCodingRepository)
        res4 = client.post("/coding/assign")
        assert res4.status_code == 422
        assert "No unassigned coding problems" in res4.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_assign_blocks_regardless_of_status(monkeypatch) -> None:
    """Confirm pending, verified, or failed_to_verify all block reassignment of that exact problem."""
    profile = InMemoryProfileRepository()
    repository = InMemoryCodingRepository()
    user_id = "status-user"
    profile.save(user_id, {"leetcode_username": "coder"})
    monkeypatch.setattr(coding_router, "profile_repository", profile)
    monkeypatch.setattr(coding_router, "coding_repository", repository)

    # Seed an assignment with 'failed_to_verify' and another with 'verified'
    repository.assign_problem(user_id, "problem-0")
    # update problem-0 to failed_to_verify
    assignments = repository.list_for_user(user_id)
    repository.update(user_id, assignments[0]["id"], "failed_to_verify")

    repository.assign_problem(user_id, "problem-1")
    assignments = repository.list_for_user(user_id)
    repository.update(user_id, assignments[1]["id"], "verified")

    app.dependency_overrides[get_current_user] = lambda: {"id": user_id, "email": "status@example.com"}
    try:
        client = TestClient(app)
        res = client.post("/coding/assign")
        assert res.status_code == 200
        # Must pick problem-2, NOT problem-0 or problem-1
        assert res.json()["problem_id"] == "problem-2"
    finally:
        app.dependency_overrides.clear()


def test_assign_fallback_when_weak_topics_exhausted(monkeypatch) -> None:
    """When all eligible problems for weak topics are assigned, fall back to next-weakest topic's problems and notify user."""
    profile = InMemoryProfileRepository()
    repository = InMemoryCodingRepository()
    # Configure 4 problems: 2 in topic-weak, 2 in topic-next
    repository.problems = [
        {"id": "prob-w1", "leetcode_slug": "w1", "title": "Weak 1", "difficulty": "Easy", "topic_id": "topic-weak"},
        {"id": "prob-w2", "leetcode_slug": "w2", "title": "Weak 2", "difficulty": "Easy", "topic_id": "topic-weak"},
        {"id": "prob-n1", "leetcode_slug": "n1", "title": "Next 1", "difficulty": "Easy", "topic_id": "topic-next"},
        {"id": "prob-n2", "leetcode_slug": "n2", "title": "Next 2", "difficulty": "Easy", "topic_id": "topic-next"},
    ]
    user_id = "fallback-user"
    profile.save(user_id, {"leetcode_username": "coder"})
    monkeypatch.setattr(coding_router, "profile_repository", profile)
    monkeypatch.setattr(coding_router, "coding_repository", repository)
    monkeypatch.setattr(coding_router, "get_user_weak_topics", lambda uid: ["topic-weak", "topic-next"])

    app.dependency_overrides[get_current_user] = lambda: {"id": user_id, "email": "fallback@example.com"}
    try:
        client = TestClient(app)
        # 1st assign -> weak topic
        res1 = client.post("/coding/assign")
        assert res1.status_code == 200
        assert res1.json()["problem_id"] in ("prob-w1", "prob-w2")
        assert "user_message" not in res1.json()

        # 2nd assign -> second weak topic problem
        res2 = client.post("/coding/assign")
        assert res2.status_code == 200
        assert res2.json()["problem_id"] in ("prob-w1", "prob-w2")
        assert res2.json()["problem_id"] != res1.json()["problem_id"]

        # 3rd assign -> all weak topic problems assigned! Must fall back to topic-next with explicit user message
        res3 = client.post("/coding/assign")
        assert res3.status_code == 200
        assert res3.json()["problem_id"] in ("prob-n1", "prob-n2")
        expected_msg = "You've been assigned all available problems for your top weak areas — showing problems for your next focus area"
        assert res3.json().get("user_message") == expected_msg
        assert res3.json().get("message") == expected_msg
    finally:
        app.dependency_overrides.clear()


