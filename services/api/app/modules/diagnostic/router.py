from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.deps import get_current_user
from app.shared.events import DiagnosticCompleted
from app.shared.learner_model import EVENT_BUS, apply_evidence
from app.shared.repositories import coding_repository, register_diagnostic_store
from app.shared.repositories.retry import retry_supabase

from .adaptive import AdaptiveDiagnostic
from .profiling import assign_profile, load_profile_model
from .question_generation import GroqClient, PendingQuestionsStore

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
REAL_QUESTION_TEMPLATES = {
    "DSA": [
        {"body": "What does this code print? values = [2, 4, 6]; print(values[1])", "options": ["4", "2", "6", "IndexError"], "answer": "4", "explanation": "Python lists are 0-indexed; index 1 retrieves the second element, which is 4."},
        {"body": "What is the worst-case time complexity of searching in a balanced Binary Search Tree?", "options": ["O(log n)", "O(1)", "O(n)", "O(n log n)"], "answer": "O(log n)", "explanation": "A balanced BST maintains height O(log n), guaranteeing logarithmic search time."},
        {"body": "Which data structure follows the Last-In-First-Out (LIFO) principle?", "options": ["Stack", "Queue", "Priority Queue", "Deque"], "answer": "Stack", "explanation": "A stack processes elements in LIFO order (last inserted is first removed)."},
        {"body": "What is the average time complexity of key lookup in a well-distributed Hash Map?", "options": ["O(1)", "O(log n)", "O(n)", "O(n^2)"], "answer": "O(1)", "explanation": "Hashing allows direct index lookup in constant average time O(1)."},
        {"body": "Which algorithm is optimal for finding the shortest path in a graph with non-negative edge weights?", "options": ["Dijkstra's Algorithm", "Bellman-Ford", "Kruskal's Algorithm", "Floyd-Warshall"], "answer": "Dijkstra's Algorithm", "explanation": "Dijkstra's greedy algorithm finds single-source shortest paths in non-negative weighted graphs."},
        {"body": "Which sorting algorithm guarantees O(n log n) time complexity in all cases (worst, average, best)?", "options": ["Merge Sort", "Quick Sort", "Selection Sort", "Bubble Sort"], "answer": "Merge Sort", "explanation": "Merge sort consistently divides into halves and merges in O(n log n) time."},
    ],
    "English": [
        {"body": "Choose the grammatically correct sentence.", "options": ["Neither the manager nor the employees are aware of the policy.", "Neither the manager nor the employees is aware of the policy.", "Neither the managers nor the employee are aware of the policy.", "Neither manager nor employees is aware of the policy."], "answer": "Neither the manager nor the employees are aware of the policy.", "explanation": "With 'neither...nor', the verb agrees with the closer subject ('employees' is plural => 'are')."},
        {"body": "Choose the word most nearly opposite in meaning to 'EPHEMERAL'.", "options": ["Permanent", "Transient", "Fleeting", "Fragile"], "answer": "Permanent", "explanation": "Ephemeral means short-lived; its antonym is permanent."},
        {"body": "Complete the sentence: If she ___ worked harder, she would have succeeded.", "options": ["had", "has", "have", "would have"], "answer": "had", "explanation": "Third conditional form: If + past perfect (had worked), would have + past participle."},
        {"body": "Choose the correctly punctuated sentence.", "options": ["Although it was raining, we decided to go for a run.", "Although it was raining we decided, to go for a run.", "Although, it was raining we decided to go for a run.", "Although it was raining; we decided to go for a run."], "answer": "Although it was raining, we decided to go for a run.", "explanation": "An introductory dependent clause is set off with a comma."},
        {"body": "Identify the correct idiom: 'To face the ___' means to accept unpleasant consequences.", "options": ["music", "storm", "fire", "wind"], "answer": "music", "explanation": "'To face the music' is the standard idiom for accepting consequences."},
        {"body": "Choose the correctly spelled word.", "options": ["Accommodate", "Acommodate", "Accomodate", "Acomodate"], "answer": "Accommodate", "explanation": "Accommodate is spelled with double 'c' and double 'm'."},
    ],
    "CS core": [
        {"body": "Which page-replacement algorithm is guaranteed to minimize page faults over any reference string?", "options": ["Optimal (MIN)", "FIFO", "LRU", "Clock"], "answer": "Optimal (MIN)", "explanation": "Optimal replaces the page that will not be referenced for the longest duration in the future."},
        {"body": "Which normal form eliminates transitive dependencies in a relational database?", "options": ["Third Normal Form (3NF)", "First Normal Form (1NF)", "Second Normal Form (2NF)", "Boyce-Codd Normal Form (BCNF)"], "answer": "Third Normal Form (3NF)", "explanation": "3NF requires no non-prime attribute to be transitively dependent on any candidate key."},
        {"body": "Which protocol provides reliable, connection-oriented data transfer at the Transport layer?", "options": ["TCP", "UDP", "IP", "ICMP"], "answer": "TCP", "explanation": "TCP provides flow control, error checking, and retransmission for reliable delivery."},
        {"body": "In Object-Oriented Programming, what is method overriding?", "options": ["A subclass providing a specific implementation of a method defined in its superclass", "Defining multiple methods with the same name and different parameters", "Restricting direct access to an object's internal fields", "Instantiating an abstract class directly"], "answer": "A subclass providing a specific implementation of a method defined in its superclass", "explanation": "Method overriding allows a derived class to provide a specific implementation of an inherited method."},
        {"body": "Which condition is NOT one of Coffman's four necessary conditions for deadlock?", "options": ["Preemption", "Mutual exclusion", "Hold and wait", "Circular wait"], "answer": "Preemption", "explanation": "Deadlock requires No Preemption; if preemption is allowed, deadlock cannot persist."},
        {"body": "In SQL, which clause filters aggregated group results?", "options": ["HAVING", "WHERE", "GROUP BY", "ORDER BY"], "answer": "HAVING", "explanation": "HAVING filters groups after aggregation, while WHERE filters individual rows before aggregation."},
    ],
    "aptitude": [
        {"body": "If the sum of three consecutive even integers is 48, what is the smallest of these integers?", "options": ["14", "12", "16", "18"], "answer": "14", "explanation": "Let integers be n, n+2, n+4. 3n + 6 = 48 => 3n = 42 => n = 14."},
        {"body": "A train traveling at 60 km/h passes a pole in 9 seconds. What is the length of the train?", "options": ["150 meters", "180 meters", "200 meters", "225 meters"], "answer": "150 meters", "explanation": "Speed = 60 * 5/18 = 50/3 m/s. Length = (50/3) * 9 = 150 meters."},
        {"body": "What is the remainder when 7^2021 is divided by 100?", "options": ["7", "1", "43", "49"], "answer": "7", "explanation": "7^4 = 2401 ≡ 1 (mod 100). 2021 = 4 * 505 + 1 => 7^2021 ≡ 7 (mod 100)."},
        {"body": "A shopkeeper sells an article for $120, making a profit of 20%. What was the cost price?", "options": ["$100", "$96", "$105", "$110"], "answer": "$100", "explanation": "Cost price = Selling price / (1 + profit_rate) = 120 / 1.20 = $100."},
        {"body": "A can complete a piece of work in 10 days and B in 15 days. How many days will they take together?", "options": ["6 days", "5 days", "7.5 days", "8 days"], "answer": "6 days", "explanation": "Combined rate = 1/10 + 1/15 = 5/30 = 1/6 work/day => 6 days."},
        {"body": "The average of five numbers is 12. If one of the numbers is 18, what is the sum of the remaining four?", "options": ["42", "36", "48", "60"], "answer": "42", "explanation": "Total sum = 5 * 12 = 60. Remaining sum = 60 - 18 = 42."},
    ],
}

