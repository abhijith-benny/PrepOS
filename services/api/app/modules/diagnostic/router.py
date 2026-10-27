from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.deps import get_current_user
from app.shared.events import DiagnosticCompleted
from app.shared.learner_model import EVENT_BUS, apply_evidence
from app.shared.repositories import coding_repository, register_diagnostic_store
from app.shared.repositories.retry import retry_supabase

from .adaptive import AdaptiveDiagnostic
from .profiling import assign_profile, load_profile_model

try:
    from supabase import Client, create_client
except ImportError:  # pragma: no cover
    Client = Any
    create_client = None


router = APIRouter(prefix="/diagnostic", tags=["diagnostic"])
PROFILE = load_profile_model()
SECTION_DEFINITIONS = [
    {
        "id": "aptitude",
        "label": "Aptitude",
        "description": "Quantitative and logical reasoning",
        "category": "aptitude",
        "time_limit_s": 60,
    },
    {
        "id": "computer_aptitude",
        "label": "Computer Aptitude",
        "description": "Computer science fundamentals",
        "category": "CS core",
        "time_limit_s": 60,
    },
    {
        "id": "english",
        "label": "English",
        "description": "Grammar, vocabulary, and reading comprehension",
        "category": "English",
        "time_limit_s": 60,
    },
    {
        "id": "coding",
        "label": "Coding",
        "description": "Solve a real LeetCode coding problem",
        "category": "DSA",
        "time_limit_s": 1500,  # 25 minutes per question
    },
]
SECTION_BY_ID = {section["id"]: section for section in SECTION_DEFINITIONS}
SECTION_BY_CATEGORY = {section["category"]: section for section in SECTION_DEFINITIONS}
DEFAULT_SECTION_COUNT = 10

TOPICS = [
    {"id": f"topic-{index}", "name": name, "category": category}
    for index, (name, category) in enumerate(
        [(f"Aptitude {i}", "aptitude") for i in range(1, 6)]
        + [(f"CS Core {i}", "CS core") for i in range(1, 6)]
        + [(f"English {i}", "English") for i in range(1, 6)]
        + [(f"Coding {i}", "DSA") for i in range(1, 6)]
    )
]
QUESTIONS = []
for index, topic in enumerate(TOPICS * 6):
    if topic["category"] == "DSA":
        body = "What does this code print? values = [2, 4, 6]; print(values[1])"
    elif topic["category"] == "English":
        body = "Choose the grammatically correct sentence."
    elif topic["category"] == "CS core":
        body = "Which statement about this computer science concept is correct?"
    else:
        body = "Which option is the best answer to this reasoning problem?"
    QUESTIONS.append({"id": f"diagnostic-{index}", "topic_id": topic["id"], "category": topic["category"], "difficulty": index % 5 + 1, "body": body, "options": ["A", "B", "C", "D"], "answer": "A"})


class AnswerCreate(BaseModel):
    question_id: str
    answer: str
    time_taken_s: float = Field(ge=0)
    auto_submitted: bool = False


def _new_sections(counts: dict[str, int] | None = None) -> dict[str, dict[str, Any]]:
    counts = counts or {}
    sections = {}
    for index, definition in enumerate(SECTION_DEFINITIONS):
        default_limit = 1 if definition["id"] == "coding" else DEFAULT_SECTION_COUNT
        sections[definition["id"]] = {
            "id": definition["id"],
            "label": definition["label"],
            "category": definition["category"],
            "status": "in_progress" if index == 0 else "locked",
            "time_limit_s": definition.get("time_limit_s", 60),
            "question_count": 0,
            "question_limit": int(counts.get(definition["id"], default_limit)),
            "correct_count": 0,
            "answers": [],
        }
    return sections


class SessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, Any]] = {}
        self.supabase: Client | None = None
        self.legacy_completion = False
        if settings.supabase_url and settings.supabase_service_role_key and create_client:
            self.supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    def _questions(self) -> list[dict[str, Any]]:
        cached = getattr(self, "_cached_questions", None)
        if cached:
            return cached
        if not self.supabase:
            return QUESTIONS
        try:
            rows = retry_supabase(
                lambda: self.supabase.table("questions")
                .select("id,topic_id,difficulty,body,options,answer,topics(category)")
                .execute()
            ).data
            for row in rows:
                topic = row.pop("topics", None) or {}
                row["category"] = topic.get("category", "")
            if rows:
                self._cached_questions = rows
                return rows
        except Exception:
            if cached:
                return cached
            return QUESTIONS
        return QUESTIONS

    def start(self, user_id: str, config: dict[str, Any]) -> dict[str, Any]:
        existing = self._find_in_progress(user_id)
        if existing:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "A diagnostic session is already in progress",
                    "session_id": existing["id"],
                },
            )
        session = {
            "id": str(uuid4()), "user_id": user_id, "status": "in_progress",
            "started_at": datetime.now(timezone.utc).isoformat(), "completed_at": None,
            "config": config, "sections": _new_sections(config.get("section_counts")), "result": None, "answers": [],
        }
        self._save_local(session)
        if self.supabase:
            try:
                retry_supabase(lambda: self.supabase.table("diagnostic_sessions").insert({key: value for key, value in session.items() if key != "answers"}).execute())
            except Exception:
                pass
        return _public_session(session)

    def _save_local(self, session: dict[str, Any]) -> None:
        for section in session["sections"].values():
            section["answers"] = [answer for answer in session["answers"] if answer.get("section") == section.get("id")]
        self.sessions[session["id"]] = session

    def _hydrate(self, session: dict[str, Any]) -> dict[str, Any]:
        session["sections"] = session.get("sections") or _new_sections()
        session["answers"] = session.get("answers") or [answer for section in session["sections"].values() for answer in section.get("answers", [])]
        return session

    def _find_in_progress(self, user_id: str) -> dict[str, Any] | None:
        local = next((session for session in self.sessions.values() if session["user_id"] == user_id and session["status"] == "in_progress"), None)
        if local:
            return local
        if self.supabase:
            try:
                rows = retry_supabase(lambda: self.supabase.table("diagnostic_sessions").select("*").eq("user_id", user_id).eq("status", "in_progress").limit(1).execute()).data
                if rows:
                    return self.sessions.setdefault(rows[0]["id"], self._hydrate(rows[0]))
            except Exception:
                pass
        return None

    def get(self, session_id: str, user_id: str) -> dict[str, Any]:
        session = self.sessions.get(session_id)
        if session and session["user_id"] == user_id:
            return session
        if self.supabase:
            try:
                rows = retry_supabase(lambda: self.supabase.table("diagnostic_sessions").select("*").eq("id", session_id).eq("user_id", user_id).limit(1).execute()).data
                if rows:
                    return self.sessions.setdefault(session_id, self._hydrate(rows[0]))
            except Exception:
                pass
        if session and session["user_id"] == user_id:
            return session
        raise HTTPException(status_code=404, detail="Diagnostic session not found")

    def save(self, session: dict[str, Any]) -> None:
        self._save_local(session)
        if self.supabase:
            try:
                retry_supabase(lambda: self.supabase.table("diagnostic_sessions").update({key: session[key] for key in ("status", "completed_at", "sections", "result")}).eq("id", session["id"]).eq("user_id", session["user_id"]).execute())
            except Exception:
                pass


STORE = SessionStore()
register_diagnostic_store(STORE)


def _public_session(session: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in session.items() if key != "answers"}


def _user_id(current_user: dict[str, Any]) -> str:
    return str(current_user.get("id", current_user.get("sub")))


def _section_for_question(question: dict[str, Any]) -> dict[str, Any]:
    return SECTION_BY_CATEGORY.get(question.get("category", ""), SECTION_DEFINITIONS[0])


def _current_section(session: dict[str, Any]) -> dict[str, Any] | None:
    for definition in SECTION_DEFINITIONS:
        if session["sections"][definition["id"]]["status"] != "completed":
            return definition
    return None


def _section_engine(session: dict[str, Any], definition: dict[str, Any]) -> AdaptiveDiagnostic:
    questions = [question for question in STORE._questions() if _section_for_question(question)["id"] == definition["id"]]
    section_state = session["sections"][definition["id"]]
    answers = [answer for answer in session["answers"] if answer.get("section") == definition["id"]]
    return AdaptiveDiagnostic.from_answers(
        questions,
        sorted({question["topic_id"] for question in questions}),
        answers,
        max_questions=int(section_state["question_limit"]),
        min_topic_coverage=999,
        confidence_threshold=0.0,
    )


