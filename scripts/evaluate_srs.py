"""FSRS sanity checks for PrepOS.

Put this file in services/api/tests/ and run from services/api:

    python -m pytest tests/test_fsrs_sanity.py -v -s

Part 1 tests the fsrs library itself (is the library behaving like FSRS?).
Part 2 tests YOUR adapter (does PrepOS use it correctly?).
Part 3 (run the file directly) prints a human-readable schedule so you can eyeball it:

    python tests/test_fsrs_sanity.py

Nothing here needs Supabase or a network connection.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fsrs import Card, Rating, Scheduler, State

UTC = timezone.utc
T0 = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


def new_scheduler(retention: float = 0.9) -> Scheduler:
    # Fuzzing off so results are deterministic.
    return Scheduler(desired_retention=retention, enable_fuzzing=False)


def review_chain(sched: Scheduler, ratings: list[Rating], start: datetime = T0):
    """Review a fresh card, always exactly when it is due. Returns [(review_time, card)]."""
    card = Card()
    now = start
    history = []
    for r in ratings:
        card, _ = sched.review_card(card, r, review_datetime=now)
        history.append((now, card))
        now = card.due
    return history


# --------------------------------------------------------------------------
# PART 1: the library behaves like FSRS
# --------------------------------------------------------------------------

def test_due_is_in_the_future_and_timezone_aware():
    s = new_scheduler()
    for r in Rating:
        card, _ = s.review_card(Card(), r, review_datetime=T0)
        assert card.due > T0, f"{r.name}: due must be after the review time"
        assert card.due.tzinfo is not None, "due must be timezone-aware (UTC)"


def test_better_rating_never_gives_an_earlier_due_date():
    s = new_scheduler()
    dues = {r: s.review_card(Card(), r, review_datetime=T0)[0].due for r in Rating}
    assert dues[Rating.Again] <= dues[Rating.Hard] <= dues[Rating.Good] <= dues[Rating.Easy]
    assert dues[Rating.Again] < dues[Rating.Easy]


def test_intervals_grow_when_you_keep_getting_it_right():
    s = new_scheduler()
    hist = review_chain(s, [Rating.Good] * 10)
    intervals = [card.due - when for when, card in hist]
    assert intervals[-1] > intervals[0]
    assert intervals[-1] >= timedelta(days=5), f"after 10 Good reviews expected >= 5 days, got {intervals[-1]}"
    # Allow small plateaus, but never a big collapse in a perfect streak.
    for earlier, later in zip(intervals[3:], intervals[4:]):
        assert later >= earlier * 0.9


def test_stability_increases_on_success_and_drops_on_failure():
    s = new_scheduler()
    hist = review_chain(s, [Rating.Good] * 8)
    stab = [card.stability for _, card in hist]
    assert stab[-1] > stab[0]

    when, last = hist[-1]
    failed, _ = s.review_card(last, Rating.Again, review_datetime=last.due)
    assert failed.stability < last.stability, "a lapse must lower stability"
    assert failed.state == State.Relearning, "failing a Review card must send it to Relearning"


def test_retrievability_decays_and_is_about_target_when_due():
    s = new_scheduler(0.9)
    hist = review_chain(s, [Rating.Good] * 8)
    when, card = hist[-1]
    r_now = s.get_card_retrievability(card, when)
    r_mid = s.get_card_retrievability(card, when + (card.due - when) / 2)
    r_due = s.get_card_retrievability(card, card.due)
    r_late = s.get_card_retrievability(card, card.due + timedelta(days=30))
    assert r_now >= 0.99
    assert r_now > r_mid > r_due > r_late
    assert 0.0 <= r_late <= 1.0
    assert 0.85 <= r_due <= 1.0, f"retrievability at the due date should be ~0.9, got {r_due:.3f}"


def test_higher_desired_retention_means_shorter_intervals():
    low = review_chain(new_scheduler(0.8), [Rating.Good] * 8)
    high = review_chain(new_scheduler(0.95), [Rating.Good] * 8)
    low_interval = low[-1][1].due - low[-1][0]
    high_interval = high[-1][1].due - high[-1][0]
    assert high_interval < low_interval


def test_is_deterministic_with_fuzzing_off():
    a = review_chain(new_scheduler(), [Rating.Good, Rating.Hard, Rating.Good, Rating.Easy])
    b = review_chain(new_scheduler(), [Rating.Good, Rating.Hard, Rating.Good, Rating.Easy])
    assert [c.due for _, c in a] == [c.due for _, c in b]


def test_card_survives_json_round_trip():
    s = new_scheduler()
    hist = review_chain(s, [Rating.Good, Rating.Good, Rating.Hard])
    card = hist[-1][1]
    restored = Card.from_json(card.to_json())
    assert restored.to_dict() == card.to_dict()
    # And it keeps scheduling identically after being stored and reloaded.
    nxt_a, _ = s.review_card(card, Rating.Good, review_datetime=card.due)
    nxt_b, _ = s.review_card(restored, Rating.Good, review_datetime=card.due)
    assert nxt_a.due == nxt_b.due


# --------------------------------------------------------------------------
# PART 2: YOUR adapter
# Adjust the import and the starting dict if your names differ.
# --------------------------------------------------------------------------

def _adapter():
    try:
        from app.modules.srs.scheduler import FSRSSchedulerAdapter
    except ImportError:
        pytest.skip("FSRSSchedulerAdapter not importable: adjust the import in this test file")
    return FSRSSchedulerAdapter()


def _blank_card() -> dict:
    return {
        "state": "learning", "ease": 2.5, "interval_days": 0, "repetitions": 0,
        "lapses": 0, "last_review_at": None, "fsrs_state": None, "due_at": T0.isoformat(),
    }


def test_adapter_returns_future_due_and_persists_state():
    ad = _adapter()
    card, due = ad.next_state(_blank_card(), 4, T0)
    assert due > T0
    assert card.get("fsrs_state"), "the FSRS state must be stored so the next review can use it"


def test_adapter_lapse_is_counted_and_failure_is_not_later_than_success():
    ad = _adapter()
    card = _blank_card()
    now = T0
    for _ in range(6):                       # build up a streak
        card, due = ad.next_state(card, 4, now)
        now = due
    before_lapses = card.get("lapses", 0)
    failed, failed_due = ad.next_state(dict(card), 1, now)
    passed, passed_due = ad.next_state(dict(card), 4, now)
    assert failed.get("lapses", 0) == before_lapses + 1
    assert failed_due <= passed_due


def test_adapter_quality_maps_monotonically():
    ad = _adapter()
    dues = [ad.next_state(_blank_card(), q, T0)[1] for q in (1, 3, 4, 5)]
    assert dues == sorted(dues), f"higher quality should never schedule sooner: {dues}"


def test_adapter_survives_a_json_round_trip_between_reviews():
    import json
    ad = _adapter()
    card, due = ad.next_state(_blank_card(), 4, T0)
    stored = json.loads(json.dumps(card, default=str))   # what the database would hand back
    card2, due2 = ad.next_state(stored, 4, due)
    assert due2 > due


# --------------------------------------------------------------------------
# PART 3: eyeball it
# --------------------------------------------------------------------------

def _demo():
    s = new_scheduler()
    plan = [
        ("Good", Rating.Good), ("Good", Rating.Good), ("Good", Rating.Good),
        ("Good", Rating.Good), ("Again (forgot)", Rating.Again), ("Good", Rating.Good),
        ("Good", Rating.Good), ("Easy", Rating.Easy),
    ]
    card, now = Card(), T0
    print(f"{'#':<3}{'answer':<16}{'state':<12}{'stability':>10}{'next review in':>20}")
    for i, (label, r) in enumerate(plan, 1):
        card, _ = s.review_card(card, r, review_datetime=now)
        gap = card.due - now
        print(f"{i:<3}{label:<16}{State(card.state).name:<12}{card.stability:>10.2f}{str(gap):>20}")
        now = card.due


if __name__ == "__main__":
    _demo()