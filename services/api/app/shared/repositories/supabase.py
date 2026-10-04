from __future__ import annotations

from datetime import datetime
from typing import Any

from supabase import Client, create_client

from app.shared.schemas import SkillState
from app.shared.repositories.retry import retry_supabase


class SupabaseSkillRepository:
    def __init__(self, client: Client) -> None:
        self.client = client

    def get_for_user(self, user_id: str) -> dict[str, SkillState]:
        rows = retry_supabase(lambda: self.client.table("skill_states").select("*").eq("user_id", user_id).execute()).data
        return {row["topic_id"]: SkillState.model_validate(row) for row in rows}

    def upsert(self, user_id: str, state: SkillState) -> SkillState:
        row = {
            "user_id": user_id,
            "topic_id": state.topic_id,
            "mastery": state.mastery,
            "confidence": state.confidence,
            "updated_at": state.updated_at.isoformat() if state.updated_at else None,
        }
        saved = retry_supabase(lambda: self.client.table("skill_states").upsert(row, on_conflict="user_id,topic_id").execute()).data
        return SkillState.model_validate(saved[0] if saved else row)


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
        saved = retry_supabase(lambda: self.client.table("events").insert(row).execute()).data
        return saved[0] if saved else row


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
        saved = retry_supabase(lambda: self.client.table("attempts").insert(row).execute()).data
        return saved[0] if saved else row


def create_supabase_repositories(url: str, service_role_key: str):
    client = create_client(url, service_role_key)
    return (
        SupabaseSkillRepository(client),
        SupabaseEventRepository(client),
        SupabaseAttemptRepository(client),
    )