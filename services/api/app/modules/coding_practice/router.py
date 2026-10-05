from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.core.deps import get_current_user
from app.shared.learner_model import apply_evidence, get_skill_vector
from app.shared.repositories import coding_repository, profile_repository

from .leetcode_client import EmptySubmissionError, LeetCodeClient, LeetCodeNetworkError, PrivateProfileError

router = APIRouter(prefix="/coding", tags=["coding-practice"])
LEETCODE_WEIGHT = 0.6
CLIENT = LeetCodeClient()


def _user_id(current_user: dict[str, Any]) -> str:
    return str(current_user.get("id", current_user.get("sub")))


@router.post("/assign")
def assign_problem(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    user_id = _user_id(current_user)
    profile = profile_repository.get(user_id)
    if not profile.get("leetcode_username"):
        raise HTTPException(status_code=422, detail="Add your LeetCode username to Profile before assigning a problem")
    skills = get_skill_vector(user_id)
    weak_topics = [topic_id for topic_id, state in sorted(skills.items(), key=lambda item: item[1].mastery)]
    try:
        return coding_repository.choose(user_id, weak_topics)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/assignments")
def list_assignments(current_user: dict[str, Any] = Depends(get_current_user)) -> list[dict[str, Any]]:
    return coding_repository.list_for_user(_user_id(current_user))


@router.post("/assignments/{assignment_id}/verify")
def verify_assignment(assignment_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    user_id = _user_id(current_user)
    assignment = coding_repository.get(user_id, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Coding assignment not found")
    profile = profile_repository.get(user_id)
    username = profile.get("leetcode_username")
    if not username:
        raise HTTPException(status_code=422, detail="Add your LeetCode username to Profile before verifying a problem")
    problem = assignment["problem"]
    try:
        submissions = CLIENT.recent_accepted_submissions(username)
    except PrivateProfileError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except EmptySubmissionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LeetCodeNetworkError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    assigned_at = datetime.fromisoformat(assignment["assigned_at"].replace("Z", "+00:00"))
    verified = any(
        submission.get("titleSlug") == problem["leetcode_slug"]
        and datetime.fromtimestamp(int(submission["timestamp"]), timezone.utc) >= assigned_at
        for submission in submissions
    )
    if not verified:
        updated = coding_repository.update(user_id, assignment_id, "failed_to_verify")
        return {**(updated or assignment), "message": "No Accepted submission after this problem was assigned yet"}
    updated = coding_repository.update(user_id, assignment_id, "verified")
    apply_evidence(user_id, problem["topic_id"], 1.0, "leetcode", LEETCODE_WEIGHT)
    return {**(updated or assignment), "message": "Accepted LeetCode submission verified"}
