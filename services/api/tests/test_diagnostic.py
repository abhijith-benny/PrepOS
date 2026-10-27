from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.deps import get_current_user
from app.main import app
from app.modules.diagnostic.adaptive import AdaptiveDiagnostic
from app.modules.diagnostic.profiling import assign_profile, fit_profile_model
from app.modules.diagnostic.router import STORE


def test_selection_never_repeats_and_posterior_moves() -> None:
    questions = [
        {"id": "q1", "topic_id": "t1", "difficulty": 2, "answer": "A"},
        {"id": "q2", "topic_id": "t1", "difficulty": 4, "answer": "A"},
        {"id": "q3", "topic_id": "t2", "difficulty": 3, "answer": "A"},
    ]
    engine = AdaptiveDiagnostic(questions, ["t1", "t2"], min_topic_coverage=1)
    first = engine.next_question()
    assert first is not None
    before = engine.posteriors[first["topic_id"]].mastery
    engine.answer(first, "A")
    assert engine.posteriors[first["topic_id"]].mastery > before
    second = engine.next_question()
    assert second is not None
    assert second["id"] != first["id"]


def test_stopping_rule_triggers_after_coverage() -> None:
    questions = [
        {"id": "q1", "topic_id": "t1", "difficulty": 2, "answer": "A"},
        {"id": "q2", "topic_id": "t2", "difficulty": 2, "answer": "A"},
    ]
    engine = AdaptiveDiagnostic(questions, ["t1", "t2"], min_topic_coverage=1)
    engine.answer(engine.next_question(), "A")
    engine.answer(engine.next_question(), "A")
    assert engine.should_stop()
    assert engine.next_question() is None


def test_profile_assignment_is_deterministic() -> None:
    profile = fit_profile_model(seed=11)
    vector = [0.8] * 5 + [0.4] * 20
    assert assign_profile(vector, profile) == assign_profile(vector, profile)


def test_diagnostic_requires_auth() -> None:
    response = TestClient(app).post("/diagnostic/sessions")
    assert response.status_code == 401


def test_full_flow_and_session_ownership() -> None:
    app.dependency_overrides[get_current_user] = lambda: {"id": "diagnostic-user", "email": "demo@example.com"}
    try:
        STORE.sessions.clear()
        client = TestClient(app)
        started = client.post("/diagnostic/sessions")
        assert started.status_code == 201
        session_id = started.json()["id"]
        next_response = client.get(f"/diagnostic/sessions/{session_id}/next")
        question = next_response.json()["question"]
        assert "answer" not in question
        answered = client.post(
            f"/diagnostic/sessions/{session_id}/answer",
            json={"question_id": question["id"], "answer": "A", "time_taken_s": 4},
        )
        assert answered.status_code == 200
        completed = client.post(f"/diagnostic/sessions/{session_id}/complete")
        assert completed.status_code == 200
        assert "model_version" in completed.json()
        report = client.get(f"/diagnostic/sessions/{session_id}/report")
        assert report.status_code == 200
        assert report.json()["weak_topics"]
    finally:
        app.dependency_overrides.clear()


