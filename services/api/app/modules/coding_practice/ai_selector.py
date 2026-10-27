from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable

logger = logging.getLogger("coding_practice.ai_selector")


def build_selection_prompt(
    weak_topics: list[str],
    problems: list[dict[str, Any]],
    difficulty_preference: str = "Medium",
    limit: int = 3,
) -> str:
    """Build the prompt instructing the LLM to select problems from the provided catalog only."""
    catalog_summary = [
        {
            "id": p["id"],
            "title": p.get("title", ""),
            "leetcode_slug": p.get("leetcode_slug", ""),
            "difficulty": p.get("difficulty", "Easy"),
            "topic_id": p.get("topic_id", ""),
        }
        for p in problems
    ]
    return (
        f"You are an expert technical interview coach. Select exactly {limit} coding problems from the catalog below "
        f"to help a student practice their weak topics: {', '.join(weak_topics) if weak_topics else 'General DSA'}.\n"
        f"Target difficulty: {difficulty_preference}.\n\n"
        f"CATALOG:\n{json.dumps(catalog_summary, indent=2)}\n\n"
        f"CRITICAL RULES:\n"
        f"1. You MUST ONLY select problem IDs that appear in the CATALOG above. Do NOT invent new problems or slugs.\n"
        f"2. Return ONLY a valid JSON object in the following format:\n"
        f'{{"selected_ids": ["<id1>", "<id2>", "<id3>"], "rationale": "One-line rationale explaining why these problems were chosen."}}\n'
    )


def _default_heuristic_selection(
    weak_topics: list[str],
    problems: list[dict[str, Any]],
    difficulty_preference: str = "Medium",
    limit: int = 3,
) -> tuple[list[dict[str, Any]], str]:
    """Deterministic fallback that ranks catalog problems by weak topic and difficulty."""
    def sort_key(p: dict[str, Any]) -> tuple[int, int]:
        topic_match = 0 if p.get("topic_id") in weak_topics else 1
        diff_match = 0 if p.get("difficulty", "").lower() == difficulty_preference.lower() else 1
        return (topic_match, diff_match)

    sorted_probs = sorted(problems, key=sort_key)
    selected = sorted_probs[:limit]
    weak_str = ", ".join(weak_topics[:2]) if weak_topics else "data structures"
    rationale = f"Targeted practice for {weak_str} at {difficulty_preference} difficulty."
    return selected, rationale


def select_coding_problems(
    weak_topics: list[str],
    problems: list[dict[str, Any]],
    difficulty_preference: str = "Medium",
    limit: int = 3,
    llm_caller: Callable[[str], str] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Select up to `limit` problems from `problems` using an LLM or fallback, with strict ID validation and 1 retry.

    Never assigns any problem not present in `problems`.
    """
    if not problems:
        return [], "No problems available in catalog."

    catalog_map = {p["id"]: p for p in problems}
    valid_ids = set(catalog_map.keys())
    target_count = min(limit, len(problems))

    # If no LLM caller provided and no external LLM configured, use the heuristic selector
    if llm_caller is None:
        selected, rationale = _default_heuristic_selection(
            weak_topics, problems, difficulty_preference, target_count
        )
        logger.info(
            "AI problem selection (heuristic): %s | Rationale: %s",
            [p["id"] for p in selected],
            rationale,
        )
        return selected, rationale

    prompt = build_selection_prompt(weak_topics, problems, difficulty_preference, target_count)
    max_attempts = 2  # initial attempt + 1 retry
    last_error = ""

    for attempt in range(max_attempts):
        current_prompt = prompt
        if attempt > 0 and last_error:
            current_prompt += f"\n\nPREVIOUS ERROR: {last_error}\nYou must ONLY return IDs from the catalog. Try again."

        try:
            raw_response = llm_caller(current_prompt)
            # Try to extract JSON object
            start_idx = raw_response.find("{")
            end_idx = raw_response.rfind("}")
            if start_idx != -1 and end_idx != -1:
                parsed = json.loads(raw_response[start_idx : end_idx + 1])
            else:
                parsed = json.loads(raw_response)

            selected_ids = parsed.get("selected_ids", [])
            rationale = str(parsed.get("rationale", "")).strip() or "Selected based on diagnostic weakness."

            # Validate that every returned ID is strictly in the catalog
            invalid_ids = [pid for pid in selected_ids if pid not in valid_ids]
            if invalid_ids:
                last_error = f"Returned IDs {invalid_ids} are not in the catalog."
                logger.warning("Attempt %d returned invalid IDs: %s. Retrying...", attempt + 1, invalid_ids)
                continue

            if not selected_ids:
                last_error = "selected_ids was empty."
                continue

            selected_problems = [catalog_map[pid] for pid in selected_ids if pid in catalog_map][:target_count]
            # If fewer than target_count returned, fill with valid fallback
            if len(selected_problems) < target_count:
                seen_ids = {p["id"] for p in selected_problems}
                remaining = [p for p in problems if p["id"] not in seen_ids]
                selected_problems.extend(remaining[: target_count - len(selected_problems)])

            logger.info(
                "AI problem selection succeeded: %s | Rationale: %s",
                [p["id"] for p in selected_problems],
                rationale,
            )
            return selected_problems, rationale

        except Exception as e:
            last_error = str(e)
            logger.warning("Attempt %d failed with error: %s", attempt + 1, e)

    # Both attempts failed or returned invalid IDs -> Safe fallback from catalog
    logger.warning("AI selection failed after %d attempts (%s). Using catalog fallback.", max_attempts, last_error)
    fallback_selected, fallback_rationale = _default_heuristic_selection(
        weak_topics, problems, difficulty_preference, target_count
    )
    fallback_rationale = f"Selected from catalog for {', '.join(weak_topics[:2]) if weak_topics else 'practice'} (fallback after invalid AI response)."
    return fallback_selected, fallback_rationale
