from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.core.deps import get_current_user
from app.shared.learner_model import apply_evidence, get_skill_vector
from app.shared.repositories import coding_repository, profile_repository, get_user_weak_topics

from .ai_selector import select_coding_problems
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

    weak_topics = get_user_weak_topics(user_id)
    target_diff = profile.get("target_difficulty") or "Medium"

    catalog_problems = []
    if hasattr(coding_repository, "get_all_problems"):
        catalog_problems = coding_repository.get_all_problems()
    if not catalog_problems and hasattr(coding_repository, "problems"):
        catalog_problems = list(coding_repository.problems)
    if not catalog_problems:
        raise HTTPException(status_code=422, detail="No unassigned coding problems are available")

    # Filter out already assigned problems if possible, so user gets fresh problems
    already_assigned = {a["problem_id"] for a in coding_repository.list_for_user(user_id)}
    unassigned = [p for p in catalog_problems if p["id"] not in already_assigned]
    candidates = unassigned if len(unassigned) >= 3 else catalog_problems

    selected_problems, rationale = select_coding_problems(
        weak_topics=weak_topics,
        problems=candidates,
        difficulty_preference=target_diff,
        limit=3,
    )

    assigned_records = []
    for prob in selected_problems:
        assigned = coding_repository.assign_problem(user_id, prob["id"], rationale=rationale)
        assigned_records.append(assigned)

    if not assigned_records:
        assigned_records.append(coding_repository.choose(user_id, weak_topics, rationale=rationale))

    primary = assigned_records[0]
    return {**primary, "assigned": assigned_records, "rationale": rationale}



@router.get("/assignments")
def list_assignments(current_user: dict[str, Any] = Depends(get_current_user)) -> list[dict[str, Any]]:
    return coding_repository.list_for_user(_user_id(current_user))


def _parse_assigned_at_epoch(assigned_at_raw: Any) -> float:
    if isinstance(assigned_at_raw, (int, float)):
        return float(assigned_at_raw)
    if isinstance(assigned_at_raw, datetime):
        if assigned_at_raw.tzinfo is None:
            assigned_at_raw = assigned_at_raw.replace(tzinfo=timezone.utc)
        return assigned_at_raw.timestamp()
    if isinstance(assigned_at_raw, str):
        dt = datetime.fromisoformat(assigned_at_raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    raise ValueError(f"Unsupported assigned_at format: {assigned_at_raw!r}")


def _normalize_slug(slug: Any) -> str:
    return str(slug or "").strip().lower()


def is_submission_verified(submission: dict[str, Any], problem_slug: str, assigned_at_epoch: float) -> bool:
    sub_slug = _normalize_slug(submission.get("titleSlug"))
    target_slug = _normalize_slug(problem_slug)
    if not sub_slug or sub_slug != target_slug:
        return False
    raw_ts = submission.get("timestamp")
    if raw_ts is None:
        return False
    try:
        sub_epoch = int(raw_ts)
    except (ValueError, TypeError):
        return False
    return sub_epoch >= assigned_at_epoch


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
        submissions = CLIENT.recent_accepted_submissions(username, force_refresh=True)
    except PrivateProfileError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except EmptySubmissionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LeetCodeNetworkError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    assigned_at_raw = assignment.get("assigned_at")
    assigned_at_epoch = _parse_assigned_at_epoch(assigned_at_raw)
    problem_slug = problem.get("leetcode_slug", "")

    verified = any(
        is_submission_verified(submission, problem_slug, assigned_at_epoch)
        for submission in submissions
    )
    if not verified:
        updated = coding_repository.update(user_id, assignment_id, "failed_to_verify")
        return {**(updated or assignment), "message": "No Accepted submission after this problem was assigned yet"}
    updated = coding_repository.update(user_id, assignment_id, "verified")
    apply_evidence(user_id, problem["topic_id"], 1.0, "leetcode", LEETCODE_WEIGHT)
    return {**(updated or assignment), "message": "Accepted LeetCode submission verified"}
