from __future__ import annotations

from datetime import datetime
from typing import Any

from supabase import Client, create_client

from app.shared.schemas import SkillState


class SupabaseSkillRepository:
    def __init__(self, client: Client) -> None:
        self.client = client
        # In-memory cache keyed by (user_id, topic_id) for graceful fallback
        self._cache: dict[tuple[str, str], SkillState] = {}

    def get_for_user(self, user_id: str) -> dict[str, SkillState]:
        try:
            rows = self.client.table("skill_states").select("*").eq("user_id", user_id).execute().data
            remote = {row["topic_id"]: SkillState.model_validate(row) for row in rows}
        except Exception:
            remote = {}
        # Merge: remote is source of truth, but supplement with local cache entries
        # not yet persisted (e.g., when Supabase failed during upsert)
        local = {tid: state for (uid, tid), state in self._cache.items() if uid == user_id}
        return {**local, **remote}

    def upsert(self, user_id: str, state: SkillState) -> SkillState:
        # Always update local cache first
        self._cache[(user_id, state.topic_id)] = state
        row = {
            "user_id": user_id,
            "topic_id": state.topic_id,
            "mastery": state.mastery,
            "confidence": state.confidence,
            "updated_at": state.updated_at.isoformat() if state.updated_at else None,
        }
        try:
            saved = self.client.table("skill_states").upsert(row, on_conflict="user_id,topic_id").execute().data
            return SkillState.model_validate(saved[0] if saved else row)
        except Exception:
            return state  # Return the local state as fallback


class SupabaseEventRepository:
    def __init__(self, client: Client) -> None:
        self.client = client

    def record(
        self,
        user_id: str,
        type_: str,
        payload: dict[str, Any],
        created_at: datetime | None = None,
    ) -> dict[str, Any]:
        row = {"user_id": user_id, "type": type_, "payload": payload}
        if created_at is not None:
            row["created_at"] = created_at.isoformat()
        try:
            saved = self.client.table("events").insert(row).execute().data
            return saved[0] if saved else row
        except Exception:
            return row  # Gracefully degrade — return the row dict in-memory


class SupabaseAttemptRepository:
    def __init__(self, client: Client) -> None:
        self.client = client

    def create(self, user_id: str, attempt: dict[str, Any]) -> dict[str, Any]:
        row = {
            "user_id": user_id,
            "question_id": attempt["question_id"],
            "correct": attempt["correct"],
            "time_taken_s": attempt.get("time_taken_s"),
        }
        try:
            saved = self.client.table("attempts").insert(row).execute().data
            return saved[0] if saved else row
        except Exception:
            return row  # Gracefully degrade to in-memory


def create_supabase_repositories(url: str, service_role_key: str):
    client = create_client(url, service_role_key)
    return (
        SupabaseSkillRepository(client),
        SupabaseEventRepository(client),
        SupabaseAttemptRepository(client),
    )