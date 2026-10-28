from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.deps import get_current_user
from app.main import app
from app.modules.srs.generation import (
    create_initial_card,
    generate_cards_for_user,
    on_attempt_recorded,
    on_diagnostic_completed,
)
from app.modules.srs.grading import grade_review
from app.modules.srs.scheduler import (
    FixedIntervalScheduler,
    FSRSSchedulerAdapter,
    SM2Scheduler,
    get_scheduler,
)
from app.shared.events import AttemptRecorded, DiagnosticCompleted
from app.shared.learner_model import EVENT_BUS, get_skill_vector
from app.shared.repositories import (
    InMemoryQuestionRepository,
    InMemorySRSRepository,
    question_repository,
    srs_repository,
)


@pytest.fixture(autouse=True)
def reset_srs_state():
    """Reset repositories to fresh in-memory state for clean test isolation."""
    # Use fresh in-memory repos for unit/API tests
    global srs_repo, q_repo
    srs_repo = InMemorySRSRepository()
    q_repo = InMemoryQuestionRepository()

    with patch("app.modules.srs.router.srs_repository", srs_repo), \
         patch("app.modules.srs.router.question_repository", q_repo), \
         patch("app.modules.srs.generation.srs_repository", srs_repo), \
         patch("app.modules.srs.generation.question_repository", q_repo):
        yield


# ============================================================================
# 1. SCHEDULER UNIT TESTS
# ============================================================================

def test_sm2_scheduler_initial_and_growth():
    scheduler = SM2Scheduler(ease_floor=1.3)
    now = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)
    card = {
        "id": "c1",
        "user_id": "u1",
        "state": "learning",
        "ease": 2.5,
        "interval_days": 0,
        "repetitions": 0,
        "lapses": 0,
        "due_at": now.isoformat(),
        "last_review_at": None,
    }

    # Review 1: Quality 4 (Good) -> rep 0 becomes rep 1, interval 1 day
    card_1, due_1 = scheduler.next_state(card, quality=4, now=now)
    assert card_1["repetitions"] == 1
    assert card_1["interval_days"] == 1
    assert card_1["state"] == "review"
    assert due_1 == now + timedelta(days=1)
    assert card_1["lapses"] == 0

    # Review 2: Quality 4 (Good) -> rep 1 becomes rep 2, interval 6 days
    now_2 = now + timedelta(days=1)
    card_2, due_2 = scheduler.next_state(card_1, quality=4, now=now_2)
    assert card_2["repetitions"] == 2
    assert card_2["interval_days"] == 6
    assert due_2 == now_2 + timedelta(days=6)

    # Review 3: Quality 5 (Easy) -> rep 2 becomes rep 3, interval = round(6 * ease)
    now_3 = now_2 + timedelta(days=6)
    card_3, due_3 = scheduler.next_state(card_2, quality=5, now=now_3)
    assert card_3["repetitions"] == 3
    assert card_3["interval_days"] > 6
    assert card_3["ease"] >= card_2["ease"]


def test_sm2_scheduler_lapse_and_floor():
    scheduler = SM2Scheduler(ease_floor=1.3)
    now = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)
    card = {
        "id": "c1",
        "user_id": "u1",
        "state": "review",
        "ease": 1.35,
        "interval_days": 15,
        "repetitions": 4,
        "lapses": 1,
        "due_at": now.isoformat(),
        "last_review_at": (now - timedelta(days=15)).isoformat(),
    }

    # Quality < 3: Lapse occurs
    failed_card, due = scheduler.next_state(card, quality=1, now=now)
    assert failed_card["repetitions"] == 0
    assert failed_card["lapses"] == 2
    assert failed_card["interval_days"] == 1
    assert failed_card["state"] == "relearning"
    assert due == now + timedelta(days=1)
    # Ease should decrease but never below floor 1.3
    assert failed_card["ease"] >= 1.3


def test_fsrs_scheduler_adapter_and_json_roundtrip():
    adapter = FSRSSchedulerAdapter(desired_retention=0.9, enable_fuzzing=False)
    now = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)
    card = {
        "id": "c1",
        "user_id": "u1",
        "state": "learning",
        "ease": 2.5,
        "interval_days": 0,
        "repetitions": 0,
        "lapses": 0,
        "due_at": now.isoformat(),
        "last_review_at": None,
        "fsrs_state": None,
    }

    # Review 1: Quality 4 (Good)
    reviewed_card, due = adapter.next_state(card, quality=4, now=now)
    assert reviewed_card["state"] == "review"
    assert reviewed_card["fsrs_state"] is not None
    assert isinstance(reviewed_card["fsrs_state"], dict)
    assert "stability" in reviewed_card["fsrs_state"]
    assert "difficulty" in reviewed_card["fsrs_state"]

    # Test JSON serialization round-trip
    serialized = json.dumps(reviewed_card["fsrs_state"])
    deserialized = json.loads(serialized)
    reviewed_card["fsrs_state"] = deserialized

    # Review 2: Quality 5 (Easy) resuming from deserialized state
    now_2 = now + timedelta(days=1)
    reviewed_card_2, due_2 = adapter.next_state(reviewed_card, quality=5, now=now_2)
    assert reviewed_card_2["repetitions"] == 2
    assert due_2 > now_2

    # Retrievability check
    retrievability = adapter.get_retrievability(reviewed_card_2, now_2)
    assert 0.0 <= retrievability <= 1.0


