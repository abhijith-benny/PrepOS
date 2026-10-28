from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.deps import get_current_user
from app.shared.events import CardReviewed
from app.shared.learner_model import EVENT_BUS, apply_evidence
from app.shared.repositories import question_repository, srs_repository

from .generation import generate_cards_for_user
from .grading import grade_review
from .scheduler import get_scheduler, _parse_dt

router = APIRouter(prefix="/srs", tags=["srs"])


def _user_id(current_user: dict[str, Any]) -> str:
    uid = current_user.get("id") or current_user.get("sub")
    if not uid:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return str(uid)


class ReviewInput(BaseModel):
    answer: str
    time_taken_s: int = Field(default=30, ge=1)
    confidence: str | None = None


class GenerateInput(BaseModel):
    count: int = Field(default=10, ge=1, le=50)


@router.get("/due")
def get_due_cards(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Return due cards for review followed by new cards up to daily limits.
    Never exposes the correct answer or explanation before submission.
    """
    user_id = _user_id(current_user)
    now = datetime.now(timezone.utc)

    cards = srs_repository.get_due_cards(
        user_id=user_id,
        now=now,
        limit=min(limit, settings.srs_daily_review_limit),
        new_card_limit=settings.srs_daily_new_limit,
    )

    result = []
    for c in cards:
        q = question_repository.get(str(c["question_id"]))
        safe_q = None
        if q:
            safe_q = {
                "id": str(q.get("id")),
                "topic_id": str(q.get("topic_id")),
                "difficulty": q.get("difficulty"),
                "type": q.get("type"),
                "body": q.get("body"),
                "options": q.get("options") or [],
                # answer and explanation explicitly omitted!
            }
        result.append({
            "id": str(c["id"]),
            "user_id": str(c["user_id"]),
            "question_id": str(c["question_id"]),
            "topic_id": str(c["topic_id"]),
            "origin": c.get("origin"),
            "state": c.get("state"),
            "ease": c.get("ease"),
            "interval_days": c.get("interval_days"),
            "repetitions": c.get("repetitions"),
            "lapses": c.get("lapses"),
            "due_at": c.get("due_at"),
            "last_review_at": c.get("last_review_at"),
            "question": safe_q,
        })
    return result


@router.post("/cards/{card_id}/review")
def review_card(
    card_id: str,
    payload: ReviewInput,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Submit a card review, update card state via scheduler, log review, and feed learner model."""
    user_id = _user_id(current_user)
    now = datetime.now(timezone.utc)

    card = srs_repository.get_card(user_id=user_id, card_id=card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    question = question_repository.get(str(card["question_id"]))
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    correct_answer = str(question.get("answer", "")).strip().lower()
    user_answer = payload.answer.strip().lower()
    is_correct = (user_answer == correct_answer)

    # 0-5 quality grading scale
    quality = grade_review(
        correct=is_correct,
        time_taken_s=payload.time_taken_s,
        expected_time_s=60,
        confidence=payload.confidence,
    )

    # Calculate elapsed days since last review
    last_dt = _parse_dt(card.get("last_review_at"))
    elapsed_days = max(0.0, (now - last_dt).total_seconds() / 86400.0) if last_dt else 0.0

    # Advance state via scheduler (SM-2 or FSRS or Fixed)
    scheduler = get_scheduler()
    updated_card, next_due_at = scheduler.next_state(
        card=card,
        quality=quality,
        now=now,
    )

    scheduled_days = float(updated_card.get("interval_days", 1))

    # Persist card updates
    srs_repository.update_card(user_id=user_id, card_id=card_id, updates=updated_card)

    # Record review entry
    review_record = {
        "card_id": card_id,
        "user_id": user_id,
        "rating": quality,
        "correct": is_correct,
        "time_taken_s": payload.time_taken_s,
        "scheduled_days": scheduled_days,
        "elapsed_days": round(elapsed_days, 2),
        "reviewed_at": now.isoformat(),
    }
    srs_repository.record_review(review_record)

    # Feed review outcome back into learner model (loop closure)
    apply_evidence(
        user_id=user_id,
        topic_id=str(card["topic_id"]),
        score=1.0 if is_correct else 0.0,
        source="srs",
        weight=settings.srs_evidence_weight,
    )

    # Emit CardReviewed event
    event = CardReviewed(
        user_id=user_id,
        payload={
            "card_id": card_id,
            "question_id": str(card["question_id"]),
            "topic_id": str(card["topic_id"]),
            "correct": is_correct,
            "quality": quality,
            "scheduled_days": scheduled_days,
            "next_due_at": next_due_at.isoformat(),
        },
    )
    EVENT_BUS.emit(event)

    return {
        "card_id": card_id,
        "correct": is_correct,
        "quality": quality,
        "user_answer": payload.answer,
        "expected_answer": question.get("answer"),
        "explanation": question.get("explanation"),
        "next_due_at": next_due_at.isoformat(),
        "interval_days": updated_card.get("interval_days"),
        "repetitions": updated_card.get("repetitions"),
        "lapses": updated_card.get("lapses"),
        "state": updated_card.get("state"),
        "ease": updated_card.get("ease"),
    }


@router.get("/stats")
def get_stats(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Return SRS statistics: due today, reviewed today, 7-day forecast, retention estimate, and streak."""
    user_id = _user_id(current_user)
    now = datetime.now(timezone.utc)
    stats = srs_repository.get_stats(user_id=user_id, now=now)
    stats["algorithm"] = settings.srs_algorithm
    return stats


@router.post("/generate")
def generate_cards(
    payload: GenerateInput | None = None,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """On-demand card generation from weak topics."""
    user_id = _user_id(current_user)
    count = payload.count if payload else 10
    created = generate_cards_for_user(user_id=user_id, count=count)
    return {
        "created_count": len(created),
        "cards": created,
    }


@router.get("/cards")
def list_cards(
    state: str | None = None,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List all cards for the authenticated user, optionally filtered by state."""
    user_id = _user_id(current_user)
    cards = srs_repository.list_cards(user_id=user_id, state=state)
    return cards
