from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TopicPosterior:
    alpha: float = 1.0
    beta: float = 1.0
    answers: int = 0

    @property
    def mastery(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def uncertainty(self) -> float:
        return 1.0 / (self.alpha + self.beta)

    def update(self, correct: bool) -> None:
        if correct:
            self.alpha += 1.0
        else:
            self.beta += 1.0
        self.answers += 1


@dataclass
class AdaptiveDiagnostic:
    questions: list[dict[str, Any]]
    topic_ids: list[str]
    max_questions: int = 25
    min_topic_coverage: int = 1
    confidence_threshold: float = 0.08
    posteriors: dict[str, TopicPosterior] = field(init=False)
    answered_ids: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.posteriors = {topic_id: TopicPosterior() for topic_id in self.topic_ids}

    @classmethod
    def from_answers(
        cls,
        questions: list[dict[str, Any]],
        topic_ids: list[str],
        answers: list[dict[str, Any]],
        **kwargs: Any,
    ) -> "AdaptiveDiagnostic":
        engine = cls(questions, topic_ids, **kwargs)
        question_by_id = {question["id"]: question for question in questions}
        for answer in answers:
            question = question_by_id.get(answer["question_id"])
            if question is None or answer["question_id"] in engine.answered_ids:
                continue
            engine.answered_ids.add(answer["question_id"])
            engine.posteriors[question["topic_id"]].update(bool(answer["correct"]))
        return engine

    @property
    def question_count(self) -> int:
        return len(self.answered_ids)

    def should_stop(self) -> bool:
        if self.question_count >= self.max_questions:
            return True
        if not self.questions:
            return True
        covered = all(
            self.posteriors[topic_id].answers >= self.min_topic_coverage
            for topic_id in self.topic_ids
        )
        confident = bool(self.posteriors) and all(
            posterior.answers > 0 and posterior.uncertainty <= self.confidence_threshold
            for posterior in self.posteriors.values()
        )
        return covered or confident

    def next_question(self) -> dict[str, Any] | None:
        if self.should_stop():
            return None
        available = [
            question for question in self.questions if question["id"] not in self.answered_ids
        ]
        if not available:
            return None
        topic_counts = {topic_id: self.posteriors[topic_id].answers for topic_id in self.topic_ids}
        uncovered = [topic_id for topic_id in self.topic_ids if topic_counts[topic_id] < self.min_topic_coverage]
        candidate_topics = uncovered or self.topic_ids
        topic_id = max(
            candidate_topics,
            key=lambda item: (self.posteriors[item].uncertainty, -topic_counts[item], item),
        )
        topic_questions = [question for question in available if question["topic_id"] == topic_id]
        if not topic_questions:
            topic_questions = available
        target_difficulty = 1.0 + 4.0 * self.posteriors[topic_id].mastery
        return min(
            topic_questions,
            key=lambda question: (abs(float(question["difficulty"]) - target_difficulty), question["id"]),
        )

    def answer(self, question: dict[str, Any], answer: Any) -> bool:
        correct = str(answer).strip().lower() == str(question["answer"]).strip().lower()
        self.answered_ids.add(question["id"])
        self.posteriors[question["topic_id"]].update(correct)
        return correct

    def mastery(self) -> dict[str, float]:
        return {topic_id: posterior.mastery for topic_id, posterior in self.posteriors.items()}

    def confidence(self) -> float:
        if not self.posteriors:
            return 0.0
        return sum(1.0 - posterior.uncertainty for posterior in self.posteriors.values()) / len(self.posteriors)