def test_sections_unlock_in_order_and_report_groups() -> None:
    from app.modules.diagnostic import router as diagnostic_router

    diagnostic_router.STORE.legacy_completion = False
    app.dependency_overrides[get_current_user] = lambda: {"id": "section-user", "email": "section@example.com"}
    try:
        client = TestClient(app)
        started = client.post("/diagnostic/sessions")
        session_id = started.json()["id"]
        session = diagnostic_router.STORE.sessions[session_id]
        for state in session["sections"].values():
            state["question_limit"] = 1
        first = client.get(f"/diagnostic/sessions/{session_id}/next").json()["question"]
        second_question = next(
            question for question in diagnostic_router.STORE._questions()
            if question["category"] == "CS core"
        )
        locked = client.post(
            f"/diagnostic/sessions/{session_id}/answer",
            json={"question_id": second_question["id"], "answer": "A", "time_taken_s": 1},
        )
        assert locked.status_code == 409
        client.post(f"/diagnostic/sessions/{session_id}/answer", json={"question_id": first["id"], "answer": "A", "time_taken_s": 1})
        for category in ("CS core", "English", "DSA"):
            question = next(item for item in diagnostic_router.STORE._questions() if item["category"] == category)
            response = client.get(f"/diagnostic/sessions/{session_id}/next").json()
            assert response["section"]["label"]
            client.post(f"/diagnostic/sessions/{session_id}/answer", json={"question_id": question["id"], "answer": "A", "time_taken_s": 1})
        report = client.post(f"/diagnostic/sessions/{session_id}/complete")
        assert report.status_code == 200
        assert [section["label"] for section in report.json()["sections"]] == ["Aptitude", "Computer Aptitude", "English", "Coding"]
        assert all("score" in section for section in report.json()["sections"])
    finally:
        app.dependency_overrides.clear()

    app.dependency_overrides[get_current_user] = lambda: {"id": "other-user", "email": "other@example.com"}
    try:
        assert TestClient(app).get(f"/diagnostic/sessions/{session_id}/report").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_coding_suggestions_maps_to_weak_coding_topics() -> None:
    """Complete a diagnostic session, then verify the /coding-suggestions endpoint
    returns LeetCode problems whose topic_ids align with the coding section weak topics."""
    from app.modules.diagnostic import router as diagnostic_router
    from app.shared.repositories.coding import InMemoryCodingRepository

    # Give the in-memory coding repo some problems tagged to known DSA topic ids.
    # The in-memory diagnostic questions use topic ids like "topic-15" … "topic-19" for DSA.
    # We seed one problem per DSA topic so the suggestions endpoint can match.
    dsa_topic_ids = [
        topic["id"]
        for topic in diagnostic_router.TOPICS
        if topic["category"] == "DSA"
    ]
    coding_repo = InMemoryCodingRepository()
    coding_repo.problems = [
        {"id": f"p-{i}", "leetcode_slug": f"problem-{i}", "title": f"DSA Problem {i}",
         "difficulty": "Easy", "topic_id": dsa_topic_ids[i % len(dsa_topic_ids)]}
        for i in range(len(dsa_topic_ids))
    ]

    # Patch coding_repository into the diagnostic router for this test.
    import app.modules.diagnostic.router as dr
    original_coding_repo = dr.coding_repository
    dr.coding_repository = coding_repo

    diagnostic_router.STORE.legacy_completion = False
    app.dependency_overrides[get_current_user] = lambda: {"id": "suggest-user", "email": "suggest@example.com"}
    try:
        client = TestClient(app)
        started = client.post("/diagnostic/sessions")
        assert started.status_code == 201
        session_id = started.json()["id"]

        # Speed-run: set every section to 1 question, answer them all.
        session = diagnostic_router.STORE.sessions[session_id]
        for state in session["sections"].values():
            state["question_limit"] = 1

        for category in ("aptitude", "CS core", "English", "DSA"):
            client.get(f"/diagnostic/sessions/{session_id}/next")
            question = next(
                q for q in diagnostic_router.STORE._questions() if q["category"] == category
            )
            client.post(
                f"/diagnostic/sessions/{session_id}/answer",
                json={"question_id": question["id"], "answer": "B", "time_taken_s": 1},
            )

        completed = client.post(f"/diagnostic/sessions/{session_id}/complete")
        assert completed.status_code == 200

        coding_section = next(
            sec for sec in completed.json()["sections"] if sec["id"] == "coding"
        )
        weak_topic_ids_from_report = coding_section["weak_topics"]

        # Now call the suggestions endpoint.
        suggestions_resp = client.get(f"/diagnostic/sessions/{session_id}/coding-suggestions")
        assert suggestions_resp.status_code == 200, suggestions_resp.text
        suggestions = suggestions_resp.json()

        assert suggestions["session_id"] == session_id
        assert suggestions["has_problems"] is True
        assert len(suggestions["problems"]) <= 3
        assert len(suggestions["problems"]) >= 1

        # Every returned problem must have a topic_id that was in the weak list
        # (or a fallback if none match — the in-memory repo has matching ones here).
        returned_topic_ids = {p["topic_id"] for p in suggestions["problems"]}
        assert returned_topic_ids.issubset(set(dsa_topic_ids)), (
            f"Returned topic_ids {returned_topic_ids} not all in DSA topics {dsa_topic_ids}"
        )
        # At least one returned topic should match the reported weak topics.
        assert returned_topic_ids & set(weak_topic_ids_from_report), (
            f"No overlap between returned {returned_topic_ids} and weak {weak_topic_ids_from_report}"
        )

        # Verify 404 for another user.
        app.dependency_overrides[get_current_user] = lambda: {"id": "intruder", "email": "x@x.com"}
        assert client.get(f"/diagnostic/sessions/{session_id}/coding-suggestions").status_code == 404
    finally:
        dr.coding_repository = original_coding_repo
        app.dependency_overrides.clear()


