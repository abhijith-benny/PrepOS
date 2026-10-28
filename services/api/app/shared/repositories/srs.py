from __future__ import annotations

import math
from datetime import datetime, time, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.shared.repositories.retry import retry_supabase

try:
    from supabase import Client, create_client
except ImportError:  # pragma: no cover
    Client = Any
    create_client = None


def _to_iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


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


class InMemorySRSRepository:
    def __init__(self) -> None:
        self.cards: dict[str, dict[str, Any]] = {}  # id -> card
        self.reviews: list[dict[str, Any]] = []

    def get_card(self, user_id: str, card_id: str) -> dict[str, Any] | None:
        card = self.cards.get(card_id)
        if card and card.get("user_id") == user_id:
            return dict(card)
        return None

    def get_card_by_question(self, user_id: str, question_id: str) -> dict[str, Any] | None:
        for card in self.cards.values():
            if card.get("user_id") == user_id and str(card.get("question_id")) == str(question_id):
                return dict(card)
        return None

    def list_cards(self, user_id: str, state: str | None = None) -> list[dict[str, Any]]:
        results = [
            dict(c) for c in self.cards.values()
            if c.get("user_id") == user_id and (state is None or c.get("state") == state)
        ]
        results.sort(key=lambda c: str(c.get("created_at")), reverse=True)
        return results

    def create_card(self, card_data: dict[str, Any]) -> dict[str, Any]:
        user_id = card_data["user_id"]
        question_id = card_data["question_id"]
        existing = self.get_card_by_question(user_id, question_id)
        if existing:
            return existing

        card_id = card_data.get("id") or str(uuid4())
        created_at = card_data.get("created_at") or datetime.now(timezone.utc).isoformat()
        due_at = card_data.get("due_at") or created_at
        row = {
            "id": card_id,
            "user_id": user_id,
            "question_id": question_id,
            "topic_id": card_data["topic_id"],
            "origin": card_data.get("origin", "diagnostic"),
            "state": card_data.get("state", "learning"),
            "ease": card_data.get("ease", 2.5),
            "interval_days": card_data.get("interval_days", 0),
            "repetitions": card_data.get("repetitions", 0),
            "lapses": card_data.get("lapses", 0),
            "due_at": due_at,
            "last_review_at": card_data.get("last_review_at"),
            "fsrs_state": card_data.get("fsrs_state"),
            "created_at": created_at,
        }
        self.cards[card_id] = row
        return dict(row)

    def update_card(self, user_id: str, card_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        card = self.cards.get(card_id)
        if not card or card.get("user_id") != user_id:
            return None
        for k, v in updates.items():
            if k != "id" and k != "user_id":
                card[k] = v
        return dict(card)

    def get_due_cards(
        self,
        user_id: str,
        now: datetime,
        limit: int = 20,
        new_card_limit: int = 10,
    ) -> list[dict[str, Any]]:
        # Count new cards reviewed today
        start_of_today = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
        today_reviews = [
            r for r in self.reviews
            if r.get("user_id") == user_id and (_parse_dt(r.get("reviewed_at")) or now) >= start_of_today
        ]
        # Cards that had their FIRST review today
        reviewed_card_ids = {r["card_id"] for r in today_reviews}
        new_cards_reviewed_today = 0
        for cid in reviewed_card_ids:
            card_revs = [r for r in self.reviews if r["card_id"] == cid]
            if len(card_revs) == 1:
                new_cards_reviewed_today += 1

        remaining_new = max(0, new_card_limit - new_cards_reviewed_today)

        user_cards = [c for c in self.cards.values() if c.get("user_id") == user_id]

        # 1. Due review cards: last_review_at is not None and due_at <= now
        due_review_cards = []
        # 2. New cards: last_review_at is None
        new_cards = []

        for c in user_cards:
            if c.get("last_review_at") is None:
                new_cards.append(c)
            else:
                due_dt = _parse_dt(c.get("due_at"))
                if due_dt and due_dt <= now:
                    due_review_cards.append(c)

        due_review_cards.sort(key=lambda c: str(c.get("due_at")))
        new_cards.sort(key=lambda c: str(c.get("created_at")))

        selected = list(due_review_cards)
        if len(selected) < limit and remaining_new > 0:
            take_new = min(limit - len(selected), remaining_new, len(new_cards))
            selected.extend(new_cards[:take_new])

        return [dict(c) for c in selected[:limit]]

    def record_review(self, review_data: dict[str, Any]) -> dict[str, Any]:
        review_id = review_data.get("id") or str(uuid4())
        row = {
            "id": review_id,
            "card_id": review_data["card_id"],
            "user_id": review_data["user_id"],
            "rating": review_data["rating"],
            "correct": review_data["correct"],
            "time_taken_s": review_data["time_taken_s"],
            "scheduled_days": review_data["scheduled_days"],
            "elapsed_days": review_data["elapsed_days"],
            "reviewed_at": review_data.get("reviewed_at") or datetime.now(timezone.utc).isoformat(),
        }
        self.reviews.append(row)
        return dict(row)

    def get_stats(self, user_id: str, now: datetime) -> dict[str, Any]:
        start_of_today = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
        end_of_today = datetime.combine(now.date(), time.max, tzinfo=timezone.utc)

        user_cards = [c for c in self.cards.values() if c.get("user_id") == user_id]
        user_reviews = [r for r in self.reviews if r.get("user_id") == user_id]

        # Due today: due_at <= end_of_today (including new cards)
        due_today = 0
        forecast = [0] * 7
        retention_sum = 0.0
        active_count = 0

        for c in user_cards:
            due_dt = _parse_dt(c.get("due_at"))
            if c.get("last_review_at") is None:
                due_today += 1
            elif due_dt and due_dt <= end_of_today:
                due_today += 1

            if due_dt:
                # 7-day forecast (day 0 = today, day 1 = tomorrow, ..., day 6)
                diff_days = (due_dt.date() - now.date()).days
                if 0 <= diff_days < 7:
                    forecast[diff_days] += 1
                elif diff_days < 0:
                    forecast[0] += 1

            # Estimate retention
            if c.get("last_review_at"):
                active_count += 1
                last_dt = _parse_dt(c.get("last_review_at")) or now
                elapsed_days = max(0.0, (now - last_dt).total_seconds() / 86400.0)
                interval = max(1, c.get("interval_days", 1))
                # Exponential recall estimate: R = 0.9 ** (elapsed / interval)
                retention = math.pow(0.9, elapsed_days / float(interval))
                retention_sum += max(0.0, min(1.0, retention))

        reviewed_today = sum(
            1 for r in user_reviews
            if (_parse_dt(r.get("reviewed_at")) or now) >= start_of_today
        )

        # Streak calculation: count consecutive days backwards with at least one review
        dates_with_reviews = {
            (_parse_dt(r.get("reviewed_at")) or now).date()
            for r in user_reviews
        }
        streak = 0
        check_date = now.date()
        # If no review today, check if yesterday had one to maintain streak
        if check_date not in dates_with_reviews:
            check_date -= timedelta(days=1)
        while check_date in dates_with_reviews:
            streak += 1
            check_date -= timedelta(days=1)

        retention_est = (retention_sum / active_count) if active_count > 0 else 1.0

        return {
            "due_today": due_today,
            "reviewed_today": reviewed_today,
            "total_cards": len(user_cards),
            "forecast": forecast,
            "retention_estimate": round(retention_est, 3),
            "streak_days": streak,
        }


class SupabaseSRSRepository:
    def __init__(self, client: Client) -> None:
        self.client = client
        self._fallback_memory = InMemorySRSRepository()

    def _is_table_missing(self, error: Exception) -> bool:
        err_msg = str(error)
        return "PGRST205" in err_msg or "Could not find the table" in err_msg or "relation" in err_msg

    def get_card(self, user_id: str, card_id: str) -> dict[str, Any] | None:
        try:
            rows = retry_supabase(
                lambda: self.client.table("cards")
                .select("*")
                .eq("id", card_id)
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            ).data
            return rows[0] if rows else None
        except Exception as e:
            if self._is_table_missing(e):
                return self._fallback_memory.get_card(user_id, card_id)
            raise

    def get_card_by_question(self, user_id: str, question_id: str) -> dict[str, Any] | None:
        try:
            rows = retry_supabase(
                lambda: self.client.table("cards")
                .select("*")
                .eq("user_id", user_id)
                .eq("question_id", question_id)
                .limit(1)
                .execute()
            ).data
            return rows[0] if rows else None
        except Exception as e:
            if self._is_table_missing(e):
                return self._fallback_memory.get_card_by_question(user_id, question_id)
            raise

    def list_cards(self, user_id: str, state: str | None = None) -> list[dict[str, Any]]:
        try:
            query = self.client.table("cards").select("*").eq("user_id", user_id)
            if state:
                query = query.eq("state", state)
            rows = retry_supabase(lambda: query.order("created_at", desc=True).execute()).data
            return rows or []
        except Exception as e:
            if self._is_table_missing(e):
                return self._fallback_memory.list_cards(user_id, state)
            raise

    def create_card(self, card_data: dict[str, Any]) -> dict[str, Any]:
        user_id = card_data["user_id"]
        question_id = card_data["question_id"]
        try:
            existing = self.get_card_by_question(user_id, question_id)
            if existing:
                return existing

            row = {
                "user_id": user_id,
                "question_id": question_id,
                "topic_id": card_data["topic_id"],
                "origin": card_data.get("origin", "diagnostic"),
                "state": card_data.get("state", "learning"),
                "ease": card_data.get("ease", 2.5),
                "interval_days": card_data.get("interval_days", 0),
                "repetitions": card_data.get("repetitions", 0),
                "lapses": card_data.get("lapses", 0),
                "due_at": card_data.get("due_at") or datetime.now(timezone.utc).isoformat(),
                "last_review_at": card_data.get("last_review_at"),
                "fsrs_state": card_data.get("fsrs_state"),
            }
            if card_data.get("id"):
                row["id"] = card_data["id"]

            saved = retry_supabase(lambda: self.client.table("cards").insert(row).execute()).data
            return saved[0] if saved else row
        except Exception as e:
            if self._is_table_missing(e):
                return self._fallback_memory.create_card(card_data)
            raise

    def update_card(self, user_id: str, card_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        try:
            clean_updates = {k: v for k, v in updates.items() if k not in ("id", "user_id")}
            rows = retry_supabase(
                lambda: self.client.table("cards")
                .update(clean_updates)
                .eq("id", card_id)
                .eq("user_id", user_id)
                .execute()
            ).data
            return rows[0] if rows else None
        except Exception as e:
            if self._is_table_missing(e):
                return self._fallback_memory.update_card(user_id, card_id, updates)
            raise

    def get_due_cards(
        self,
        user_id: str,
        now: datetime,
        limit: int = 20,
        new_card_limit: int = 10,
    ) -> list[dict[str, Any]]:
        try:
            # Query cards for user
            rows = retry_supabase(
                lambda: self.client.table("cards").select("*").eq("user_id", user_id).execute()
            ).data or []

            # Use identical logic for selection
            due_review_cards = []
            new_cards = []
            for c in rows:
                if c.get("last_review_at") is None:
                    new_cards.append(c)
                else:
                    due_dt = _parse_dt(c.get("due_at"))
                    if due_dt and due_dt <= now:
                        due_review_cards.append(c)

            due_review_cards.sort(key=lambda c: str(c.get("due_at")))
            new_cards.sort(key=lambda c: str(c.get("created_at")))

            # Check new cards reviewed today
            start_of_today = datetime.combine(now.date(), time.min, tzinfo=timezone.utc).isoformat()
            rev_rows = retry_supabase(
                lambda: self.client.table("reviews")
                .select("card_id,reviewed_at")
                .eq("user_id", user_id)
                .gte("reviewed_at", start_of_today)
                .execute()
            ).data or []
            reviewed_cids = {r["card_id"] for r in rev_rows}
            new_cards_reviewed_today = len(reviewed_cids)  # conservative estimate
            remaining_new = max(0, new_card_limit - new_cards_reviewed_today)

            selected = list(due_review_cards)
            if len(selected) < limit and remaining_new > 0:
                take_new = min(limit - len(selected), remaining_new, len(new_cards))
                selected.extend(new_cards[:take_new])

            return selected[:limit]
        except Exception as e:
            if self._is_table_missing(e):
                return self._fallback_memory.get_due_cards(user_id, now, limit, new_card_limit)
            raise

    def record_review(self, review_data: dict[str, Any]) -> dict[str, Any]:
        try:
            row = {
                "card_id": review_data["card_id"],
                "user_id": review_data["user_id"],
                "rating": review_data["rating"],
                "correct": review_data["correct"],
                "time_taken_s": review_data["time_taken_s"],
                "scheduled_days": review_data["scheduled_days"],
                "elapsed_days": review_data["elapsed_days"],
                "reviewed_at": review_data.get("reviewed_at") or datetime.now(timezone.utc).isoformat(),
            }
            if review_data.get("id"):
                row["id"] = review_data["id"]
            saved = retry_supabase(lambda: self.client.table("reviews").insert(row).execute()).data
            return saved[0] if saved else row
        except Exception as e:
            if self._is_table_missing(e):
                return self._fallback_memory.record_review(review_data)
            raise

    def get_stats(self, user_id: str, now: datetime) -> dict[str, Any]:
        try:
            rows = retry_supabase(
                lambda: self.client.table("cards").select("*").eq("user_id", user_id).execute()
            ).data or []

            start_of_today = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
            end_of_today = datetime.combine(now.date(), time.max, tzinfo=timezone.utc)

            due_today = 0
            forecast = [0] * 7
            retention_sum = 0.0
            active_count = 0

            for c in rows:
                due_dt = _parse_dt(c.get("due_at"))
                if c.get("last_review_at") is None:
                    due_today += 1
                elif due_dt and due_dt <= end_of_today:
                    due_today += 1

                if due_dt:
                    diff_days = (due_dt.date() - now.date()).days
                    if 0 <= diff_days < 7:
                        forecast[diff_days] += 1
                    elif diff_days < 0:
                        forecast[0] += 1

                if c.get("last_review_at"):
                    active_count += 1
                    last_dt = _parse_dt(c.get("last_review_at")) or now
                    elapsed_days = max(0.0, (now - last_dt).total_seconds() / 86400.0)
                    interval = max(1, c.get("interval_days", 1))
                    retention = math.pow(0.9, elapsed_days / float(interval))
                    retention_sum += max(0.0, min(1.0, retention))

            rev_rows = retry_supabase(
                lambda: self.client.table("reviews")
                .select("reviewed_at")
                .eq("user_id", user_id)
                .gte("reviewed_at", start_of_today.isoformat())
                .execute()
            ).data or []

            reviewed_today = len(rev_rows)
            retention_est = (retention_sum / active_count) if active_count > 0 else 1.0

            # Streak query
            all_revs = retry_supabase(
                lambda: self.client.table("reviews")
                .select("reviewed_at")
                .eq("user_id", user_id)
                .order("reviewed_at", desc=True)
                .limit(200)
                .execute()
            ).data or []

            dates_with_reviews = {
                (_parse_dt(r.get("reviewed_at")) or now).date()
                for r in all_revs
            }
            streak = 0
            check_date = now.date()
            if check_date not in dates_with_reviews:
                check_date -= timedelta(days=1)
            while check_date in dates_with_reviews:
                streak += 1
                check_date -= timedelta(days=1)

            return {
                "due_today": due_today,
                "reviewed_today": reviewed_today,
                "total_cards": len(rows),
                "forecast": forecast,
                "retention_estimate": round(retention_est, 3),
                "streak_days": streak,
            }
        except Exception as e:
            if self._is_table_missing(e):
                return self._fallback_memory.get_stats(user_id, now)
            raise


def create_srs_repository(url: str, key: str) -> SupabaseSRSRepository:
    if create_client is None:  # pragma: no cover
        raise RuntimeError("supabase-py is not installed")
    client = create_client(url, key)
    return SupabaseSRSRepository(client)
