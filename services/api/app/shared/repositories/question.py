from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.shared.repositories.retry import retry_supabase

try:
    from supabase import Client, create_client
except ImportError:  # pragma: no cover
    Client = Any
    create_client = None


class InMemoryQuestionRepository:
    def __init__(self, initial_questions: list[dict[str, Any]] | None = None) -> None:
        self.questions: list[dict[str, Any]] = initial_questions or []
        if not self.questions:
            # Provide sample questions across topics for unit testing
            for i in range(1, 21):
                self.questions.append({
                    "id": f"q-{i}",
                    "topic_id": f"topic-{(i % 5) + 1}",
                    "difficulty": 1 + (i % 3),
                    "type": "mcq",
                    "body": f"Sample question body {i}",
                    "options": ["A", "B", "C", "D"],
                    "answer": "A",
                    "explanation": f"Explanation for question {i}",
                })

    def get(self, question_id: str) -> dict[str, Any] | None:
        return next((q for q in self.questions if str(q.get("id")) == str(question_id)), None)

    def list_for_topics(
        self,
        topic_ids: list[str],
        limit: int = 10,
        exclude_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        exclude_set = {str(qid) for qid in (exclude_ids or [])}
        matched = [
            q for q in self.questions
            if str(q.get("topic_id")) in topic_ids and str(q.get("id")) not in exclude_set
        ]
        return matched[:limit]


class SupabaseQuestionRepository:
    def __init__(self, client: Client) -> None:
        self.client = client

    def get(self, question_id: str) -> dict[str, Any] | None:
        rows = retry_supabase(
            lambda: self.client.table("questions").select("*").eq("id", question_id).limit(1).execute()
        ).data
        return rows[0] if rows else None

    def list_for_topics(
        self,
        topic_ids: list[str],
        limit: int = 10,
        exclude_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if not topic_ids:
            return []
        exclude_set = {str(qid) for qid in (exclude_ids or [])}
        # Fetch questions in the topics
        query = self.client.table("questions").select("*").in_("topic_id", topic_ids)
        rows = retry_supabase(lambda: query.limit(limit + len(exclude_set) + 10).execute()).data or []
        filtered = [r for r in rows if str(r.get("id")) not in exclude_set]
        return filtered[:limit]


def create_question_repository(url: str, key: str) -> SupabaseQuestionRepository:
    if create_client is None:  # pragma: no cover
        raise RuntimeError("supabase-py is not installed")
    client = create_client(url, key)
    return SupabaseQuestionRepository(client)