def test_coding_section_directly_gives_leetcode_problem_no_mcq() -> None:
    """Verify that when a user reaches the coding section, it directly returns a
    LeetCode problem with no MCQ options and question_limit=1."""
    from app.modules.diagnostic import router as diagnostic_router

    diagnostic_router.STORE.sessions.clear()
    diagnostic_router.STORE.legacy_completion = False
    app.dependency_overrides[get_current_user] = lambda: {"id": "leetcode-user", "email": "coder@example.com"}
    try:
        client = TestClient(app)
        started = client.post("/diagnostic/sessions")
        assert started.status_code == 201
        session_id = started.json()["id"]

        session = diagnostic_router.STORE.sessions[session_id]
        # Speed-run first 3 sections with 1 question each
        for sec_id in ("aptitude", "computer_aptitude", "english"):
            session["sections"][sec_id]["question_limit"] = 1

        for category in ("aptitude", "CS core", "English"):
            resp = client.get(f"/diagnostic/sessions/{session_id}/next").json()
            q = resp["question"]
            client.post(
                f"/diagnostic/sessions/{session_id}/answer",
                json={"question_id": q["id"], "answer": "A", "time_taken_s": 2},
            )

        # Now we are in the Coding section
        coding_next = client.get(f"/diagnostic/sessions/{session_id}/next").json()
        assert coding_next["section"]["id"] == "coding"
        assert coding_next["section"]["question_limit"] == 1
        coding_q = coding_next["question"]
        assert coding_q is not None
        assert coding_q.get("type") == "leetcode"
        assert "leetcode_slug" in coding_q
        assert "leetcode_url" in coding_q
        assert coding_q.get("options") == []  # No MCQ options!

        # Answering/verifying completes the section directly in 1 question
        ans_resp = client.post(
            f"/diagnostic/sessions/{session_id}/answer",
            json={"question_id": coding_q["id"], "answer": "verified", "time_taken_s": 15},
        )
        assert ans_resp.status_code == 200
        assert ans_resp.json()["section_complete"] is True

        # And diagnostic is complete
        completed = client.post(f"/diagnostic/sessions/{session_id}/complete")
        assert completed.status_code == 200
        report = client.get(f"/diagnostic/sessions/{session_id}/report").json()
        coding_report = next(s for s in report["sections"] if s["id"] == "coding")
        assert coding_report["question_limit"] == 1
        assert coding_report["question_count"] == 1
        assert coding_report["score"] == 1.0
    finally:
        app.dependency_overrides.clear()


