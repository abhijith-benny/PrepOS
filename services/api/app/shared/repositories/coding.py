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

    def get_all_problems(self) -> list[dict[str, Any]]:
        return list(self.problems)

    def assign_problem(self, user_id: str, problem_id: str, rationale: str | None = None) -> dict[str, Any]:
        problem = next((item for item in self.problems if item["id"] == problem_id or item.get("leetcode_slug") == problem_id), None)
        if not problem and self.problems:
            problem = self.problems[0]
        actual_id = problem["id"] if problem else problem_id
        assignment = {
            "id": str(uuid4()),
            "user_id": user_id,
            "problem_id": actual_id,
            "assigned_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending",
            "verified_at": None,
            "problem": problem,
            "rationale": rationale,
        }
        self.assignments.setdefault(user_id, []).append(assignment)
        return assignment

    def choose(self, user_id: str, weak_topic_ids: list[str], rationale: str | None = None) -> dict[str, Any]:
        assigned = {item["problem_id"] for item in self.assignments.get(user_id, [])}
        problem = next((item for item in self.problems if item["id"] not in assigned and (weak_topic_ids and item["topic_id"] in weak_topic_ids)), None)
        if not problem:
            problem = next((item for item in self.problems if item["id"] not in assigned), None)
        if not problem:
            raise ValueError("No unassigned coding problems are available")
        return self.assign_problem(user_id, problem["id"], rationale=rationale)

    def suggest_problems(self, topic_ids: list[str], limit: int = 3) -> list[dict[str, Any]]:
        """Return up to *limit* problems for the given topic_ids without creating assignments."""
        if topic_ids:
            matched = [p for p in self.problems if p["topic_id"] in topic_ids]
        else:
            matched = list(self.problems)
        return matched[:limit]

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
        self._rationales: dict[str, str] = {}

    def get_all_problems(self) -> list[dict[str, Any]]:
        rows = retry_supabase(lambda: self.client.table("coding_problems").select("*").execute()).data
        return rows or []

    def assign_problem(self, user_id: str, problem_id: str, rationale: str | None = None) -> dict[str, Any]:
        prob_rows = retry_supabase(lambda: self.client.table("coding_problems").select("*").eq("id", problem_id).limit(1).execute()).data
        problem = prob_rows[0] if prob_rows else None
        row = {"user_id": user_id, "problem_id": problem_id, "status": "pending"}
        saved = retry_supabase(lambda: self.client.table("coding_assignments").insert(row).execute()).data[0]
        if rationale:
            self._rationales[saved["id"]] = rationale
        return {**saved, "problem": problem, "rationale": rationale}

    def choose(self, user_id: str, weak_topic_ids: list[str], rationale: str | None = None) -> dict[str, Any]:
        assigned = retry_supabase(lambda: self.client.table("coding_assignments").select("problem_id").eq("user_id", user_id).execute()).data
        used = {row["problem_id"] for row in assigned}

        problems = []
        if weak_topic_ids:
            query = self.client.table("coding_problems").select("*").in_("topic_id", weak_topic_ids)
            problems = retry_supabase(lambda: query.limit(50).execute()).data or []
        problem = next((row for row in problems if row["id"] not in used), None)
        if not problem:
            all_problems = retry_supabase(lambda: self.client.table("coding_problems").select("*").limit(100).execute()).data or []
            problem = next((row for row in all_problems if row["id"] not in used), None)
        if not problem:
            raise ValueError("No unassigned coding problems are available")
        return self.assign_problem(user_id, problem["id"], rationale=rationale)

    def suggest_problems(self, topic_ids: list[str], limit: int = 3) -> list[dict[str, Any]]:
        """Return up to *limit* problems for the given topic_ids without creating assignments."""
        query = self.client.table("coding_problems").select("*")
        if topic_ids:
            query = query.in_("topic_id", topic_ids)
        rows = retry_supabase(lambda: query.limit(limit).execute()).data
        if not rows and topic_ids:
            # fall back to any problems if none match the specific topics
            rows = retry_supabase(lambda: self.client.table("coding_problems").select("*").limit(limit).execute()).data
        return rows[:limit]

    def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        rows = retry_supabase(lambda: self.client.table("coding_assignments").select("*,coding_problems(*)").eq("user_id", user_id).order("assigned_at", desc=True).execute()).data
        return [
            {
                **row,
                "problem": row.pop("coding_problems", None),
                "rationale": self._rationales.get(row["id"]) or row.get("rationale"),
            }
            for row in rows
        ]

    def get(self, user_id: str, assignment_id: str) -> dict[str, Any] | None:
        rows = retry_supabase(lambda: self.client.table("coding_assignments").select("*,coding_problems(*)").eq("id", assignment_id).eq("user_id", user_id).limit(1).execute()).data
        if not rows:
            return None
        row = rows[0]
        row["problem"] = row.pop("coding_problems", None)
        row["rationale"] = self._rationales.get(row["id"]) or row.get("rationale")
        return row

    def update(self, user_id: str, assignment_id: str, status: str) -> dict[str, Any] | None:
        rows = retry_supabase(lambda: self.client.table("coding_assignments").update({"status": status, "verified_at": datetime.now(timezone.utc).isoformat() if status == "verified" else None}).eq("id", assignment_id).eq("user_id", user_id).execute()).data
        if rows:
            row = rows[0]
            row["rationale"] = self._rationales.get(assignment_id) or row.get("rationale")
            return row
        return None


def create_coding_repository(url: str, service_role_key: str):
    return SupabaseCodingRepository(create_client(url, service_role_key))
