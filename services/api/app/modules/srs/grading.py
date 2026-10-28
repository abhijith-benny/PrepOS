from __future__ import annotations


def grade_review(
    correct: bool,
    time_taken_s: int,
    expected_time_s: int = 60,
    confidence: str | None = None,
) -> int:
    """Map correctness, time taken, and optional self-reported confidence to a 0-5 quality score.

    Scale:
      0: Complete blackout / incorrect with zero recall
      1: Incorrect response with basic familiarity
      2: Incorrect response where correct answer seemed close / recalled with effort
      3: Correct response recalled with serious difficulty / hesitation / slow
      4: Correct response after normal hesitation / standard timing
      5: Perfect response with fast, effortless recall
    """
    conf = (confidence or "").strip().lower()
    t = max(1, int(time_taken_s))
    exp = max(1, int(expected_time_s))

    if not correct:
        if conf in ("blackout", "none", "zero") or t <= (0.3 * exp):
            return 0
        if t >= exp or conf in ("high", "close"):
            return 2
        return 1

    # Correct responses
    if t > (1.3 * exp) or conf in ("low", "hesitant", "unsure", "hard"):
        return 3

    if t <= (0.7 * exp) and conf in ("high", "easy", "sure", "effortless", ""):
        return 5

    return 4