def test_section_timer_durations_configured_and_applied() -> None:
    """Verify that coding section gets 25 min (1500s) and MCQ sections get 60s."""
    from app.modules.diagnostic import router as diagnostic_router

    diagnostic_router.STORE.sessions.clear()
    diagnostic_router.STORE.legacy_completion = False
    app.dependency_overrides[get_current_user] = lambda: {"id": "timer-duration-user", "email": "timer@example.com"}
    try:
        client = TestClient(app)
        started = client.post("/diagnostic/sessions")
        assert started.status_code == 201
        session_id = started.json()["id"]

        # Aptitude section: 60s
        resp1 = client.get(f"/diagnostic/sessions/{session_id}/next").json()
        assert resp1["time_limit_s"] == 60
        assert resp1["section"]["time_limit_s"] == 60
        assert "served_at" in resp1

        # Advance through first 3 sections with 1 question each
        session = diagnostic_router.STORE.sessions[session_id]
        for sec_id in ("aptitude", "computer_aptitude", "english"):
            session["sections"][sec_id]["question_limit"] = 1

        for cat in ("aptitude", "CS core", "English"):
            q_resp = client.get(f"/diagnostic/sessions/{session_id}/next").json()
            client.post(
                f"/diagnostic/sessions/{session_id}/answer",
                json={"question_id": q_resp["question"]["id"], "answer": "A", "time_taken_s": 5},
            )

        # Coding section: 1500s (25 minutes)
        coding_resp = client.get(f"/diagnostic/sessions/{session_id}/next").json()
        assert coding_resp["section"]["id"] == "coding"
        assert coding_resp["time_limit_s"] == 1500
        assert coding_resp["section"]["time_limit_s"] == 1500
        assert "served_at" in coding_resp
    finally:
        app.dependency_overrides.clear()


def test_late_answer_past_grace_period_marked_timeout_and_incorrect() -> None:
    """Verify that an answer arriving past served_at + time_limit + 3s grace period is auto-treated as timeout/incorrect."""
    from datetime import datetime, timedelta, timezone
    from app.modules.diagnostic import router as diagnostic_router

    diagnostic_router.STORE.sessions.clear()
    diagnostic_router.STORE.legacy_completion = False
    app.dependency_overrides[get_current_user] = lambda: {"id": "late-user", "email": "late@example.com"}
    try:
        client = TestClient(app)
        started = client.post("/diagnostic/sessions")
        session_id = started.json()["id"]
        session = diagnostic_router.STORE.sessions[session_id]

        q_resp = client.get(f"/diagnostic/sessions/{session_id}/next").json()
        q_id = q_resp["question"]["id"]

        # Simulate that question was served 65 seconds ago (60s limit + 3s grace = 63s threshold)
        past_time = (datetime.now(timezone.utc) - timedelta(seconds=65)).isoformat()
        session["current_question"]["served_at"] = past_time

        # Client submits correct answer "A", but it is late
        ans_resp = client.post(
            f"/diagnostic/sessions/{session_id}/answer",
            json={"question_id": q_id, "answer": "A", "time_taken_s": 65},
        )
        assert ans_resp.status_code == 200
        ans_data = ans_resp.json()
        assert ans_data["correct"] is False  # Must be rejected / treated as incorrect due to timeout
        assert ans_data["auto_submitted"] is True

        # Check recorded answer in session
        stored_answer = session["sections"]["aptitude"]["answers"][-1]
        assert stored_answer["auto_submitted"] is True
        assert stored_answer["correct"] is False
    finally:
        app.dependency_overrides.clear()