def _question_response(
    question: dict[str, Any],
    definition: dict[str, Any],
    progress: int,
    limit: int,
    served_at: str | None = None,
    time_limit_s: int = 60,
) -> dict[str, Any]:
    return {
        "done": False,
        "progress": progress,
        "served_at": served_at,
        "time_limit_s": time_limit_s,
        "section": {
            "id": definition["id"],
            "label": definition["label"],
            "description": definition["description"],
            "index": SECTION_DEFINITIONS.index(definition) + 1,
            "total": len(SECTION_DEFINITIONS),
            "question_count": progress,
            "question_limit": limit,
            "time_limit_s": time_limit_s,
        },
        "question": {key: value for key, value in question.items() if key not in {"answer", "category"}},
    }


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"module": "diagnostic", "status": "ready"}


def _get_or_assign_coding_problem(session: dict[str, Any], user_id: str) -> dict[str, Any]:
    if session.get("coding_problem"):
        return session["coding_problem"]
    problem = None
    assignment_id = None
    try:
        assignment = coding_repository.choose(user_id, [])
        if assignment:
            problem = assignment.get("problem")
            assignment_id = assignment.get("id")
    except Exception:
        pass
    if not problem:
        if STORE.supabase:
            try:
                rows = retry_supabase(
                    lambda: STORE.supabase.table("coding_problems").select("*").limit(10).execute()
                ).data
                if rows:
                    easy = [r for r in rows if r.get("difficulty") == "Easy"]
                    problem = easy[0] if easy else rows[0]
            except Exception:
                pass
        if not problem and hasattr(coding_repository, "problems") and coding_repository.problems:
            problem = coding_repository.problems[0]
    if not problem:
        problem = {
            "id": "two-sum",
            "title": "Two Sum",
            "leetcode_slug": "two-sum",
            "difficulty": "Easy",
            "topic_id": "topic-1",
        }
    prob_dict = {
        "id": problem["id"],
        "title": problem.get("title", "Coding Problem"),
        "leetcode_slug": problem.get("leetcode_slug", "two-sum"),
        "difficulty": problem.get("difficulty", "Easy"),
        "topic_id": problem.get("topic_id"),
        "assignment_id": assignment_id,
    }
    session["coding_problem"] = prob_dict
    return prob_dict


