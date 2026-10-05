from __future__ import annotations

import json
import os
import re
from typing import Any
import httpx

from .schemas import RubricScores


class InterviewRubricEvaluator:
    """Evaluates interview answers using rubric criteria and returns scoring and structured feedback."""

    @classmethod
    def evaluate(
        cls,
        round_type: str,
        question: str,
        topic: str | None,
        answer_transcript: str,
        model_answer: str,
        time_taken_s: float = 0.0,
        custom_key: str | None = None,
    ) -> dict[str, Any]:
        from app.core.config import settings
        api_key = (
            custom_key
            or settings.gemini_api_key
            or os.getenv("GEMINI_API_KEY")
            or settings.openai_api_key
            or os.getenv("OPENAI_API_KEY")
        )

        # If API key is available, attempt LLM evaluation with fast timeout fallback
        if api_key:
            try:
                # If key starts with AIzaSy (Google standard) or configured as Gemini
                if api_key.startswith("AIza") or not api_key.startswith("sk-"):
                    return cls._evaluate_gemini(
                        api_key=api_key,
                        round_type=round_type,
                        question=question,
                        topic=topic,
                        answer_transcript=answer_transcript,
                        model_answer=model_answer,
                    )
                else:
                    return cls._evaluate_openai(
                        api_key=api_key,
                        round_type=round_type,
                        question=question,
                        topic=topic,
                        answer_transcript=answer_transcript,
                        model_answer=model_answer,
                    )
            except Exception:
                # Graceful fallback to heuristic evaluation
                pass

        return cls._evaluate_heuristic(
            round_type=round_type,
            question=question,
            answer_transcript=answer_transcript,
            model_answer=model_answer,
            time_taken_s=time_taken_s,
        )

    @classmethod
    def _evaluate_heuristic(
        cls,
        round_type: str,
        question: str,
        answer_transcript: str,
        model_answer: str,
        time_taken_s: float,
    ) -> dict[str, Any]:
        text = answer_transcript.strip().lower()
        words = re.findall(r"\w+", text)
        word_count = len(words)
        unique_words = set(words)
        unique_ratio = len(unique_words) / max(word_count, 1)

        # 1. Repetitive / Spam / Gibberish detection
        if word_count >= 6 and unique_ratio < 0.45:
            return {
                "scores": RubricScores(accuracy=0.5, structure=0.5, communication=1.0, overall=6.0),
                "feedback": (
                    "The answer contains repetitive phrases with no substantive technical explanation. "
                    "In an actual interview, repeating filler words or prompts will result in immediate disqualification."
                ),
                "strengths": ["Spoke into the audio input"],
                "improvements": ["Provide a coherent, structured explanation addressing the specific problem and approach."],
            }

        if word_count < 10:
            return {
                "scores": RubricScores(accuracy=0.5, structure=0.5, communication=1.5, overall=8.0),
                "feedback": "Answer was too brief. In an interview, you must explain your problem-solving steps and reasoning.",
                "strengths": ["Attempted to answer promptly"],
                "improvements": ["Elaborate on technical steps, algorithms, data structures, and complexity trade-offs."],
            }

        # Extract keywords from model answer and question
        model_words = set(re.findall(r"\b[a-z]{4,}\b", model_answer.lower()))
        question_words = set(re.findall(r"\b[a-z]{4,}\b", question.lower()))
        common_words = {
            "this", "that", "with", "have", "from", "which", "would", "about",
            "there", "their", "what", "when", "where", "your", "explain", "would"
        }
        key_terms = (model_words | question_words) - common_words

        matched_terms = [term for term in key_terms if term in text]
        coverage_ratio = len(matched_terms) / max(len(key_terms), 1)

        # If zero technical keywords matched, reject as off-topic
        if not matched_terms:
            sample_keys = list(key_terms)[:3]
            sample_str = ", ".join(sample_keys) if sample_keys else "the requested topic"
            return {
                "scores": RubricScores(accuracy=0.5, structure=1.0, communication=2.0, overall=10.0),
                "feedback": (
                    f"The answer appears off-topic and did not mention any expected concepts or principles "
                    f"(such as {sample_str})."
                ),
                "strengths": ["Provided full-length verbal response"],
                "improvements": [f"Directly target the question: discuss algorithms or concepts like {sample_str}."],
            }

        if round_type == "technical":
            has_complexity = bool(re.search(r"o\(|log|time|space|pointer|node|index|o\s*\(", text))
            has_structure = bool(re.search(r"first|second|then|because|approach|algorithm|trade-off|finally|start by", text))

            # Realistic scaled scoring based on actual matched content
            base_acc = min(9.5, (coverage_ratio * 8.0) + (1.5 if has_complexity else 0.0))
            base_struct = min(9.5, (coverage_ratio * 5.0) + (3.0 if has_structure else 0.5))

            base_comm = 6.0
            if word_count < 25:
                base_comm = 3.5
            elif 40 <= word_count <= 250:
                base_comm = 8.0
            elif word_count > 300:
                base_comm = 6.0

            overall = (base_acc * 0.40 + base_struct * 0.35 + base_comm * 0.25) * 10

            feedback = (
                f"Addressed key relevant concepts: {', '.join(matched_terms[:3])}. "
                + ("Good time/space complexity analysis included. " if has_complexity else "Make sure to explicitly state time and space complexity ($O(N)$, etc.). ")
                + ("Well-structured response breakdown." if has_structure else "Try structuring your answer with an approach overview first.")
            )
            return {
                "scores": RubricScores(
                    accuracy=round(max(0.5, base_acc), 1),
                    structure=round(max(0.5, base_struct), 1),
                    communication=round(max(1.0, base_comm), 1),
                    overall=round(max(5.0, overall), 1),
                ),
                "feedback": feedback,
                "strengths": [f"Identified core terms: {', '.join(matched_terms[:3])}"],
                "improvements": ["Discuss edge cases, scaling limits, and alternative algorithmic trade-offs."],
            }
        else:
            # HR / Behavioral round - check STAR indicators
            star_signals = {
                "situation": bool(re.search(r"project|team|situation|when|company|task|client|challenge", text)),
                "action": bool(re.search(r"i decided|i built|i handled|i implemented|my role|i communicated|action|i resolved", text)),
                "result": bool(re.search(r"result|outcome|improved|delivered|learned|success|reduced|achieved|percent|metric", text)),
            }
            star_count = sum(star_signals.values())
            has_ownership = bool(re.search(r"\bi\b|my responsibility|i took|i realized|my decision", text))

            base_star = (star_count / 3.0) * 6.5 + (coverage_ratio * 3.0)
            base_owner = (3.0 if has_ownership else 1.0) + (star_count * 1.5)
            base_comm = 8.0 if (40 <= word_count <= 250) else 5.0

            overall = (base_star * 0.40 + base_owner * 0.35 + base_comm * 0.25) * 10

            feedback = (
                f"Behavioral response covered {star_count}/3 STAR components. "
                + ("Strong personal ownership demonstrated. " if has_ownership else "Use more 'I' statements to highlight your specific individual contribution. ")
                + "Focus on measurable results and what you learned from the experience."
            )
            return {
                "scores": RubricScores(
                    accuracy=round(max(0.5, base_star), 1),
                    structure=round(max(0.5, base_owner), 1),
                    communication=round(max(1.0, base_comm), 1),
                    overall=round(max(5.0, overall), 1),
                ),
                "feedback": feedback,
                "strengths": ["Clear narrative flow" if star_count >= 2 else "Relevant situational context"],
                "improvements": ["Structure explicitly using STAR (Situation, Task, Action, Result) with measurable metrics."],
            }
            star_score = sum(star_signals.values()) / 3.0
            base_star = min(9.5, max(3.5, 3.0 + (star_score * 5.0) + (coverage_ratio * 2.0)))

            has_ownership = bool(re.search(r"\bi\b|my responsibility|i took|i realized", text))
            base_owner = min(9.5, 5.0 + (2.5 if has_ownership else 0.5) + (coverage_ratio * 2.0))

            base_comm = 8.0 if (40 <= word_count <= 250) else 6.0
            overall = (base_star * 0.40 + base_owner * 0.35 + base_comm * 0.25) * 10

            feedback = "Clear behavioral explanation. Focus on quantifying measurable results (e.g. % improvements, team velocity) for stronger impact."
            return {
                "scores": RubricScores(
                    accuracy=round(base_star, 1),
                    structure=round(base_owner, 1),
                    communication=round(base_comm, 1),
                    overall=round(overall, 1),
                ),
                "feedback": feedback,
                "strengths": ["Good narrative flow and personal accountability."],
                "improvements": ["Quantify project impact with specific metrics or KPIs where possible."],
            }

    @classmethod
    def _evaluate_gemini(
        cls,
        api_key: str,
        round_type: str,
        question: str,
        topic: str | None,
        answer_transcript: str,
        model_answer: str,
    ) -> dict[str, Any]:
        prompt = f"""
You are an expert technical and HR placement interviewer for top software engineering companies.
Evaluate the candidate's interview answer based on the following rubric.

Round Type: {round_type}
Topic: {topic or 'General'}
Question: {question}
Candidate's Answer: {answer_transcript}
Ideal Reference Answer: {model_answer}

Provide evaluation in exact JSON format:
{{
  "accuracy": <float 0-10>,
  "structure": <float 0-10>,
  "communication": <float 0-10>,
  "overall": <float 0-100>,
  "feedback": "<concise actionable constructive feedback>",
  "strengths": ["<strength 1>", "<strength 2>"],
  "improvements": ["<improvement 1>", "<improvement 2>"]
}}
"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                url,
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json"},
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(raw_text)
                return {
                    "scores": RubricScores(
                        accuracy=float(parsed.get("accuracy", 7.0)),
                        structure=float(parsed.get("structure", 7.0)),
                        communication=float(parsed.get("communication", 7.0)),
                        overall=float(parsed.get("overall", 70.0)),
                    ),
                    "feedback": parsed.get("feedback", "Good effort with room for technical depth."),
                    "strengths": parsed.get("strengths", ["Solid foundational answer"]),
                    "improvements": parsed.get("improvements", ["Provide deeper technical clarity"]),
                }
        raise RuntimeError("Gemini API call failed")

    @classmethod
    def _evaluate_openai(
        cls,
        api_key: str,
        round_type: str,
        question: str,
        topic: str | None,
        answer_transcript: str,
        model_answer: str,
    ) -> dict[str, Any]:
        prompt = f"""
Evaluate this interview answer.
Round Type: {round_type}
Topic: {topic or 'General'}
Question: {question}
Candidate's Answer: {answer_transcript}
Ideal Reference Answer: {model_answer}

Return valid JSON with keys:
accuracy (0-10), structure (0-10), communication (0-10), overall (0-100), feedback (string), strengths (list of strings), improvements (list of strings).
"""
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                },
            )
            if resp.status_code == 200:
                parsed = json.loads(resp.json()["choices"][0]["message"]["content"])
                return {
                    "scores": RubricScores(
                        accuracy=float(parsed.get("accuracy", 7.0)),
                        structure=float(parsed.get("structure", 7.0)),
                        communication=float(parsed.get("communication", 7.0)),
                        overall=float(parsed.get("overall", 70.0)),
                    ),
                    "feedback": parsed.get("feedback", "Well-reasoned response."),
                    "strengths": parsed.get("strengths", ["Clear explanation"]),
                    "improvements": parsed.get("improvements", ["Add more depth on edge cases"]),
                }
        raise RuntimeError("OpenAI API call failed")