def test_report_shows_overall_score_percentage_and_detailed_answers() -> None:
    """Verify that report contains overall_score_percentage and question-level breakdown with time taken and auto_submitted."""
    from app.modules.diagnostic import router as diagnostic_router

    diagnostic_router.STORE.sessions.clear()
    diagnostic_router.STORE.legacy_completion = False
    app.dependency_overrides[get_current_user] = lambda: {"id": "score-user", "email": "score@example.com"}
    try:
        client = TestClient(app)
        started = client.post("/diagnostic/sessions")
        session_id = started.json()["id"]
        session = diagnostic_router.STORE.sessions[session_id]
        for sec in session["sections"].values():
            sec["question_limit"] = 1

        # Section 1 (Aptitude): answered correctly on time
        q1 = client.get(f"/diagnostic/sessions/{session_id}/next").json()["question"]
        client.post(f"/diagnostic/sessions/{session_id}/answer", json={"question_id": q1["id"], "answer": "A", "time_taken_s": 12})

        # Section 2 (CS Core): auto-submitted on timeout
        q2 = client.get(f"/diagnostic/sessions/{session_id}/next").json()["question"]
        client.post(f"/diagnostic/sessions/{session_id}/answer", json={"question_id": q2["id"], "answer": "unanswered", "time_taken_s": 60, "auto_submitted": True})

        # Section 3 (English): answered correctly
        q3 = client.get(f"/diagnostic/sessions/{session_id}/next").json()["question"]
        client.post(f"/diagnostic/sessions/{session_id}/answer", json={"question_id": q3["id"], "answer": "A", "time_taken_s": 20})

        # Section 4 (Coding): verified
        q4 = client.get(f"/diagnostic/sessions/{session_id}/next").json()["question"]
        client.post(f"/diagnostic/sessions/{session_id}/answer", json={"question_id": q4["id"], "answer": "verified", "time_taken_s": 120})

        # Complete and fetch report
        complete_resp = client.post(f"/diagnostic/sessions/{session_id}/complete")
        assert complete_resp.status_code == 200
        data = complete_resp.json()

        # 4 total questions, 3 correct (Aptitude, English, Coding), 1 timeout (CS Core) = 75%
        assert data["total_questions"] == 4
        assert data["total_correct"] == 3
        assert data["overall_score_percentage"] == 75.0

        # Section-level answers breakdown
        report_resp = client.get(f"/diagnostic/sessions/{session_id}/report")
        assert report_resp.status_code == 200
        rep = report_resp.json()
        assert rep["overall_score_percentage"] == 75.0

        cs_sec = next(s for s in rep["sections"] if s["id"] == "computer_aptitude")
        assert len(cs_sec["answers"]) == 1
        assert cs_sec["answers"][0]["auto_submitted"] is True
        assert cs_sec["answers"][0]["correct"] is False
        assert cs_sec["answers"][0]["time_taken_s"] == 60.0

        apt_sec = next(s for s in rep["sections"] if s["id"] == "aptitude")
        assert len(apt_sec["answers"]) == 1
        assert apt_sec["answers"][0]["auto_submitted"] is False
        assert apt_sec["answers"][0]["correct"] is True
        assert apt_sec["answers"][0]["time_taken_s"] == 12.0
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Part 2: AI-Generated Question Staging & Self-Check Tests
# ---------------------------------------------------------------------------

def test_malformed_llm_json_triggers_retry_then_skip() -> None:
    import json
    from app.modules.diagnostic.question_generation import GroqClient

    client = GroqClient(api_key="fake-key")
    attempts = []

    def fake_llm(messages):
        attempts.append(messages)
        if len(attempts) == 1:
            # First attempt: completely malformed text
            return "This is not valid json at all {"
        else:
            # Second attempt (retry): 1 valid question and 1 malformed item
            return json.dumps([
                {
                    "question": "What is the capital of France?",
                    "options": ["Paris", "Rome", "Berlin", "Madrid"],
                    "answer_index": 0,
                    "explanation": "Paris is the capital of France.",
                },
                {
                    "bad_key": "missing required options and question body"
                },
            ])

    # Should retry once, accept the valid question, skip the bad one, and not crash
    raw_questions = client.generate_raw_batch("General", "Easy", 2, llm_caller=fake_llm)
    assert len(attempts) == 2, "Must retry once on malformed response"
    assert len(raw_questions) == 1
    assert raw_questions[0]["body"] == "What is the capital of France?"
    assert raw_questions[0]["answer_index"] == 0