@router.post("/sessions", status_code=201)
def start_session(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return STORE.start(
        _user_id(current_user),
        {
            "section_counts": {
                section["id"]: (1 if section["id"] == "coding" else DEFAULT_SECTION_COUNT)
                for section in SECTION_DEFINITIONS
            }
        },
    )


@router.get("/sessions/{session_id}/next")
def next_question(session_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    session = STORE.get(session_id, _user_id(current_user))
    definition = _current_section(session)
    if definition is None:
        return {"done": True, "question": None, "progress": len(session["answers"]), "sections": session["sections"]}
    state = session["sections"][definition["id"]]

    now_iso = datetime.now(timezone.utc).isoformat()
    limit_s = int(definition.get("time_limit_s", 60))

    if definition["id"] == "coding":
        state["question_limit"] = 1
        coding_answers = [a for a in session["answers"] if a.get("section") == "coding"]
        if coding_answers or state.get("question_count", 0) >= 1:
            state["status"] = "completed"
            STORE.save(session)
            return {
                "done": False,
                "section_complete": True,
                "section": {"id": definition["id"], "label": definition["label"]},
                "question": None,
                "progress": state["question_count"],
            }
        prob = _get_or_assign_coding_problem(session, _user_id(current_user))
        session["current_question"] = {
            "question_id": prob["id"],
            "served_at": now_iso,
            "time_limit_s": limit_s,
        }
        STORE.save(session)
        leetcode_q = {
            "id": prob["id"],
            "type": "leetcode",
            "title": prob["title"],
            "leetcode_slug": prob["leetcode_slug"],
            "difficulty": prob["difficulty"],
            "topic_id": prob.get("topic_id"),
            "body": f"Solve {prob['title']} on LeetCode ({prob['difficulty']})",
            "leetcode_url": f"https://leetcode.com/problems/{prob['leetcode_slug']}/",
            "assignment_id": prob.get("assignment_id"),
            "options": [],
        }
        return {
            "done": False,
            "progress": 0,
            "served_at": now_iso,
            "time_limit_s": limit_s,
            "section": {
                "id": definition["id"],
                "label": definition["label"],
                "description": definition["description"],
                "index": SECTION_DEFINITIONS.index(definition) + 1,
                "total": len(SECTION_DEFINITIONS),
                "question_count": 0,
                "question_limit": 1,
                "time_limit_s": limit_s,
            },
            "question": leetcode_q,
        }

    question = _section_engine(session, definition).next_question()
    if question is None:
        state["status"] = "completed"
        STORE.save(session)
        return {"done": False, "section_complete": True, "section": {"id": definition["id"], "label": definition["label"]}, "question": None, "progress": state["question_count"]}

    session["current_question"] = {
        "question_id": question["id"],
        "served_at": now_iso,
        "time_limit_s": limit_s,
    }
    STORE.save(session)
    return _question_response(
        question,
        definition,
        state["question_count"],
        state["question_limit"],
        served_at=now_iso,
        time_limit_s=limit_s,
    )


@router.post("/sessions/{session_id}/answer")
def answer_question(session_id: str, payload: AnswerCreate, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    session = STORE.get(session_id, _user_id(current_user))
    if session["status"] != "in_progress":
        raise HTTPException(status_code=409, detail="Diagnostic session is not in progress")
    definition = _current_section(session)
    if definition is None:
        raise HTTPException(status_code=409, detail="Diagnostic session is complete")

    GRACE_PERIOD_S = 3.0
    now = datetime.now(timezone.utc)
    current_q = session.get("current_question") or {}
    served_at_str = current_q.get("served_at")
    time_limit_s = float(current_q.get("time_limit_s", definition.get("time_limit_s", 60)))

    is_timeout = False
    if served_at_str:
        try:
            served_at_dt = datetime.fromisoformat(served_at_str.replace("Z", "+00:00"))
            elapsed_server = (now - served_at_dt).total_seconds()
            if elapsed_server > (time_limit_s + GRACE_PERIOD_S):
                is_timeout = True
        except Exception:
            pass

    auto_submitted = payload.auto_submitted or is_timeout
    time_taken_s = payload.time_taken_s
    if is_timeout and time_taken_s < time_limit_s:
        time_taken_s = time_limit_s

    if definition["id"] == "coding":
        state = session["sections"]["coding"]
        prob = _get_or_assign_coding_problem(session, _user_id(current_user))
        if is_timeout:
            is_correct = False
        else:
            is_correct = str(payload.answer).strip().lower() in ("verified", "solved", "correct", "a", "true", "1")
        answer = {
            "question_id": payload.question_id,
            "title": prob.get("title", "Coding Problem"),
            "correct": is_correct,
            "time_taken_s": time_taken_s,
            "auto_submitted": auto_submitted,
            "section": "coding",
            "type": "leetcode",
            "problem_id": prob["id"],
        }
        session["answers"].append(answer)
        state["question_count"] += 1
        state["correct_count"] += int(is_correct)
        state.setdefault("answers", []).append(answer)
        state["status"] = "completed"
        session["current_question"] = None
        if prob.get("assignment_id") and is_correct:
            try:
                coding_repository.update(_user_id(current_user), prob["assignment_id"], "verified")
            except Exception:
                pass
        next_index = SECTION_DEFINITIONS.index(definition) + 1
        if next_index < len(SECTION_DEFINITIONS):
            session["sections"][SECTION_DEFINITIONS[next_index]["id"]]["status"] = "in_progress"
        STORE.save(session)
        next_definition = _current_section(session)
        return {
            "correct": is_correct,
            "auto_submitted": auto_submitted,
            "time_taken_s": time_taken_s,
            "progress": len(session["answers"]),
            "section_complete": True,
            "section": {"id": definition["id"], "label": definition["label"]},
            "next_section": {"id": next_definition["id"], "label": next_definition["label"]} if next_definition else None,
        }

    question = next((item for item in STORE._questions() if item["id"] == payload.question_id), None)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    question_section = _section_for_question(question)
    if question_section["id"] != definition["id"]:
        raise HTTPException(status_code=409, detail=f"Complete {definition['label']} before starting {question_section['label']}")
    engine = _section_engine(session, definition)
    if payload.question_id in engine.answered_ids:
        raise HTTPException(status_code=409, detail="Question already answered")

    ans_raw = str(payload.answer).strip().lower()
    if is_timeout or (auto_submitted and ans_raw in ("unanswered", "skipped", "", "none")):
        correct = False
        engine.answered_ids.add(question["id"])
        engine.posteriors[question["topic_id"]].update(False)
    else:
        correct = engine.answer(question, payload.answer)

    answer = {
        "question_id": payload.question_id,
        "title": question.get("body", payload.question_id),
        "correct": correct,
        "time_taken_s": time_taken_s,
        "auto_submitted": auto_submitted,
        "section": definition["id"],
    }
    session["answers"].append(answer)
    state = session["sections"][definition["id"]]
    state["question_count"] += 1
    state["correct_count"] += int(correct)
    state.setdefault("answers", []).append(answer)
    session["current_question"] = None

    section_complete = state["question_count"] >= state["question_limit"] or engine.next_question() is None
    if section_complete:
        state["status"] = "completed"
        next_index = SECTION_DEFINITIONS.index(definition) + 1
        if next_index < len(SECTION_DEFINITIONS):
            session["sections"][SECTION_DEFINITIONS[next_index]["id"]]["status"] = "in_progress"
    STORE.save(session)
    next_definition = _current_section(session)
    return {
        "correct": correct,
        "auto_submitted": auto_submitted,
        "time_taken_s": time_taken_s,
        "progress": len(session["answers"]),
        "section_complete": section_complete,
        "section": {"id": definition["id"], "label": definition["label"]},
        "next_section": {"id": next_definition["id"], "label": next_definition["label"]} if section_complete and next_definition else None,
    }


def _profile_vector(mastery: dict[str, float], questions: list[dict[str, Any]]) -> list[float]:
    by_category: dict[str, list[float]] = {}
    for question in questions:
        if question["topic_id"] in mastery:
            by_category.setdefault(question.get("category", ""), []).append(mastery[question["topic_id"]])
    aptitude = by_category.get("aptitude", []) + by_category.get("English", [])
    groups = [by_category.get("DSA", []), aptitude, by_category.get("CS core", []), [], []]
    return [sum(values) / len(values) if values else 0.5 for values in groups for _ in range(5)]


def _section_reports(session: dict[str, Any], mastery: dict[str, float], questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    topic_names = {question["topic_id"]: question["topic_id"] for question in questions}
    question_by_id = {q["id"]: q for q in questions}
    reports = []
    for definition in SECTION_DEFINITIONS:
        state = session["sections"][definition["id"]]
        topic_ids = {question["topic_id"] for question in questions if _section_for_question(question)["id"] == definition["id"]}
        if definition["id"] == "coding":
            prob = session.get("coding_problem") or {}
            prob_topic = prob.get("topic_id")
            if prob_topic and prob_topic not in topic_ids:
                topic_ids.add(prob_topic)
                topic_names[prob_topic] = prob.get("title", prob_topic)
        section_mastery = {topic: mastery.get(topic, 0.5) for topic in topic_ids}
        ranked = sorted(section_mastery, key=section_mastery.get)

        sec_answers = [a for a in session["answers"] if a.get("section") == definition["id"]]
        sec_time_taken_s = sum(a.get("time_taken_s", 0) for a in sec_answers)
        detailed_answers = []
        for a in sec_answers:
            q_info = question_by_id.get(a.get("question_id"), {})
            title = a.get("title") or q_info.get("body") or (session.get("coding_problem", {}).get("title") if definition["id"] == "coding" else a.get("question_id"))
            detailed_answers.append({
                "question_id": a.get("question_id"),
                "title": title,
                "correct": a.get("correct", False),
                "time_taken_s": round(float(a.get("time_taken_s", 0)), 2),
                "auto_submitted": bool(a.get("auto_submitted", False)),
            })

        reports.append({
            "id": definition["id"],
            "label": definition["label"],
            "description": definition["description"],
            "question_count": state["question_count"],
            "question_limit": state["question_limit"],
            "correct_count": state["correct_count"],
            "score": state["correct_count"] / max(1, state["question_count"]),
            "time_taken_s": round(sec_time_taken_s, 2),
            "strong_topics": [topic_names.get(topic, topic) for topic in ranked[-2:]] if ranked else [],
            "weak_topics": [topic_names.get(topic, topic) for topic in ranked[:2]] if ranked else [],
            "answers": detailed_answers,
        })
    return reports


@router.post("/sessions/{session_id}/complete")
def complete_session(session_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    session = STORE.get(session_id, _user_id(current_user))
    if session["status"] != "in_progress":
        raise HTTPException(status_code=409, detail="Diagnostic session is not in progress")
    if _current_section(session) is not None and not STORE.legacy_completion:
        raise HTTPException(status_code=409, detail="Complete all diagnostic sections before submitting")
    questions = STORE._questions()
    mastery: dict[str, float] = {}
    for definition in SECTION_DEFINITIONS:
        if definition["id"] == "coding":
            coding_answers = [a for a in session["answers"] if a.get("section") == "coding"]
            is_correct = any(a.get("correct") for a in coding_answers) if coding_answers else False
            coding_score = 0.85 if is_correct else 0.35
            prob = session.get("coding_problem") or {}
            prob_topic = prob.get("topic_id")
            dsa_topic_ids = {q["topic_id"] for q in questions if _section_for_question(q)["id"] == "coding"}
            if not dsa_topic_ids and prob_topic:
                dsa_topic_ids = {prob_topic}
            for tid in dsa_topic_ids:
                mastery[tid] = coding_score if tid == prob_topic else (coding_score * 0.9)
            if prob_topic:
                mastery[prob_topic] = coding_score
        else:
            mastery.update(_section_engine(session, definition).mastery())
    for topic_id, value in mastery.items():
        apply_evidence(session["user_id"], topic_id, value, "diagnostic", 1.0)
    assignment = assign_profile(_profile_vector(mastery, questions), PROFILE)

    conf_list = [
        _section_engine(session, d).confidence()
        for d in SECTION_DEFINITIONS
        if d["id"] != "coding"
    ]
    conf_list.append(0.8 if any(a.get("correct") for a in session["answers"] if a.get("section") == "coding") else 0.5)
    confidence = sum(conf_list) / len(conf_list)

    total_questions = sum(s["question_count"] for s in session["sections"].values())
    total_correct = sum(s["correct_count"] for s in session["sections"].values())
    overall_score_percentage = round((total_correct / max(1, total_questions)) * 100, 1)

    result = {
        "mastery": mastery,
        "confidence": confidence,
        "sections": _section_reports(session, mastery, questions),
        "total_questions": total_questions,
        "total_correct": total_correct,
        "overall_score_percentage": overall_score_percentage,
        **assignment,
    }
    session.update({"status": "completed", "completed_at": datetime.now(timezone.utc).isoformat(), "result": result})
    STORE.save(session)
    if STORE.supabase:
        try:
            retry_supabase(lambda: STORE.supabase.table("cluster_assignments").insert({"user_id": session["user_id"], "session_id": session_id, **assignment}).execute())
        except Exception:
            pass
    EVENT_BUS.emit(DiagnosticCompleted(user_id=session["user_id"], payload=result))
    return result


@router.get("/sessions/{session_id}/report")
def session_report(session_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    session = STORE.get(session_id, _user_id(current_user))
    if not session.get("result"):
        raise HTTPException(status_code=409, detail="Diagnostic session is not complete")
    result = session["result"]
    mastery = result.get("mastery", {})
    if "overall_score_percentage" not in result and "sections" in result:
        total_q = sum(s.get("question_count", 0) for s in result["sections"])
        total_c = sum(s.get("correct_count", 0) for s in result["sections"])
        result["total_questions"] = total_q
        result["total_correct"] = total_c
        result["overall_score_percentage"] = round((total_c / max(1, total_q)) * 100, 1)
    return {**result, "weak_topics": sorted(mastery, key=mastery.get)}


@router.get("/sessions/{session_id}/coding-suggestions")
def coding_suggestions(
    session_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    limit: int = 3,
) -> dict[str, Any]:
    """Return up to *limit* real LeetCode problems mapped to the topics the user
    scored weakest on in the Coding section of this diagnostic session.

    Problems are returned as a preview only — no assignment is created here.
    The caller should direct the user to POST /coding/assign (scoped to the
    returned topic_ids) to actually create assignments.
    """
    session = STORE.get(session_id, _user_id(current_user))
    result = session.get("result")
    if not result:
        raise HTTPException(status_code=409, detail="Diagnostic session is not complete")

    # Find the Coding section report (category = DSA)
    coding_report = next(
        (sec for sec in (result.get("sections") or []) if sec.get("id") == "coding"),
        None,
    )
    weak_topic_ids: list[str] = []
    if coding_report:
        weak_topic_ids = coding_report.get("weak_topics") or []

    problems = coding_repository.suggest_problems(weak_topic_ids, limit=min(limit, 3))
    return {
        "session_id": session_id,
        "weak_topic_ids": weak_topic_ids,
        "problems": problems,
        "has_problems": bool(problems),
    }


@router.get("/latest")
def latest_session(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any] | None:
    sessions = [session for session in STORE.sessions.values() if session["user_id"] == _user_id(current_user) and session["status"] == "completed"]
    return max((_public_session(session) for session in sessions), key=lambda session: session["completed_at"]) if sessions else None