QUESTIONS = []
for index, topic in enumerate(TOPICS * 6):
    cat = topic["category"]
    templates = REAL_QUESTION_TEMPLATES.get(cat, REAL_QUESTION_TEMPLATES["aptitude"])
    template = templates[index % len(templates)]
    QUESTIONS.append({
        "id": f"diagnostic-{index}",
        "topic_id": topic["id"],
        "category": cat,
        "difficulty": index % 5 + 1,
        "body": template["body"],
        "options": template["options"],
        "answer": template["answer"],
        "explanation": template["explanation"],
    })


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

    def _questions(self, force_reload: bool = False) -> list[dict[str, Any]]:
        if not force_reload:
            cached = getattr(self, "_cached_questions", None)
            if cached:
                return cached
        if not self.supabase:
            return QUESTIONS
        try:
            rows = retry_supabase(
                lambda: self.supabase.table("questions")
                .select("id,topic_id,difficulty,body,options,answer,explanation,topics(name,category)")
                .execute()
            ).data
            if rows:
                real_rows = []
                for row in rows:
                    topic = row.pop("topics", None) or {}
                    row["category"] = topic.get("category", "")
                    row["topic_name"] = topic.get("name", "")
                    opts = [str(o) for o in (row.get("options") or [])]
                    body = row.get("body", "")
                    # Exclude placeholder, dummy, or invalid questions
                    if any("The first option" in o for o in opts):
                        continue
                    if "Variant " in body:
                        continue
                    if "Example question:" in body:
                        continue
                    if "best answer to this reasoning problem" in body:
                        continue
                    if row.get("answer") == "The first option":
                        continue
                    if not _section_for_question(row):
                        continue
                    real_rows.append(row)
                if real_rows:
                    self._cached_questions = real_rows
                    return real_rows
        except Exception:
            cached = getattr(self, "_cached_questions", None)
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
GROQ_CLIENT = GroqClient()
PENDING_STORE = PendingQuestionsStore(supabase=STORE.supabase)
_LAST_GENERATION_TIME: float = 0.0
_GENERATION_COOLDOWN_SECONDS: float = 3.0