def test_mismatched_self_check_discarded_and_never_reaches_pending() -> None:
    import json
    from app.modules.diagnostic.question_generation import GroqClient, PendingQuestionsStore

    client = GroqClient(api_key="fake-key")
    store = PendingQuestionsStore()

    # Generator returns 2 questions
    def fake_generator(messages):
        return json.dumps([
            {
                "question": "Question 1: What is 2 + 2?",
                "options": ["3", "4", "5", "6"],
                "answer_index": 1,  # Option 1 is "4"
                "explanation": "2 + 2 = 4",
            },
            {
                "question": "Question 2: What is 3 * 3?",
                "options": ["6", "7", "8", "9"],
                "answer_index": 3,  # Option 3 is "9"
                "explanation": "3 * 3 = 9",
            },
        ])

    call_count = 0

    def fake_self_checker(messages):
        nonlocal call_count
        call_count += 1
        prompt_content = messages[-1]["content"]
        if "Question 1" in prompt_content:
            # Matches answer_index 1
            return json.dumps({"reasoning": "2 + 2 is definitely 4", "derived_answer_index": 1})
        else:
            # Mismatch! Says derived is 0 instead of 3
            return json.dumps({"reasoning": "I mistakenly think 3 * 3 is 6", "derived_answer_index": 0})

    surviving = client.generate_and_verify(
        category="Math",
        difficulty="Easy",
        count=2,
        llm_caller=fake_generator,
        self_check_caller=fake_self_checker,
    )

    # Question 2 must be discarded because derived 0 != stated 3!
    assert len(surviving) == 1
    assert surviving[0]["body"] == "Question 1: What is 2 + 2?"
    assert surviving[0]["model_check_passed"] is True

    # Store surviving in pending table
    for q in surviving:
        store.add_pending(q)

    pending_list = store.list_pending()
    assert len(pending_list) == 1
    assert pending_list[0]["body"] == "Question 1: What is 2 + 2?"


def test_approve_moves_question_to_live_questions_table() -> None:
    from app.modules.diagnostic.question_generation import PendingQuestionsStore

    store = PendingQuestionsStore()
    pending_item = store.add_pending({
        "category": "Data Structures",
        "difficulty": "Medium",
        "body": "What is the time complexity of QuickSort average case?",
        "options": ["O(N)", "O(N log N)", "O(N^2)", "O(1)"],
        "answer_index": 1,
        "explanation": "Average case of QuickSort is O(N log N).",
        "model_check_passed": True,
    })

    assert len(store.list_pending()) == 1
    assert len(store.local_questions) == 0

    # Approve question
    approved = store.approve_question(pending_item["id"])
    assert approved["approved_question"]["body"] == pending_item["body"]
    assert approved["approved_question"]["answer"] == "O(N log N)"
    assert approved["approved_question"]["difficulty"] == 2
    assert approved["approved_question"]["type"] == "mcq"

    # Confirms it is moved to live questions and marked reviewed in pending
    assert len(store.local_questions) == 1
    assert len(store.list_pending()) == 0  # No longer in unreviewed pending list


def test_reject_discards_question() -> None:
    from app.modules.diagnostic.question_generation import PendingQuestionsStore

    store = PendingQuestionsStore()
    pending_item = store.add_pending({
        "category": "Algorithms",
        "difficulty": "Hard",
        "body": "Is P equal to NP?",
        "options": ["Yes", "No", "Unknown", "Sometimes"],
        "answer_index": 2,
        "explanation": "Currently an open problem in computer science.",
        "model_check_passed": True,
    })

    assert len(store.list_pending()) == 1

    # Reject question
    rejected = store.reject_question(pending_item["id"])
    assert rejected["status"] == "rejected"
    assert rejected["rejected_id"] == pending_item["id"]

    # Confirms it is removed from active pending list
    assert len(store.list_pending()) == 0


