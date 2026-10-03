from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from supabase import create_client

from app.main import app


REQUIRED_ENV = (
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_TEST_JWT",
)


@pytest.mark.integration
def test_attempt_persists_across_repository_instances() -> None:
    if any(not os.getenv(name) for name in REQUIRED_ENV):
        pytest.skip("real Supabase integration environment is not configured")

    url = os.environ["SUPABASE_URL"]
    service_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    user_id = os.environ.get("SUPABASE_TEST_USER_ID")
    client = create_client(url, service_key)
    question = client.table("questions").select("id,topic_id").limit(1).execute().data[0]
    token = os.environ["SUPABASE_TEST_JWT"]

    response = TestClient(app).post(
        "/attempts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "question_id": question["id"],
            "topic_id": question["topic_id"],
            "correct": True,
            "time_taken_s": 18,
            "source": "integration",
            "weight": 1.0,
        },
    )
    assert response.status_code == 200, response.text
    persisted_user_id = user_id or response.json()["user_id"]

    attempts = (
        client.table("attempts")
        .select("id")
        .eq("user_id", persisted_user_id)
        .eq("question_id", question["id"])
        .execute()
        .data
    )
    skills = (
        client.table("skill_states")
        .select("mastery,confidence")
        .eq("user_id", persisted_user_id)
        .eq("topic_id", question["topic_id"])
        .execute()
        .data
    )
    events = (
        client.table("events")
        .select("type")
        .eq("user_id", persisted_user_id)
        .in_("type", ["SkillUpdated", "AttemptRecorded"])
        .execute()
        .data
    )

    assert attempts
    assert skills
    assert {event["type"] for event in events} >= {"SkillUpdated", "AttemptRecorded"}