def _public_session(session: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in session.items() if key != "answers"}


def _user_id(current_user: dict[str, Any]) -> str:
    return str(current_user.get("id", current_user.get("sub")))


def _section_for_question(question: dict[str, Any]) -> dict[str, Any] | None:
    cat = str(question.get("category", "")).strip().lower()
    for s in SECTION_DEFINITIONS:
        if s["category"].lower() == cat or s["id"].lower() == cat:
            return s
    return None


def _current_section(session: dict[str, Any]) -> dict[str, Any] | None:
    for definition in SECTION_DEFINITIONS:
        if session["sections"][definition["id"]]["status"] != "completed":
            return definition
    return None


ADDITIONAL_CODING_PROBLEMS = [
    {"leetcode_slug": "reverse-linked-list", "title": "Reverse Linked List", "difficulty": "Easy"},
    {"leetcode_slug": "invert-binary-tree", "title": "Invert Binary Tree", "difficulty": "Easy"},
    {"leetcode_slug": "climbing-stairs", "title": "Climbing Stairs", "difficulty": "Easy"},
    {"leetcode_slug": "merge-two-sorted-lists", "title": "Merge Two Sorted Lists", "difficulty": "Easy"},
    {"leetcode_slug": "middle-of-the-linked-list", "title": "Middle of the Linked List", "difficulty": "Easy"},
    {"leetcode_slug": "search-in-rotated-sorted-array", "title": "Search in Rotated Sorted Array", "difficulty": "Medium"},
    {"leetcode_slug": "subsets", "title": "Subsets", "difficulty": "Medium"},
    {"leetcode_slug": "coin-change", "title": "Coin Change", "difficulty": "Medium"},
    {"leetcode_slug": "course-schedule", "title": "Course Schedule", "difficulty": "Medium"},
    {"leetcode_slug": "lowest-common-ancestor-of-a-binary-search-tree", "title": "Lowest Common Ancestor of a BST", "difficulty": "Medium"},
    {"leetcode_slug": "binary-search", "title": "Binary Search", "difficulty": "Easy"},
    {"leetcode_slug": "maximum-depth-of-binary-tree", "title": "Maximum Depth of Binary Tree", "difficulty": "Easy"},
    {"leetcode_slug": "linked-list-cycle", "title": "Linked List Cycle", "difficulty": "Easy"},
    {"leetcode_slug": "valid-palindrome", "title": "Valid Palindrome", "difficulty": "Easy"},
    {"leetcode_slug": "kth-largest-element-in-an-array", "title": "Kth Largest Element in an Array", "difficulty": "Medium"},
]


def _seed_additional_coding_problems(supabase: Client) -> None:
    try:
        dsa_topics = retry_supabase(
            lambda: supabase.table("topics").select("id").eq("category", "DSA").limit(1).execute()
        ).data or []
        fallback_tid = dsa_topics[0]["id"] if dsa_topics else "topic-1"
        for p in ADDITIONAL_CODING_PROBLEMS:
            row = {
                "leetcode_slug": p["leetcode_slug"],
                "title": p["title"],
                "difficulty": p["difficulty"],
                "topic_id": fallback_tid,
                "added_by_admin": False,
            }
            retry_supabase(
                lambda: supabase.table("coding_problems").upsert(row, on_conflict="leetcode_slug").execute()
            )
    except Exception:
        pass


