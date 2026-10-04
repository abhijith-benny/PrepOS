from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from ortools.sat.python import cp_model


CATEGORY_IMPORTANCE = {
    "DSA": 1.20,
    "aptitude": 1.00,
    "CS core": 1.15,
    "system design": 1.10,
    "behavioral": 0.85,
}


@dataclass
class ScheduleResult:
    feasible: bool
    sessions: list[dict[str, Any]]
    reason: str | None = None
    minimum_hours_needed: float | None = None
    solver_wall_seconds: float = 0.0


def _preferred_days(value: Any) -> set[int]:
    if not value:
        return set(range(7))
    names = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
    result = set()
    for item in value:
        normalized = str(item).lower()
        result.add(names[normalized] if normalized in names else int(normalized) if normalized.isdigit() else 0)
    return result


def _preferred_times(value: Any) -> list[str]:
    if not value:
        return ["08:00", "10:00", "12:00", "14:00", "18:00", "20:00"]
    if isinstance(value, dict):
        value = value.get("times", [])
    return [str(item)[:5] for item in value]


def build_weekly_plan(
    topics: list[dict[str, Any]],
    mastery: dict[str, float],
    weekly_hours: float,
    preferred_days: Any = None,
    preferred_times: Any = None,
    min_block_minutes: int = 30,
    weak_threshold: float = 0.6,
    mastered_threshold: float = 0.8,
    solver_seconds: float = 5.0,
    week_start: date | None = None,
) -> ScheduleResult:
    if weekly_hours <= 0 or min_block_minutes <= 0:
        return ScheduleResult(False, [], "weekly_hours and min_block_minutes must be positive", 0.0)
    if not topics:
        return ScheduleResult(True, [])

    days = sorted(_preferred_days(preferred_days))
    times = _preferred_times(preferred_times)
    blocks_available = int(weekly_hours * 60 // min_block_minutes)
    weak_topics = [topic for topic in topics if mastery.get(topic["id"], 0.5) < weak_threshold]
    minimum_hours = len(weak_topics) * min_block_minutes / 60
    if blocks_available < len(weak_topics):
        return ScheduleResult(
            False,
            [],
            f"At least {minimum_hours:g} hours are required to cover {len(weak_topics)} weak topics with {min_block_minutes}-minute blocks.",
            minimum_hours,
        )

    model = cp_model.CpModel()
    variables: dict[tuple[int, str, str], cp_model.IntVar] = {}
    slots: dict[tuple[int, str], list[cp_model.IntVar]] = {}
    topic_day: dict[tuple[int, str], list[cp_model.IntVar]] = {}
    priorities: dict[str, int] = {}
    for topic in topics:
        importance = CATEGORY_IMPORTANCE.get(topic.get("category", ""), 1.0)
        priorities[topic["id"]] = int(round((1.0 - mastery.get(topic["id"], 0.5)) * importance * 1000))

    for day in days:
        for time in times:
            slots[(day, time)] = []
            for topic in topics:
                key = (day, time, topic["id"])
                variable = model.NewBoolVar(f"study_{day}_{time.replace(':', '')}_{topic['id']}")
                variables[key] = variable
                slots[(day, time)].append(variable)
                topic_day.setdefault((day, topic["id"]), []).append(variable)
            model.Add(sum(slots[(day, time)]) <= 1)

    for topic in topics:
        topic_id = topic["id"]
        all_variables = [variable for key, variable in variables.items() if key[2] == topic_id]
        if topic in weak_topics:
            model.Add(sum(all_variables) >= 1)
        for day in days:
            model.Add(sum(topic_day[(day, topic_id)]) <= 1)

    model.Add(sum(variables.values()) <= blocks_available)
    objective_terms = []
    preferred_day_set = _preferred_days(preferred_days)
    for (day, _time, topic_id), variable in variables.items():
        score = priorities[topic_id] * 100
        if day in preferred_day_set:
            score += 10
        objective_terms.append(score * variable)
    model.Maximize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = solver_seconds
    solver.parameters.num_search_workers = 1
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        reason = "Solver time limit reached before a schedule was found." if status == cp_model.UNKNOWN else "No schedule satisfies the selected hours, coverage, and slot constraints."
        return ScheduleResult(False, [], reason, minimum_hours, solver.WallTime())

    start = week_start or date.today()
    sessions = []
    for (day, time, topic_id), variable in variables.items():
        if solver.Value(variable):
            sessions.append({
                "id": None,
                "topic_id": topic_id,
                "day_of_week": day,
                "date": (start + timedelta(days=day)).isoformat(),
                "start_time": time,
                "duration_minutes": min_block_minutes,
                "status": "scheduled",
                "completed_at": None,
            })
    sessions.sort(key=lambda session: (session["day_of_week"], session["start_time"], session["topic_id"]))
    return ScheduleResult(True, sessions, solver_wall_seconds=solver.WallTime())