def test_admin_endpoints_auth_and_rate_limits() -> None:
    from app.core.config import settings

    client = TestClient(app)

    # 1. Unauthenticated requests to admin endpoints are rejected with 403
    r_unauth = client.get("/diagnostic/admin/pending-questions")
    assert r_unauth.status_code == 403
    assert "Admin access required" in r_unauth.json()["detail"]

    # 2. Authenticated with X-Admin-Secret header succeeds
    headers = {"X-Admin-Secret": settings.admin_secret}
    r_auth = client.get("/diagnostic/admin/pending-questions", headers=headers)
    assert r_auth.status_code == 200
    assert isinstance(r_auth.json(), list)

    # 3. Requesting > 20 questions is rejected with 400
    r_too_many = client.post(
        "/diagnostic/admin/generate-questions",
        headers=headers,
        json={"category": "DSA", "difficulty": "Easy", "count": 25},
    )
    assert r_too_many.status_code == 400
    assert "Maximum 20" in r_too_many.json()["detail"]


def test_real_marking_and_question_quality() -> None:
    """Verify that real questions have legitimate options and evaluate_answer
    scores submitted answers with real marking (+1.0 mark)."""
    from app.modules.diagnostic.adaptive import evaluate_answer
    from app.modules.diagnostic import router as dr

    # 1. Verify evaluate_answer logic
    q = {
        "body": "What is the remainder when 7^2021 is divided by 100?",
        "options": ["7", "1", "43", "49"],
        "answer": "7",
        "answer_index": 0,
        "explanation": "7^4 = 2401 = 1 mod 100",
    }

    # Matches text
    assert evaluate_answer(q, "7") is True
    # Matches letter A (index 0)
    assert evaluate_answer(q, "A") is True
    assert evaluate_answer(q, "a") is True
    # Matches digit index 0
    assert evaluate_answer(q, "0") is True
    # Incorrect option text or letter
    assert evaluate_answer(q, "43") is False
    assert evaluate_answer(q, "B") is False
    assert evaluate_answer(q, "C") is False
    # Skipped / unanswered
    assert evaluate_answer(q, "skipped") is False
    assert evaluate_answer(q, "") is False

    # 2. Verify all questions in dr.STORE._questions() are real (no dummy placeholder options)
    questions = dr.STORE._questions()
    assert len(questions) > 0
    for item in questions:
        opts = [str(o) for o in item.get("options", [])]
        assert not any("The first option" in o for o in opts), f"Dummy question found: {item}"
        assert "Variant " not in item.get("body", "")
        assert "best answer to this reasoning problem" not in item.get("body", "")

    # 3. Verify complete diagnostic session flow records marks and real marking reports
    app.dependency_overrides[get_current_user] = lambda: {"id": "marking-tester", "email": "marking@example.com"}
    try:
        client = TestClient(app)
        start_res = client.post("/diagnostic/sessions")
        assert start_res.status_code == 201
        sid = start_res.json()["id"]

        session = dr.STORE.sessions[sid]
        for sec in session["sections"].values():
            sec["question_limit"] = 1

        for cat in ("aptitude", "CS core", "English", "DSA"):
            next_q = client.get(f"/diagnostic/sessions/{sid}/next").json()["question"]
            assert next_q is not None
            ans_payload = "verified" if cat == "DSA" else (next_q.get("options", ["A"])[0] if next_q.get("options") else "A")
            ans_res = client.post(
                f"/diagnostic/sessions/{sid}/answer",
                json={"question_id": next_q["id"], "answer": ans_payload, "time_taken_s": 5},
            )
            assert ans_res.status_code == 200
            assert "marks" in ans_res.json()
            assert ans_res.json()["marks"] == 1

        complete_res = client.post(f"/diagnostic/sessions/{sid}/complete")
        assert complete_res.status_code == 200
        report_data = complete_res.json()

        assert "marks_obtained" in report_data
        assert "total_marks" in report_data
        assert report_data["marks_obtained"] >= 1
        assert report_data["total_marks"] == 4

        # Verify section detailed answers have marks, user_answer, and explanation
        for sec_rep in report_data["sections"]:
            assert "marks_obtained" in sec_rep
            assert "total_marks" in sec_rep
            for ans_item in sec_rep.get("answers", []):
                assert "marks" in ans_item
                assert "user_answer" in ans_item
                assert "correct_answer" in ans_item
    finally:
        app.dependency_overrides.clear()

