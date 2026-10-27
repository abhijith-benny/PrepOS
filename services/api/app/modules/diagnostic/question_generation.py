from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

import httpx
from supabase import Client

from app.core.config import settings
from app.shared.repositories.retry import retry_supabase

logger = logging.getLogger("diagnostic.question_generation")

GROQ_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"


def _clean_json_text(text: str) -> str:
    """Strip code fences and locate outermost JSON brackets."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
    return text


def _extract_json(text: str) -> Any:
    cleaned = _clean_json_text(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        first_bracket = min([i for i in (cleaned.find("["), cleaned.find("{")) if i != -1], default=-1)
        last_bracket = max([cleaned.rfind("]"), cleaned.rfind("}")])
        if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
            sub = cleaned[first_bracket : last_bracket + 1]
            return json.loads(sub)
        raise


class GroqClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key or settings.groq_api_key
        self.model = model or settings.groq_model or "openai/gpt-oss-120b"
        self.http_client = http_client or httpx.Client(timeout=30.0)

    def _call_groq(self, messages: list[dict[str, str]], temperature: float = 0.6) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        response = self.http_client.post(GROQ_COMPLETIONS_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def _validate_question_dict(self, item: Any) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        body = item.get("question") or item.get("body")
        options = item.get("options")
        answer_idx = item.get("answer_index")
        explanation = item.get("explanation")

        if not body or not isinstance(body, str) or not body.strip():
            return None
        if not isinstance(options, list) or len(options) != 4:
            return None
        if any(not isinstance(opt, str) or not opt.strip() for opt in options):
            return None
        try:
            answer_idx = int(answer_idx)
            if answer_idx not in (0, 1, 2, 3):
                return None
        except (ValueError, TypeError):
            return None

        return {
            "body": body.strip(),
            "options": [opt.strip() for opt in options],
            "answer_index": answer_idx,
            "explanation": str(explanation or "").strip() or "Standard technical interview question.",
        }

    def generate_raw_batch(
        self,
        category: str,
        difficulty: str | int,
        count: int,
        llm_caller: Callable[[list[dict[str, str]]], str] | None = None,
    ) -> list[dict[str, Any]]:
        """Generate a batch of questions with 1 retry on malformed JSON."""
        caller = llm_caller or (lambda msgs: self._call_groq(msgs, temperature=0.7))

        prompt = (
            f"You are an expert technical interviewer creating diagnostic placement questions.\n"
            f"Generate exactly {count} distinct multiple-choice questions for Category: '{category}', Difficulty: '{difficulty}'.\n"
            f"Requirements:\n"
            f"1. Exactly 4 clear, plausible options per question.\n"
            f"2. answer_index MUST be 0, 1, 2, or 3, pointing to the unambiguously correct option.\n"
            f"3. explanation must be a clear one-line justification.\n"
            f"4. Output STRICT, VALID JSON ONLY as an array of objects. Do not include markdown codeblocks or extra text.\n"
            f"Format:\n"
            f"[\n"
            f'  {{"question": "Question text...", "options": ["Opt0", "Opt1", "Opt2", "Opt3"], "answer_index": 0, "explanation": "Why correct..."}}\n'
            f"]"
        )

        messages = [
            {"role": "system", "content": "You are a strict JSON question generator. Output ONLY a JSON array."},
            {"role": "user", "content": prompt},
        ]

        valid_questions: list[dict[str, Any]] = []
        max_attempts = 2  # initial + 1 retry

        for attempt in range(max_attempts):
            try:
                raw_text = caller(messages)
                parsed = _extract_json(raw_text)
                if isinstance(parsed, dict) and "questions" in parsed:
                    parsed = parsed["questions"]
                if not isinstance(parsed, list):
                    parsed = [parsed]

                for item in parsed:
                    validated = self._validate_question_dict(item)
                    if validated:
                        validated["category"] = category
                        validated["difficulty"] = str(difficulty)
                        valid_questions.append(validated)
                    else:
                        logger.warning("Skipping malformed question item: %s", item)

                if valid_questions:
                    break
            except Exception as e:
                logger.warning("Attempt %d generation failed: %s. Retrying once...", attempt + 1, e)
                messages.append({"role": "user", "content": f"The previous response was malformed ({e}). Return STRICT valid JSON array only."})

        return valid_questions[:count]

    def self_check_question(
        self,
        question: dict[str, Any],
        llm_caller: Callable[[list[dict[str, str]]], str] | None = None,
    ) -> tuple[bool, str]:
        """Independently solve the question without knowing the stated answer index.

        Returns (matches: bool, reasoning: str).
        """
        caller = llm_caller or (lambda msgs: self._call_groq(msgs, temperature=0.1))

        options_text = "\n".join(f"{i}: {opt}" for i, opt in enumerate(question["options"]))
        prompt = (
            f"You are a meticulous technical grader verifying a multiple-choice question.\n"
            f"Question:\n{question['body']}\n\n"
            f"Options:\n{options_text}\n\n"
            f"Instructions:\n"
            f"1. Solve the question independently step-by-step.\n"
            f"2. Identify the single correct option index (0, 1, 2, or 3).\n"
            f"3. Return STRICT JSON ONLY in the following format:\n"
            f'{{"reasoning": "Your step-by-step reasoning...", "derived_answer_index": 0}}\n'
        )

        messages = [
            {"role": "system", "content": "You are a strict independent grader. Output STRICT JSON ONLY."},
            {"role": "user", "content": prompt},
        ]

        for attempt in range(2):
            try:
                raw_text = caller(messages)
                parsed = _extract_json(raw_text)
                derived_idx = int(parsed.get("derived_answer_index"))
                reasoning = str(parsed.get("reasoning", "")).strip()

                matches = derived_idx == int(question["answer_index"])
                if not matches:
                    logger.warning(
                        "Self-check DISCARD: question stated answer %d, model independently derived %d. Body: %s",
                        question["answer_index"],
                        derived_idx,
                        question["body"],
                    )
                return matches, reasoning
            except Exception as e:
                logger.warning("Self-check attempt %d failed: %s", attempt + 1, e)

        return False, "Failed to independently verify answer."

    def generate_and_verify(
        self,
        category: str,
        difficulty: str | int,
        count: int,
        llm_caller: Callable[[list[dict[str, str]]], str] | None = None,
        self_check_caller: Callable[[list[dict[str, str]]], str] | None = None,
    ) -> list[dict[str, Any]]:
        """Generate questions, perform independent self-check, and return only surviving questions."""
        raw_candidates = self.generate_raw_batch(category, difficulty, count, llm_caller=llm_caller)
        surviving: list[dict[str, Any]] = []

        for candidate in raw_candidates:
            passed, reasoning = self.self_check_question(candidate, llm_caller=self_check_caller or llm_caller)
            if passed:
                surviving.append({
                    "id": str(uuid4()),
                    "category": candidate["category"],
                    "difficulty": candidate["difficulty"],
                    "body": candidate["body"],
                    "options": candidate["options"],
                    "answer_index": candidate["answer_index"],
                    "explanation": candidate["explanation"],
                    "model_check_passed": True,
                    "self_check_reasoning": reasoning,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "reviewed": False,
                })
            else:
                logger.info("Question discarded by self-check: %s", candidate.get("body"))

        return surviving


class PendingQuestionsStore:
    def __init__(self, supabase: Client | None = None) -> None:
        self.supabase = supabase
        self.local_pending: dict[str, dict[str, Any]] = {}
        self.local_questions: list[dict[str, Any]] = []
        self._supabase_table_exists: bool | None = None

    def _check_supabase_table(self) -> bool:
        if not self.supabase:
            return False
        if self._supabase_table_exists is not None:
            return self._supabase_table_exists
        try:
            self.supabase.table("generated_questions_pending").select("id").limit(1).execute()
            self._supabase_table_exists = True
        except Exception:
            self._supabase_table_exists = False
        return self._supabase_table_exists

    def add_pending(self, question: dict[str, Any]) -> dict[str, Any]:
        item = dict(question)
        if "id" not in item:
            item["id"] = str(uuid4())
        if "created_at" not in item:
            item["created_at"] = datetime.now(timezone.utc).isoformat()
        if "reviewed" not in item:
            item["reviewed"] = False

        self.local_pending[item["id"]] = item

        if self._check_supabase_table():
            try:
                row = {
                    "id": item["id"],
                    "category": item["category"],
                    "difficulty": str(item["difficulty"]),
                    "body": item["body"],
                    "options": item["options"],
                    "answer_index": int(item["answer_index"]),
                    "explanation": item["explanation"],
                    "model_check_passed": bool(item.get("model_check_passed", True)),
                    "created_at": item["created_at"],
                    "reviewed": bool(item["reviewed"]),
                }
                retry_supabase(lambda: self.supabase.table("generated_questions_pending").insert(row).execute())
            except Exception as e:
                logger.warning("Supabase insert pending failed, using local: %s", e)

        return item

    def list_pending(self, include_reviewed: bool = False) -> list[dict[str, Any]]:
        if self._check_supabase_table():
            try:
                query = self.supabase.table("generated_questions_pending").select("*").order("created_at", desc=True)
                if not include_reviewed:
                    query = query.eq("reviewed", False)
                rows = retry_supabase(lambda: query.execute()).data or []
                if rows:
                    for row in rows:
                        self.local_pending[row["id"]] = row
                    return rows
            except Exception as e:
                logger.warning("Supabase list pending failed, using local: %s", e)

        items = list(self.local_pending.values())
        if not include_reviewed:
            items = [item for item in items if not item.get("reviewed")]
        return sorted(items, key=lambda x: x.get("created_at", ""), reverse=True)

    def get_pending(self, question_id: str) -> dict[str, Any] | None:
        if question_id in self.local_pending:
            return self.local_pending[question_id]
        if self._check_supabase_table():
            try:
                rows = retry_supabase(lambda: self.supabase.table("generated_questions_pending").select("*").eq("id", question_id).limit(1).execute()).data
                if rows:
                    self.local_pending[question_id] = rows[0]
                    return rows[0]
            except Exception:
                pass
        return None

    def approve_question(self, question_id: str, default_topic_id: str | None = None) -> dict[str, Any]:
        item = self.get_pending(question_id)
        if not item:
            raise KeyError(f"Pending question {question_id} not found")

        diff_raw = str(item.get("difficulty", "2")).lower()
        diff_int = 1 if "easy" in diff_raw or diff_raw == "1" else (3 if "hard" in diff_raw or diff_raw == "3" else 2)

        answer_idx = int(item["answer_index"])
        options = item["options"]
        answer_text = options[answer_idx] if 0 <= answer_idx < len(options) else options[0]

        topic_id = default_topic_id or item.get("topic_id")
        if not topic_id and self.supabase:
            try:
                topics = retry_supabase(lambda: self.supabase.table("topics").select("id,name").limit(1).execute()).data
                if topics:
                    topic_id = topics[0]["id"]
            except Exception:
                pass
        if not topic_id:
            topic_id = "4fd489c2-6123-43aa-b443-f0ca2bf08efd"

        live_row = {
            "id": str(uuid4()),
            "topic_id": topic_id,
            "difficulty": diff_int,
            "type": "mcq",
            "body": item["body"],
            "options": options,
            "answer": answer_text,
            "explanation": item.get("explanation", ""),
        }

        if self.supabase:
            try:
                retry_supabase(lambda: self.supabase.table("questions").insert(live_row).execute())
            except Exception as e:
                logger.error("Failed to insert into live questions table: %s", e)

        self.local_questions.append(live_row)

        item["reviewed"] = True
        self.local_pending[question_id] = item

        if self._check_supabase_table():
            try:
                retry_supabase(lambda: self.supabase.table("generated_questions_pending").update({"reviewed": True}).eq("id", question_id).execute())
            except Exception as e:
                logger.warning("Failed to update pending row reviewed=True: %s", e)

        return {"approved_question": live_row, "pending_id": question_id}

    def reject_question(self, question_id: str) -> dict[str, Any]:
        item = self.get_pending(question_id)
        if not item:
            raise KeyError(f"Pending question {question_id} not found")

        item["reviewed"] = True
        self.local_pending[question_id] = item

        if self._check_supabase_table():
            try:
                retry_supabase(lambda: self.supabase.table("generated_questions_pending").update({"reviewed": True}).eq("id", question_id).execute())
            except Exception as e:
                logger.warning("Failed to update pending row reviewed=True on reject: %s", e)

        return {"rejected_id": question_id, "status": "rejected"}