def _generate_and_persist_questions_for_category(category: str, count: int = 5) -> list[dict[str, Any]]:
    if not STORE.supabase:
        return []
    try:
        import random
        t_rows = retry_supabase(
            lambda: STORE.supabase.table("topics")
            .select("id,name,category")
            .ilike("category", f"%{category}%")
            .execute()
        ).data or []
        if not t_rows:
            return []
        target_topic = random.choice(t_rows)
        generated = GROQ_CLIENT.generate_raw_batch(
            topic_name=target_topic["name"],
            category=category,
            count=min(count, 5),
            difficulty=3,
        )
        saved = []
        for g in generated:
            row = {
                "topic_id": target_topic["id"],
                "body": g["body"],
                "options": g["options"],
                "answer": g["answer"],
                "explanation": g.get("explanation", ""),
                "difficulty": 3,
            }
            inserted = retry_supabase(
                lambda: STORE.supabase.table("questions").insert(row).execute()
            ).data
            if inserted:
                q_row = inserted[0]
                q_row["category"] = category
                q_row["topic_name"] = target_topic["name"]
                saved.append(q_row)
        if saved:
            STORE._cached_questions = None
        return saved
    except Exception:
        return []


def _get_past_asked_ids_for_user(user_id: str, current_session_id: str | None = None) -> set[str]:
    asked_ids: set[str] = set()
    if STORE.supabase and user_id:
        try:
            att_rows = retry_supabase(
                lambda: STORE.supabase.table("attempts")
                .select("question_id")
                .eq("user_id", user_id)
                .execute()
            ).data or []
            asked_ids.update({str(r["question_id"]) for r in att_rows if r.get("question_id")})
        except Exception:
            pass

        try:
            query = STORE.supabase.table("diagnostic_sessions").select("result,sections").eq("user_id", user_id)
            if current_session_id:
                query = query.neq("id", current_session_id)
            sess_rows = retry_supabase(lambda: query.execute()).data or []
            for s_row in sess_rows:
                res = s_row.get("result") or {}
                for sec in res.get("sections") or []:
                    for ans in sec.get("answers") or []:
                        if ans.get("question_id"):
                            asked_ids.add(str(ans["question_id"]))
                raw_secs = s_row.get("sections") or {}
                sec_items = raw_secs.values() if isinstance(raw_secs, dict) else raw_secs
                for sec in sec_items:
                    if isinstance(sec, dict):
                        for ans in sec.get("answers") or []:
                            if isinstance(ans, dict) and ans.get("question_id"):
                                asked_ids.add(str(ans["question_id"]))
        except Exception:
            pass
    return asked_ids


