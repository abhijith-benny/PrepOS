from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.shared.events import AttemptRecorded, BaseEvent, DiagnosticCompleted
from app.shared.learner_model import EVENT_BUS, get_skill_vector
from app.shared.repositories import question_repository, srs_repository

try:
    from fsrs import Card as FSRSCard
except ImportError:  # pragma: no cover
    FSRSCard = None


def create_initial_card(
    user_id: str,
    question_id: str,
    topic_id: str,
    origin: str = "manual",
) -> dict[str, Any]:
    """Create a new SRS card in initial state with idempotency on (user_id, question_id)."""
    existing = srs_repository.get_card_by_question(user_id, question_id)
    if existing:
        return existing

    now_iso = datetime.now(timezone.utc).isoformat()
    fsrs_state = None
    if FSRSCard is not None:
        try:
            fsrs_state = FSRSCard().to_dict()
        except Exception:
            fsrs_state = None

    card_data = {
        "user_id": user_id,
        "question_id": question_id,
        "topic_id": topic_id,
        "origin": origin,
        "state": "learning",
        "ease": 2.5,
        "interval_days": 0,
        "repetitions": 0,
        "lapses": 0,
        "due_at": now_iso,
        "last_review_at": None,
        "fsrs_state": fsrs_state,
        "created_at": now_iso,
    }
    return srs_repository.create_card(card_data)


def on_diagnostic_completed(event: BaseEvent) -> list[dict[str, Any]]:
    """Listener for DiagnosticCompleted event.
    Identifies the user's weak topics from the diagnostic report and creates review cards.
    """
    user_id = event.user_id
    payload = event.payload or {}
    created_cards = []

    # 1. Identify weak topics
    weak_topic_ids: list[str] = []
    mastery = payload.get("mastery") or {}
    if isinstance(mastery, dict) and mastery:
        weak_topic_ids = sorted(mastery, key=mastery.get)
    else:
        sections = payload.get("sections") or []
        for s in sections:
            weak_topic_ids.extend(s.get("weak_topics", []))

    if not weak_topic_ids:
        # Fallback to learner model skill vector
        try:
            skills = get_skill_vector(user_id)
            if skills:
                weak_topic_ids = [
                    tid for tid, s in sorted(skills.items(), key=lambda it: it[1].mastery)
                ]
        except Exception:
            pass

    # Deduplicate while preserving order
    seen_topics: set[str] = set()
    unique_weak_topics: list[str] = []
    for tid in weak_topic_ids:
        if tid and tid not in seen_topics:
            seen_topics.add(tid)
            unique_weak_topics.append(tid)

    if not unique_weak_topics:
        return []

    # 2. Get questions for these topics (up to 3 per weak topic, max 10 total)
    target_topics = unique_weak_topics[:4]
    existing_cards = srs_repository.list_cards(user_id)
    existing_q_ids = [str(c["question_id"]) for c in existing_cards]

    candidate_questions = question_repository.list_for_topics(
        topic_ids=target_topics,
        limit=10,
        exclude_ids=existing_q_ids,
    )

    for q in candidate_questions:
        card = create_initial_card(
            user_id=user_id,
            question_id=str(q["id"]),
            topic_id=str(q["topic_id"]),
            origin="diagnostic",
        )
        created_cards.append(card)

    return created_cards


def on_attempt_recorded(event: BaseEvent) -> dict[str, Any] | None:
    """Listener for AttemptRecorded event.
    If the attempt was incorrect, generate a review card for that question (origin="mistake").
    """
    payload = event.payload or {}
    if payload.get("correct") is False:
        user_id = event.user_id
        question_id = payload.get("question_id")
        topic_id = payload.get("topic_id")
        if user_id and question_id:
            # If topic_id not in payload, look up question
            if not topic_id:
                q = question_repository.get(question_id)
                topic_id = q.get("topic_id") if q else None
            if topic_id:
                return create_initial_card(
                    user_id=user_id,
                    question_id=question_id,
                    topic_id=topic_id,
                    origin="mistake",
                )
    return None


def generate_cards_for_user(user_id: str, count: int = 10) -> list[dict[str, Any]]:
    """On-demand card generation from the user's current skill vector or syllabus."""
    weak_topic_ids: list[str] = []
    try:
        skills = get_skill_vector(user_id)
        if skills:
            weak_topic_ids = [
                tid for tid, s in sorted(skills.items(), key=lambda it: it[1].mastery)
            ]
    except Exception:
        pass

    # If no skill vector yet, fetch all topics or fallback
    existing_cards = srs_repository.list_cards(user_id)
    existing_q_ids = [str(c["question_id"]) for c in existing_cards]

    # If still no weak topics, query question repository directly
    questions = question_repository.list_for_topics(
        topic_ids=weak_topic_ids,
        limit=count,
        exclude_ids=existing_q_ids,
    )

    if not questions and not weak_topic_ids:
        # Fallback to general topics
        questions = question_repository.list_for_topics(
            topic_ids=[f"topic-{i}" for i in range(1, 10)],
            limit=count,
            exclude_ids=existing_q_ids,
        )

    created = []
    for q in questions:
        card = create_initial_card(
            user_id=user_id,
            question_id=str(q["id"]),
            topic_id=str(q["topic_id"]),
            origin="manual",
        )
        created.append(card)
    return created


# Register event listeners on import
EVENT_BUS.subscribe("DiagnosticCompleted", on_diagnostic_completed)
EVENT_BUS.subscribe("AttemptRecorded", on_attempt_recorded)