def test_fixed_interval_scheduler():
    scheduler = FixedIntervalScheduler(interval_days=3)
    now = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)
    card = {"id": "c1", "user_id": "u1", "repetitions": 0}
    next_card, due = scheduler.next_state(card, quality=4, now=now)
    assert next_card["interval_days"] == 3
    assert due == now + timedelta(days=3)
    assert next_card["repetitions"] == 1


# ============================================================================
# 2. GRADING UNIT TESTS
# ============================================================================

def test_grading_scale():
    # Incorrect variations (0-2)
    assert grade_review(correct=False, time_taken_s=5, expected_time_s=60, confidence="blackout") == 0
    assert grade_review(correct=False, time_taken_s=10, expected_time_s=60) == 0  # < 0.3 * 60
    assert grade_review(correct=False, time_taken_s=40, expected_time_s=60) == 1  # standard incorrect
    assert grade_review(correct=False, time_taken_s=70, expected_time_s=60) == 2  # took long / effort

    # Correct variations (3-5)
    assert grade_review(correct=True, time_taken_s=90, expected_time_s=60) == 3  # slow (> 1.3 * 60)
    assert grade_review(correct=True, time_taken_s=30, expected_time_s=60, confidence="low") == 3  # hesitant
    assert grade_review(correct=True, time_taken_s=50, expected_time_s=60) == 4  # standard correct
    assert grade_review(correct=True, time_taken_s=25, expected_time_s=60, confidence="high") == 5  # fast & confident


# ============================================================================
# 3. CARD GENERATION & IDEMPOTENCY
# ============================================================================

def test_create_initial_card_idempotency():
    user_id = "user-123"
    q_id = "q-1"
    card1 = create_initial_card(user_id=user_id, question_id=q_id, topic_id="topic-1", origin="manual")
    card2 = create_initial_card(user_id=user_id, question_id=q_id, topic_id="topic-1", origin="manual")
    assert card1["id"] == card2["id"]
    assert card1["state"] == "learning"
    assert card1["repetitions"] == 0
    assert card1["last_review_at"] is None


def test_diagnostic_completed_event_creates_cards():
    user_id = "user-test-diag"
    event = DiagnosticCompleted(
        user_id=user_id,
        payload={
            "mastery": {"topic-1": 0.2, "topic-2": 0.8},
            "sections": [],
        },
    )
    cards = on_diagnostic_completed(event)
    assert len(cards) > 0
    assert all(c["user_id"] == user_id for c in cards)
    assert all(c["origin"] == "diagnostic" for c in cards)


def test_attempt_recorded_incorrect_creates_mistake_card():
    user_id = "user-test-mistake"
    event = AttemptRecorded(
        user_id=user_id,
        payload={
            "question_id": "q-5",
            "topic_id": "topic-1",
            "correct": False,
        },
    )
    card = on_attempt_recorded(event)
    assert card is not None
    assert card["origin"] == "mistake"
    assert card["user_id"] == user_id
    assert card["question_id"] == "q-5"


# ============================================================================
# 4. API INTEGRATION TESTS
# ============================================================================

def test_due_cards_unauthorized():
    client = TestClient(app)
    resp = client.get("/srs/due")
    assert resp.status_code == 401


def test_due_cards_does_not_leak_answers():
    client = TestClient(app)
    user_id = "user-due-leak-test"
    app.dependency_overrides[get_current_user] = lambda: {"id": user_id, "email": "test@example.com"}

    try:
        # Create a card
        create_initial_card(user_id=user_id, question_id="q-1", topic_id="topic-1", origin="manual")

        resp = client.get("/srs/due")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        card = data[0]
        q = card.get("question")
        assert q is not None
        assert "body" in q
        assert "options" in q
        # Ensure answer and explanation are NOT leaked!
        assert "answer" not in q
        assert "explanation" not in q
    finally:
        app.dependency_overrides.clear()


def test_review_card_other_user_returns_404():
    client = TestClient(app)
    owner_id = "user-owner"
    stranger_id = "user-stranger"

    card = create_initial_card(user_id=owner_id, question_id="q-2", topic_id="topic-1", origin="manual")

    # Access with stranger
    app.dependency_overrides[get_current_user] = lambda: {"id": stranger_id, "email": "stranger@example.com"}
    try:
        resp = client.post(
            f"/srs/cards/{card['id']}/review",
            json={"answer": "A", "time_taken_s": 25},
        )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_review_card_flow_and_learner_model_update():
    from uuid import uuid4
    client = TestClient(app)
    user_id = str(uuid4())
    app.dependency_overrides[get_current_user] = lambda: {"id": user_id, "email": "flow@example.com"}

    try:
        card = create_initial_card(user_id=user_id, question_id="q-1", topic_id="topic-1", origin="manual")

        # Submit correct answer ("A" for q-1)
        resp = client.post(
            f"/srs/cards/{card['id']}/review",
            json={"answer": "A", "time_taken_s": 25, "confidence": "high"},
        )
        assert resp.status_code == 200
        res = resp.json()
        assert res["correct"] is True
        assert res["quality"] == 5
        assert res["state"] == "review"
        assert res["repetitions"] == 1
        assert res["interval_days"] >= 1
        assert "explanation" in res

        # Verify stats endpoint
        stats_resp = client.get("/srs/stats")
        assert stats_resp.status_code == 200
        stats = stats_resp.json()
        assert stats["reviewed_today"] >= 1
        assert stats["total_cards"] >= 1
        assert len(stats["forecast"]) == 7

        # Verify learner model updated
        skill_vector = get_skill_vector(user_id)
        assert "topic-1" in skill_vector
        assert skill_vector["topic-1"].mastery > 0
    finally:
        app.dependency_overrides.clear()
