from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from supabase import Client, create_client


DEFAULT_TOPICS = [
    {"id": f"topic-{index}", "name": f"Topic {index}", "category": category}
    for index, category in enumerate(
        ["DSA"] * 5 + ["aptitude"] * 5 + ["CS core"] * 5 + ["system design"] * 5 + ["behavioral"] * 5,
        start=1,
    )
]


class InMemoryTopicRepository:
    def __init__(self) -> None:
        self.topics = [dict(topic) for topic in DEFAULT_TOPICS]

    def list_topics(self) -> list[dict[str, Any]]:
        return [dict(topic) for topic in self.topics]


class InMemoryProfileRepository:
    def __init__(self) -> None:
        self.profiles: dict[str, dict[str, Any]] = {}

    def get(self, user_id: str) -> dict[str, Any]:
        return dict(self.profiles.get(user_id, {}))


class InMemoryStudyPlanRepository:
    def __init__(self) -> None:
        self.plans: dict[str, dict[str, dict[str, Any]]] = {}

    def create(self, plan: dict[str, Any]) -> dict[str, Any]:
        self.plans.setdefault(plan["user_id"], {})[plan["id"]] = plan
        return plan

    def archive(self, user_id: str, plan_id: str) -> None:
        plan = self.get(user_id, plan_id)
        if plan:
            plan["status"] = "archived"

    def current(self, user_id: str, week_start: date) -> dict[str, Any] | None:
        plans = [
            plan for plan in self.plans.get(user_id, {}).values()
            if plan["week_start_date"] == week_start.isoformat() and plan["status"] == "active"
        ]
        return max(plans, key=lambda plan: plan["generated_at"]) if plans else None

    def get(self, user_id: str, plan_id: str) -> dict[str, Any] | None:
        plan = self.plans.get(user_id, {}).get(plan_id)
        return plan if plan and plan["user_id"] == user_id else None

    def history(self, user_id: str, limit: int, offset: int) -> list[dict[str, Any]]:
        plans = sorted(self.plans.get(user_id, {}).values(), key=lambda plan: plan["week_start_date"], reverse=True)
        return plans[offset:offset + limit]

    def update_session(self, user_id: str, plan_id: str, session_id: str, status: str) -> dict[str, Any] | None:
        plan = self.get(user_id, plan_id)
        if not plan:
            return None
        for session in plan["sessions"]:
            if session["id"] == session_id:
                session["status"] = status
                session["completed_at"] = datetime.now(timezone.utc).isoformat() if status == "completed" else None
                return session
        return None


class SupabaseTopicRepository:
    def __init__(self, client: Client) -> None:
        self.client = client

    def list_topics(self) -> list[dict[str, Any]]:
        return self.client.table("topics").select("id,name,category").execute().data


class SupabaseProfileRepository:
    def __init__(self, client: Client) -> None:
        self.client = client

    def get(self, user_id: str) -> dict[str, Any]:
        rows = self.client.table("profiles").select("*").eq("id", user_id).limit(1).execute().data
        return rows[0] if rows else {}


class SupabaseStudyPlanRepository:
    def __init__(self, client: Client) -> None:
        self.client = client

    def create(self, plan: dict[str, Any]) -> dict[str, Any]:
        plan_row = {key: plan[key] for key in ("id", "user_id", "week_start_date", "status", "generated_at", "horizon_weeks", "config")}
        self.client.table("study_plans").insert(plan_row).execute()
        rows = [{key: session[key] for key in ("id", "plan_id", "user_id", "topic_id", "day_of_week", "start_time", "duration_minutes", "status", "completed_at")} for session in plan["sessions"]]
        if rows:
            self.client.table("plan_sessions").insert(rows).execute()
        return plan

    def archive(self, user_id: str, plan_id: str) -> None:
        self.client.table("study_plans").update({"status": "archived"}).eq("id", plan_id).eq("user_id", user_id).execute()

    def _with_sessions(self, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not rows:
            return None
        plan = rows[0]
        plan["sessions"] = self.client.table("plan_sessions").select("*").eq("plan_id", plan["id"]).eq("user_id", plan["user_id"]).execute().data
        return plan

    def current(self, user_id: str, week_start: date) -> dict[str, Any] | None:
        rows = self.client.table("study_plans").select("*").eq("user_id", user_id).eq("week_start_date", week_start.isoformat()).eq("status", "active").limit(1).execute().data
        return self._with_sessions(rows)

    def get(self, user_id: str, plan_id: str) -> dict[str, Any] | None:
        rows = self.client.table("study_plans").select("*").eq("id", plan_id).eq("user_id", user_id).limit(1).execute().data
        return self._with_sessions(rows)

    def history(self, user_id: str, limit: int, offset: int) -> list[dict[str, Any]]:
        rows = self.client.table("study_plans").select("*").eq("user_id", user_id).order("week_start_date", desc=True).range(offset, offset + limit - 1).execute().data
        return [self._with_sessions([row]) for row in rows]

    def update_session(self, user_id: str, plan_id: str, session_id: str, status: str) -> dict[str, Any] | None:
        rows = self.client.table("plan_sessions").update({"status": status, "completed_at": datetime.now(timezone.utc).isoformat() if status == "completed" else None}).eq("id", session_id).eq("plan_id", plan_id).eq("user_id", user_id).execute().data
        return rows[0] if rows else None


def create_scheduler_repositories(url: str, service_role_key: str):
    client = create_client(url, service_role_key)
    return SupabaseTopicRepository(client), SupabaseProfileRepository(client), SupabaseStudyPlanRepository(client)
