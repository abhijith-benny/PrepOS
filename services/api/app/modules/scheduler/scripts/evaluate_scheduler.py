from __future__ import annotations

import importlib
import json
import time
from pathlib import Path

import numpy as np

from ..scheduler_engine import CATEGORY_IMPORTANCE, build_weekly_plan


# Keep scheduler production imports within app.shared/app.core while reusing M1's generator.
def _synthetic_population(seed: int, size: int) -> tuple[np.ndarray, np.ndarray]:
    module = importlib.import_module("app.modules.diagnostic.profiling")
    return module.synthetic_population(seed=seed, size=size)


def _topics(count: int) -> list[dict[str, str]]:
    categories = ["DSA", "aptitude", "CS core", "system design", "behavioral"]
    return [{"id": str(index), "name": f"Topic {index}", "category": categories[index % len(categories)]} for index in range(count)]


def _allocate(skills: np.ndarray, topics: list[dict[str, str]], hours: float, mode: str) -> tuple[set[int], float]:
    blocks = int(hours * 2)
    if mode == "equal":
        order = list(range(len(topics)))
    elif mode == "unweighted":
        order = sorted(range(len(topics)), key=lambda index: skills[index])
    else:
        order = sorted(
            range(len(topics)),
            key=lambda index: (1.0 - skills[index]) * CATEGORY_IMPORTANCE.get(topics[index]["category"], 1.0),
            reverse=True,
        )
    selected = {order[index % len(order)] for index in range(blocks)}
    wasted = sum(0.5 for index in range(blocks) if skills[order[index % len(order)]] >= 0.8)
    return selected, wasted


def evaluate(seed: int = 7, learners: int = 1500) -> dict[str, object]:
    skills, _ = _synthetic_population(seed, learners)
    topics = _topics(25)
    evaluation_slots = [f"{hour:02d}:00" for hour in range(7, 23)]
    sample = skills[:20]
    coverage: dict[str, list[float]] = {mode: [] for mode in ("weighted", "equal", "unweighted")}
    wasted: dict[str, list[float]] = {mode: [] for mode in coverage}
    for learner in sample:
        for mode in coverage:
            seen: set[int] = set()
            wasted_hours = 0.0
            for _week in range(4):
                selected, wasted_week = _allocate(learner, topics, 10, mode)
                seen.update(selected)
                wasted_hours += wasted_week
            weak = {index for index, value in enumerate(learner) if value < 0.6}
            coverage[mode].append(len(seen & weak) / max(1, len(weak)))
            wasted[mode].append(wasted_hours)

    solver_times: dict[str, float] = {}
    for count in (10, 25, 50):
        active_topics = _topics(count)
        start = time.perf_counter()
        build_weekly_plan(
            active_topics,
            {topic["id"]: 0.4 for topic in active_topics},
            max(10, count / 2),
            preferred_times=evaluation_slots,
            solver_seconds=0.5,
        )
        solver_times[str(count)] = time.perf_counter() - start

    infeasibility: dict[str, float] = {}
    for hours in (1, 2, 4, 8, 12, 16, 20):
        failures = sum(
            hours < sum(float(value) < 0.6 for value in learner) * 0.5
            for learner in sample
        )
        infeasibility[str(hours)] = failures / len(sample)

    return {
        "seed": seed,
        "learners_evaluated": len(sample),
        "four_week_weak_topic_coverage": {mode: float(np.mean(values)) for mode, values in coverage.items()},
        "four_week_wasted_hours": {mode: float(np.mean(values)) for mode, values in wasted.items()},
        "solver_wall_seconds": solver_times,
        "infeasibility_rate_by_weekly_hours": infeasibility,
    }


if __name__ == "__main__":
    output = Path("scheduler-evaluation.json")
    report = evaluate()
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
