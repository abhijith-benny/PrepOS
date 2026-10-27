from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from supabase import Client, create_client

from app.shared.repositories.retry import retry_supabase


class InMemoryCodingRepository:
    def __init__(self) -> None:
        self.problems = [{"id": f"problem-{i}", "leetcode_slug": slug, "title": title, "difficulty": difficulty, "topic_id": "topic-1", "added_by_admin": True} for i, (slug, title, difficulty) in enumerate([
            ("two-sum", "Two Sum", "Easy"), ("valid-parentheses", "Valid Parentheses", "Easy"), ("binary-tree-inorder-traversal", "Binary Tree Inorder Traversal", "Easy")
        ])]
        self.assignments: dict[str, list[dict[str, Any]]] = {}

    def choose(self, user_id: str, weak_topic_ids: list[str]) -> dict[str, Any]:
        assigned = {item["problem_id"] for item in self.assignments.get(user_id, [])}
        problem = next((item for item in self.problems if item["id"] not in assigned and (not weak_topic_ids or item["topic_id"] in weak_topic_ids)), None) or next(item for item in self.problems if item["id"] not in assigned)
        assignment = {"id": str(uuid4()), "user_id": user_id, "problem_id": problem["id"], "assigned_at": datetime.now(timezone.utc).isoformat(), "status": "pending", "verified_at": None, "problem": problem}
        self.assignments.setdefault(user_id, []).append(assignment)
        return assignment

    def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        return list(self.assignments.get(user_id, []))

    def get(self, user_id: str, assignment_id: str) -> dict[str, Any] | None:
        return next((item for item in self.assignments.get(user_id, []) if item["id"] == assignment_id), None)

    def update(self, user_id: str, assignment_id: str, status: str) -> dict[str, Any] | None:
        item = self.get(user_id, assignment_id)
        if item:
            item["status"] = status
            item["verified_at"] = datetime.now(timezone.utc).isoformat() if status == "verified" else None
        return item


class SupabaseCodingRepository:
    def __init__(self, client: Client) -> None:
        self.client = client

    def choose(self, user_id: str, weak_topic_ids: list[str]) -> dict[str, Any]:
        query = self.client.table("coding_problems").select("*")
        if weak_topic_ids:
            query = query.in_("topic_id", weak_topic_ids)
        problems = retry_supabase(lambda: query.limit(20).execute()).data
        if not problems:
            problems = retry_supabase(lambda: self.client.table("coding_problems").select("*").limit(20).execute()).data
        assigned = retry_supabase(lambda: self.client.table("coding_assignments").select("problem_id").eq("user_id", user_id).execute()).data
        used = {row["problem_id"] for row in assigned}
        problem = next((row for row in problems if row["id"] not in used), None)
        if not problem:
            raise ValueError("No unassigned coding problems are available")
        row = {"user_id": user_id, "problem_id": problem["id"], "status": "pending"}
        saved = retry_supabase(lambda: self.client.table("coding_assignments").insert(row).execute()).data[0]
        return {**saved, "problem": problem}

    def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        rows = retry_supabase(lambda: self.client.table("coding_assignments").select("*,coding_problems(*)").eq("user_id", user_id).order("assigned_at", desc=True).execute()).data
        return [{**row, "problem": row.pop("coding_problems", None)} for row in rows]

    def get(self, user_id: str, assignment_id: str) -> dict[str, Any] | None:
        rows = retry_supabase(lambda: self.client.table("coding_assignments").select("*,coding_problems(*)").eq("id", assignment_id).eq("user_id", user_id).limit(1).execute()).data
        if not rows:
            return None
        row = rows[0]
        row["problem"] = row.pop("coding_problems", None)
        return row

    def update(self, user_id: str, assignment_id: str, status: str) -> dict[str, Any] | None:
        rows = retry_supabase(lambda: self.client.table("coding_assignments").update({"status": status, "verified_at": datetime.now(timezone.utc).isoformat() if status == "verified" else None}).eq("id", assignment_id).eq("user_id", user_id).execute()).data
        return rows[0] if rows else None


def create_coding_repository(url: str, service_role_key: str):
    return SupabaseCodingRepository(create_client(url, service_role_key))
