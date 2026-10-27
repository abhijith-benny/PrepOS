"""Diagnostic repository functions to access diagnostic session results without violating module import boundaries."""
from __future__ import annotations

from typing import Any

_DIAGNOSTIC_STORE: Any = None


def register_diagnostic_store(store: Any) -> None:
    global _DIAGNOSTIC_STORE
    _DIAGNOSTIC_STORE = store


def get_user_weak_topics(user_id: str) -> list[str]:
    """Retrieve weak topics for the user from their latest completed diagnostic session.
    Falls back to learner model skill vector if no diagnostic session exists."""
    if _DIAGNOSTIC_STORE:
        for session in reversed(list(_DIAGNOSTIC_STORE.sessions.values())):
            if session.get("user_id") == user_id and session.get("status") == "completed":
                result = session.get("result", {})
                mastery = result.get("mastery", {})
                if mastery:
                    return sorted(mastery, key=mastery.get)
                sections = result.get("sections", [])
                weak = []
                for s in sections:
                    weak.extend(s.get("weak_topics", []))
                if weak:
                    return weak

    try:
        from app.shared.learner_model import get_skill_vector
        skills = get_skill_vector(user_id)
        if skills:
            return [topic_id for topic_id, state in sorted(skills.items(), key=lambda item: item[1].mastery)]
    except Exception:
        pass

    return []
