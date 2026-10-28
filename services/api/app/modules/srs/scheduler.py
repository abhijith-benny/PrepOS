from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from app.core.config import settings

try:
    from fsrs import Card as FSRSCard, Rating as FSRSRating, Scheduler as PyFSRSScheduler
except ImportError:  # pragma: no cover
    FSRSCard = None
    FSRSRating = None
    PyFSRSScheduler = None


def _parse_dt(val: Any) -> datetime | None:
    if not val:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


class SpacedScheduler(Protocol):
    def next_state(
        self,
        card: dict[str, Any],
        quality: int,  # 0 to 5
        now: datetime,
    ) -> tuple[dict[str, Any], datetime]: ...


class SM2Scheduler:
    """SuperMemo-2 (SM-2) scheduling algorithm.
    - Ease floor 1.3, initial ease 2.5
    - Intervals: 1 day on rep 0, 6 days on rep 1, then interval * ease
    - Quality < 3 resets repetitions and counts a lapse
    """

    def __init__(self, ease_floor: float = 1.3) -> None:
        self.ease_floor = ease_floor

    def next_state(
        self,
        card: dict[str, Any],
        quality: int,
        now: datetime,
    ) -> tuple[dict[str, Any], datetime]:
        q = max(0, min(5, int(quality)))
        ease = float(card.get("ease") or 2.5)
        repetitions = int(card.get("repetitions") or 0)
        lapses = int(card.get("lapses") or 0)
        interval_days = int(card.get("interval_days") or 0)

        # Update ease factor
        new_ease = ease + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
        new_ease = max(self.ease_floor, round(new_ease, 4))

        if q < 3:
            new_repetitions = 0
            new_lapses = lapses + 1
            new_interval = 1
            new_state = "relearning" if card.get("last_review_at") else "learning"
        else:
            if repetitions == 0:
                new_interval = 1
            elif repetitions == 1:
                new_interval = 6
            else:
                new_interval = max(1, round(interval_days * new_ease))
            new_repetitions = repetitions + 1
            new_lapses = lapses
            new_state = "review"

        due_at = now + timedelta(days=new_interval)

        updated_card = dict(card)
        updated_card.update({
            "ease": new_ease,
            "interval_days": new_interval,
            "repetitions": new_repetitions,
            "lapses": new_lapses,
            "state": new_state,
            "due_at": due_at.isoformat(),
            "last_review_at": now.isoformat(),
        })
        return updated_card, due_at


class FSRSSchedulerAdapter:
    """Adapter for py-fsrs (fsrs==6.3.2) Spaced Repetition Scheduler.
    Maps 0-5 quality scale to FSRS Ratings inside the adapter:
      0, 1, 2 -> Rating.Again
      3       -> Rating.Hard
      4       -> Rating.Good
      5       -> Rating.Easy
    Updates explicit columns AND saves full FSRS state in `fsrs_state` jsonb.
    """

    def __init__(self, desired_retention: float = 0.9, enable_fuzzing: bool = False) -> None:
        if PyFSRSScheduler is None:  # pragma: no cover
            raise RuntimeError("py-fsrs is not installed. Install with `pip install fsrs`.")
        self.scheduler = PyFSRSScheduler(
            desired_retention=desired_retention,
            enable_fuzzing=enable_fuzzing,
        )

    def _quality_to_rating(self, quality: int) -> FSRSRating:
        if quality >= 5:
            return FSRSRating.Easy
        if quality == 4:
            return FSRSRating.Good
        if quality == 3:
            return FSRSRating.Hard
        return FSRSRating.Again

    def next_state(
        self,
        card: dict[str, Any],
        quality: int,
        now: datetime,
    ) -> tuple[dict[str, Any], datetime]:
        rating = self._quality_to_rating(quality)

        # Resume or initialize fsrs Card
        fsrs_state = card.get("fsrs_state")
        if fsrs_state and isinstance(fsrs_state, dict):
            try:
                fsrs_card = FSRSCard.from_dict(fsrs_state)
            except Exception:
                fsrs_card = FSRSCard()
        else:
            fsrs_card = FSRSCard()

        new_fsrs_card, _ = self.scheduler.review_card(
            card=fsrs_card,
            rating=rating,
            review_datetime=now,
        )

        due_at = new_fsrs_card.due
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=timezone.utc)

        interval_seconds = max(0.0, (due_at - now).total_seconds())
        interval_days = max(1, round(interval_seconds / 86400.0))

        repetitions = int(card.get("repetitions") or 0)
        lapses = int(card.get("lapses") or 0)

        if rating == FSRSRating.Again:
            new_repetitions = 0
            new_lapses = lapses + 1
            new_state = "relearning" if card.get("last_review_at") else "learning"
        else:
            new_repetitions = repetitions + 1
            new_lapses = lapses
            new_state = "review"

        updated_card = dict(card)
        updated_card.update({
            "interval_days": interval_days,
            "repetitions": new_repetitions,
            "lapses": new_lapses,
            "state": new_state,
            "due_at": due_at.isoformat(),
            "last_review_at": now.isoformat(),
            "fsrs_state": new_fsrs_card.to_dict(),
        })
        return updated_card, due_at

    def get_retrievability(self, card: dict[str, Any], now: datetime) -> float:
        fsrs_state = card.get("fsrs_state")
        if fsrs_state and isinstance(fsrs_state, dict):
            try:
                fsrs_card = FSRSCard.from_dict(fsrs_state)
                return float(self.scheduler.get_card_retrievability(fsrs_card, now))
            except Exception:
                pass
        return 1.0


class FixedIntervalScheduler:
    """Fixed-interval baseline scheduler (reviews every fixed number of days).
    Used solely for evaluation comparison.
    """

    def __init__(self, interval_days: int = 3) -> None:
        self.interval_days = interval_days

    def next_state(
        self,
        card: dict[str, Any],
        quality: int,
        now: datetime,
    ) -> tuple[dict[str, Any], datetime]:
        due_at = now + timedelta(days=self.interval_days)
        repetitions = int(card.get("repetitions") or 0) + 1
        updated_card = dict(card)
        updated_card.update({
            "interval_days": self.interval_days,
            "repetitions": repetitions,
            "state": "review",
            "due_at": due_at.isoformat(),
            "last_review_at": now.isoformat(),
        })
        return updated_card, due_at


def get_scheduler(algorithm_name: str | None = None) -> SpacedScheduler:
    algo = (algorithm_name or settings.srs_algorithm or "sm2").strip().lower()
    if algo == "fsrs":
        return FSRSSchedulerAdapter()
    if algo == "fixed":
        return FixedIntervalScheduler()
    return SM2Scheduler()
