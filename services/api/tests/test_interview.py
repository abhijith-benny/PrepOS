from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.deps import get_current_user
from app.main import app
from app.modules.interview.evaluator import InterviewRubricEvaluator
from app.modules.interview.generator import InterviewQuestionGenerator
from app.modules.interview.router import STORE
from app.shared.learner_model import EVENT_BUS, get_skill_vector


def test_question_generator_technical_and_hr() -> None:
    tech_q1 = InterviewQuestionGenerator.generate_question("technical", "Backend Engineer", 1)
    assert "question" in tech_q1
    assert "topic" in tech_q1
    assert tech_q1["model_answer"]

    tech_q2 = InterviewQuestionGenerator.generate_question("technical", "Backend Engineer", 2)
    assert tech_q2["question"] != tech_q1["question"]

    hr_q1 = InterviewQuestionGenerator.generate_question("hr", "Software Engineer", 1)
    assert "project" in hr_q1["question"].lower() or "challenging" in hr_q1["question"].lower()


def test_rubric_evaluator_technical() -> None:
    good_answer = (
        "To find the median, I used a binary search on the partition cut of the smaller array. "
        "The time complexity is O(log(min(N, M))) and space complexity is O(1). "
        "The trade-off is ensuring the left partition maximums are less than right partition minimums."
    )
    res = InterviewRubricEvaluator.evaluate(
        round_type="technical",
        question="How to find median of two sorted arrays?",
        topic="DSA",
        answer_transcript=good_answer,
        model_answer="Binary search on partition cut with O(log(min(N, M))) time and O(1) space.",
        time_taken_s=30.0,
    )
    assert res["scores"].accuracy >= 6.0
    assert res["scores"].structure >= 6.0
    assert res["scores"].overall >= 60.0
    assert len(res["strengths"]) > 0


def test_rubric_evaluator_short_answer() -> None:
    short_answer = "Yes I know."
    res = InterviewRubricEvaluator.evaluate(
        round_type="technical",
        question="Explain CAP theorem",
        topic="System Design",
        answer_transcript=short_answer,
        model_answer="Consistency, Availability, Partition tolerance tradeoff.",
    )
    assert res["scores"].overall < 40.0
    assert "too brief" in res["feedback"].lower()


def test_interview_requires_auth() -> None:
    client = TestClient(app)
    resp = client.post("/interview/sessions", json={"round_type": "technical"})
    assert resp.status_code == 401


def test_interview_session_full_lifecycle() -> None:
    test_user_id = "test-interview-user-42"
    app.dependency_overrides[get_current_user] = lambda: {"id": test_user_id, "email": "test@prep.os"}

    try:
        STORE.sessions.clear()
        STORE.turns.clear()
        client = TestClient(app)

        # 1. Start session
        start_resp = client.post(
            "/interview/sessions",
            json={"round_type": "technical", "target_role": "Backend Engineer", "total_questions": 2},
        )
        assert start_resp.status_code == 201
        session_data = start_resp.json()
        session_id = session_data["id"]
        assert session_data["status"] == "in_progress"

        # 2. Fetch current question
        next_q = client.get(f"/interview/sessions/{session_id}/next")
        assert next_q.status_code == 200
        q_data = next_q.json()
        assert not q_data["is_complete"]
        assert q_data["turn_number"] == 1
        assert q_data["question"]["question"]

        # 3. Submit first answer
        ans1_resp = client.post(
            f"/interview/sessions/{session_id}/answer",
            json={
                "turn_number": 1,
                "answer_transcript": "I would use Floyd's cycle detection algorithm with slow and fast pointers. Time complexity is O(N) and space is O(1).",
                "time_taken_s": 25.0,
            },
        )
        assert ans1_resp.status_code == 200
        eval1 = ans1_resp.json()
        assert eval1["scores"]["overall"] > 0
        assert not eval1["is_complete"]
        assert eval1["next_turn_number"] == 2

        # 4. Submit second answer (completing questions)
        ans2_resp = client.post(
            f"/interview/sessions/{session_id}/answer",
            json={
                "turn_number": 2,
                "answer_transcript": "Binary search on the smaller array partition to achieve O(log(min(N,M))).",
                "time_taken_s": 20.0,
            },
        )
        assert ans2_resp.status_code == 200
        eval2 = ans2_resp.json()
        assert eval2["is_complete"]

        # 5. Complete session
        complete_resp = client.post(f"/interview/sessions/{session_id}/complete")
        assert complete_resp.status_code == 200
        summary = complete_resp.json()
        assert summary["status"] == "completed"
        assert summary["completed_turns"] == 2
        assert summary["overall_score"] > 0
        assert len(summary["strengths"]) > 0 or len(summary["improvements"]) > 0

        # Check event bus recorded InterviewScored event
        events = [e for e in EVENT_BUS.events if e.type == "InterviewScored" and e.user_id == test_user_id]
        assert len(events) >= 1
        assert events[-1].payload["session_id"] == session_id

        # Check skill state update
        skills = get_skill_vector(test_user_id)
        assert "System Design 1" in skills

    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_interview_audio_transcription_endpoint(monkeypatch) -> None:
    test_user_id = "test-audio-user"
    app.dependency_overrides[get_current_user] = lambda: {"id": test_user_id, "email": "audio@prep.os"}
    try:
        STORE.sessions.clear()
        client = TestClient(app)
        start_resp = client.post("/interview/sessions", json={"round_type": "technical"})
        session_id = start_resp.json()["id"]

        monkeypatch.setattr(
            "app.modules.interview.router.AudioTranscriptionService.transcribe",
            lambda file_content, filename: "I used dynamic programming to solve the knapsack problem.",
        )
        fake_wav = b"RIFF....WAVEfmt ...."
        resp = client.post(
            f"/interview/sessions/{session_id}/transcribe",
            files={"file": ("test.wav", fake_wav, "audio/wav")},
        )
        assert resp.status_code == 200
        assert resp.json()["transcript"] == "I used dynamic programming to solve the knapsack problem."
    finally:
        app.dependency_overrides.pop(get_current_user, None)