def _section_engine(session: dict[str, Any], definition: dict[str, Any]) -> AdaptiveDiagnostic:
    user_id = session.get("user_id")
    if "_past_asked_ids" not in session:
        session["_past_asked_ids"] = _get_past_asked_ids_for_user(user_id, session.get("id"))
    previously_asked_ids = set(session["_past_asked_ids"])

    # Add questions already answered in current session
    for ans in session.get("answers", []):
        if ans.get("question_id"):
            previously_asked_ids.add(str(ans["question_id"]))

    all_sec_questions = [
        question for question in STORE._questions(force_reload=False)
        if _section_for_question(question) and _section_for_question(question)["id"] == definition["id"]
    ]

    # Strictly filter out any previously asked question
    available_questions = [q for q in all_sec_questions if str(q["id"]) not in previously_asked_ids]

    section_state = session["sections"][definition["id"]]
    needed = int(section_state.get("question_limit", DEFAULT_SECTION_COUNT))

    # Dynamically generate and store new questions via Groq in Supabase if low on unseen questions
    if len(available_questions) < needed and STORE.supabase:
        new_qs = _generate_and_persist_questions_for_category(
            definition["category"],
            count=max(5, needed - len(available_questions) + 2),
        )
        for nq in new_qs:
            if str(nq["id"]) not in previously_asked_ids:
                available_questions.append(nq)

    candidate_questions = available_questions if available_questions else all_sec_questions
    current_section_answers = [answer for answer in session.get("answers", []) if answer.get("section") == definition["id"]]

    return AdaptiveDiagnostic.from_answers(
        candidate_questions,
        sorted({question["topic_id"] for question in candidate_questions}),
        current_section_answers,
        max_questions=needed,
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

    used_prob_ids: set[str] = set()
    used_prob_slugs: set[str] = set()

    if STORE.supabase and user_id:
        try:
            assigns = retry_supabase(
                lambda: STORE.supabase.table("coding_assignments")
                .select("problem_id,coding_problems(leetcode_slug)")
                .eq("user_id", user_id)
                .execute()
            ).data or []
            for a in assigns:
                if a.get("problem_id"):
                    used_prob_ids.add(str(a["problem_id"]))
                cp = a.get("coding_problems") or {}
                if cp.get("leetcode_slug"):
                    used_prob_slugs.add(str(cp["leetcode_slug"]).lower())
        except Exception:
            pass

        try:
            past_s = retry_supabase(
                lambda: STORE.supabase.table("diagnostic_sessions")
                .select("result,sections")
                .eq("user_id", user_id)
                .execute()
            ).data or []
            for s in past_s:
                res = s.get("result") or {}
                for sec in res.get("sections") or []:
                    if sec.get("id") == "coding":
                        for a in sec.get("answers") or []:
                            if a.get("problem_id"):
                                used_prob_ids.add(str(a["problem_id"]))
                            if a.get("question_id"):
                                used_prob_ids.add(str(a["question_id"]))
        except Exception:
            pass

    all_problems = []
    if STORE.supabase:
        try:
            all_problems = retry_supabase(
                lambda: STORE.supabase.table("coding_problems").select("*").execute()
            ).data or []
        except Exception:
            pass
    if not all_problems and hasattr(coding_repository, "problems") and coding_repository.problems:
        all_problems = list(coding_repository.problems)

    unseen = [
        p for p in all_problems
        if str(p["id"]) not in used_prob_ids and str(p.get("leetcode_slug", "")).lower() not in used_prob_slugs
    ]

    if not unseen and STORE.supabase:
        _seed_additional_coding_problems(STORE.supabase)
        all_problems = retry_supabase(
            lambda: STORE.supabase.table("coding_problems").select("*").execute()
        ).data or []
        unseen = [
            p for p in all_problems
            if str(p["id"]) not in used_prob_ids and str(p.get("leetcode_slug", "")).lower() not in used_prob_slugs
        ]

    easy_unseen = [p for p in unseen if p.get("difficulty") == "Easy"]
    chosen = easy_unseen[0] if easy_unseen else (unseen[0] if unseen else (all_problems[0] if all_problems else None))

    if not chosen:
        chosen = {
            "id": "two-sum",
            "title": "Two Sum",
            "leetcode_slug": "two-sum",
            "difficulty": "Easy",
            "topic_id": "topic-1",
        }

    assignment_id = None
    if STORE.supabase and user_id:
        try:
            row = {
                "user_id": user_id,
                "problem_id": chosen["id"],
                "status": "pending",
                "assigned_at": datetime.now(timezone.utc).isoformat(),
            }
            res = retry_supabase(lambda: STORE.supabase.table("coding_assignments").insert(row).execute()).data
            if res:
                assignment_id = res[0].get("id")
        except Exception:
            pass

    prob_dict = {
        "id": chosen["id"],
        "title": chosen.get("title", "Coding Problem"),
        "leetcode_slug": chosen.get("leetcode_slug", "two-sum"),
        "difficulty": chosen.get("difficulty", "Easy"),
        "topic_id": chosen.get("topic_id"),
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
            "options": [],
            "user_answer": "Verified Accepted Solution" if is_correct else ("Timed out" if is_timeout else "Skipped / Unverified"),
            "correct_answer": "Accepted LeetCode Submission",
            "explanation": f"Solve and verify on LeetCode ({prob.get('difficulty', 'Easy')}). Requires verified Accepted submission.",
            "correct": is_correct,
            "marks": 1 if is_correct else 0,
            "max_marks": 1,
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
        if STORE.supabase:
            attempt_row = {
                "user_id": _user_id(current_user),
                "question_id": prob["id"],
                "correct": is_correct,
                "time_taken_s": int(round(float(time_taken_s))),
            }
            try:
                retry_supabase(lambda: STORE.supabase.table("attempts").insert({**attempt_row, "session_id": session_id}).execute())
            except Exception:
                try:
                    retry_supabase(lambda: STORE.supabase.table("attempts").insert(attempt_row).execute())
                except Exception:
                    pass
        if prob.get("assignment_id"):
            status = "verified" if is_correct else "failed"
            try:
                coding_repository.update(_user_id(current_user), prob["assignment_id"], status)
            except Exception:
                pass
        next_index = SECTION_DEFINITIONS.index(definition) + 1
        if next_index < len(SECTION_DEFINITIONS):
            session["sections"][SECTION_DEFINITIONS[next_index]["id"]]["status"] = "in_progress"
        STORE.save(session)
        next_definition = _current_section(session)
        return {
            "correct": is_correct,
            "marks": 1 if is_correct else 0,
            "max_marks": 1,
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
    if not question_section or question_section["id"] != definition["id"]:
        raise HTTPException(status_code=409, detail=f"Complete {definition['label']} before starting this question")
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
        "options": question.get("options", []),
        "user_answer": str(payload.answer),
        "correct_answer": str(question.get("answer", "")),
        "explanation": str(question.get("explanation", "Standard technical question.")),
        "correct": correct,
        "marks": 1 if correct else 0,
        "max_marks": 1,
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

    if STORE.supabase:
        attempt_row = {
            "user_id": _user_id(current_user),
            "question_id": question["id"],
            "correct": correct,
            "time_taken_s": int(round(float(time_taken_s))),
        }
        try:
            retry_supabase(lambda: STORE.supabase.table("attempts").insert({**attempt_row, "session_id": session_id}).execute())
        except Exception:
            try:
                retry_supabase(lambda: STORE.supabase.table("attempts").insert(attempt_row).execute())
            except Exception:
                pass

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
        "marks": 1 if correct else 0,
        "max_marks": 1,
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


def _section_reports(session: dict[str, Any], mastery: dict[str, float], questions: list[dict[str, Any]], topic_map: dict[str, str] | None = None) -> list[dict[str, Any]]:
    topic_names = dict(topic_map or {})
    for question in questions:
        if question["topic_id"] not in topic_names:
            topic_names[question["topic_id"]] = question.get("topic_name") or question["topic_id"]
    question_by_id = {q["id"]: q for q in questions}
    reports = []
    for definition in SECTION_DEFINITIONS:
        state = session["sections"][definition["id"]]
        topic_ids = {question["topic_id"] for question in questions if _section_for_question(question) and _section_for_question(question)["id"] == definition["id"]}
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
                "options": a.get("options") or q_info.get("options", []),
                "user_answer": a.get("user_answer", ""),
                "correct_answer": a.get("correct_answer") or q_info.get("answer", ""),
                "explanation": a.get("explanation") or q_info.get("explanation", ""),
                "correct": a.get("correct", False),
                "marks": a.get("marks", 1 if a.get("correct") else 0),
                "max_marks": a.get("max_marks", 1),
                "time_taken_s": round(float(a.get("time_taken_s", 0)), 2),
                "auto_submitted": bool(a.get("auto_submitted", False)),
            })

        sec_total_marks = state["question_count"]
        sec_marks_obtained = state["correct_count"]
        reports.append({
            "id": definition["id"],
            "label": definition["label"],
            "description": definition["description"],
            "question_count": state["question_count"],
            "question_limit": state["question_limit"],
            "correct_count": state["correct_count"],
            "marks_obtained": sec_marks_obtained,
            "total_marks": sec_total_marks,
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
            dsa_topic_ids = {q["topic_id"] for q in questions if _section_for_question(q) and _section_for_question(q)["id"] == "coding"}
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
    total_marks = total_questions
    marks_obtained = total_correct
    overall_score_percentage = round((marks_obtained / max(1, total_marks)) * 100, 1)

    topic_map = {}
    if STORE.supabase:
        try:
            t_rows = retry_supabase(lambda: STORE.supabase.table("topics").select("id,name").execute()).data or []
            topic_map = {r["id"]: r["name"] for r in t_rows}
        except Exception:
            pass

    result = {
        "mastery": mastery,
        "topic_names": topic_map,
        "confidence": confidence,
        "sections": _section_reports(session, mastery, questions, topic_map),
        "total_questions": total_questions,
        "total_correct": total_correct,
        "total_marks": total_marks,
        "marks_obtained": marks_obtained,
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
    result = dict(session["result"])
    topic_map = result.get("topic_names") or {}
    if not topic_map and STORE.supabase:
        try:
            t_rows = retry_supabase(lambda: STORE.supabase.table("topics").select("id,name").execute()).data or []
            topic_map = {r["id"]: r["name"] for r in t_rows}
        except Exception:
            pass
        result["topic_names"] = topic_map
    mastery = result.get("mastery", {})
    if "overall_score_percentage" not in result and "sections" in result:
        total_q = sum(s.get("question_count", 0) for s in result["sections"])
        total_c = sum(s.get("correct_count", 0) for s in result["sections"])
        result["total_questions"] = total_q
        result["total_correct"] = total_c
        result["total_marks"] = total_q
        result["marks_obtained"] = total_c
        result["overall_score_percentage"] = round((total_c / max(1, total_q)) * 100, 1)
    return {**result, "weak_topics": [topic_map.get(t, t) for t in sorted(mastery, key=mastery.get)]}


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


# ---------------------------------------------------------------------------
# Admin Question Staging Endpoints
# ---------------------------------------------------------------------------

def require_admin_auth(
    x_admin_secret: str | None = Header(None, alias="X-Admin-Secret"),
    authorization: str | None = Header(None, alias="Authorization"),
) -> bool:
    """Validate admin shared secret or admin JWT claim."""
    # 1. Match shared secret header
    if x_admin_secret and settings.admin_secret and x_admin_secret == settings.admin_secret:
        return True

    # 2. Check JWT role / is_admin flag if Bearer token present
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1].strip()
        from app.core.security import verify_supabase_jwt
        payload = verify_supabase_jwt(token)
        if payload:
            if payload.get("role") == "admin" or payload.get("user_metadata", {}).get("is_admin") is True:
                return True

    raise HTTPException(status_code=403, detail="Admin access required")


class GenerateQuestionsRequest(BaseModel):
    category: str = Field(default="Data Structures")
    difficulty: str | int = Field(default="Medium")
    count: int = Field(default=3, ge=1)


@router.post("/admin/generate-questions")
def generate_questions(
    req: GenerateQuestionsRequest,
    is_admin: bool = Depends(require_admin_auth),
) -> dict[str, Any]:
    global _LAST_GENERATION_TIME
    if req.count > 20:
        raise HTTPException(
            status_code=400,
            detail="Maximum 20 questions can be requested per generation call.",
        )

    now = time.time()
    if now - _LAST_GENERATION_TIME < _GENERATION_COOLDOWN_SECONDS:
        raise HTTPException(
            status_code=429,
            detail="Rate limit cooldown in effect. Please wait a few seconds before generating more questions.",
        )
    _LAST_GENERATION_TIME = now

    surviving = GROQ_CLIENT.generate_and_verify(
        category=req.category,
        difficulty=req.difficulty,
        count=req.count,
    )

    for q in surviving:
        PENDING_STORE.add_pending(q)

    return {
        "status": "success",
        "requested_count": req.count,
        "surviving_count": len(surviving),
        "questions": surviving,
    }


@router.get("/admin/pending-questions")
def list_pending_questions(
    is_admin: bool = Depends(require_admin_auth),
) -> list[dict[str, Any]]:
    return PENDING_STORE.list_pending(include_reviewed=False)


@router.post("/admin/pending-questions/{question_id}/approve")
def approve_pending_question(
    question_id: str,
    is_admin: bool = Depends(require_admin_auth),
) -> dict[str, Any]:
    try:
        res = PENDING_STORE.approve_question(question_id)
        # Also sync to in-memory STORE._cached_questions if present
        if hasattr(STORE, "_cached_questions") and STORE._cached_questions:
            STORE._cached_questions.append(res["approved_question"])
        return {"status": "approved", "question_id": res["approved_question"]["id"], "approved_question": res["approved_question"]}
    except KeyError:
        raise HTTPException(status_code=404, detail="Pending question not found")


@router.post("/admin/pending-questions/{question_id}/reject")
def reject_pending_question(
    question_id: str,
    is_admin: bool = Depends(require_admin_auth),
) -> dict[str, Any]:
    try:
        return PENDING_STORE.reject_question(question_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Pending question not found")

