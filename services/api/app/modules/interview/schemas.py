from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


RoundType = Literal["technical", "hr"]
SessionStatus = Literal["in_progress", "completed", "abandoned"]


class InterviewSessionCreate(BaseModel):
    round_type: RoundType = "technical"
    target_role: str = "Software Engineer"
    total_questions: int = Field(default=5, ge=1, le=10)


class RubricScores(BaseModel):
    accuracy: float = Field(ge=0, le=10, description="Technical accuracy or situational context (0-10)")
    structure: float = Field(ge=0, le=10, description="Problem-solving structure or STAR alignment (0-10)")
    communication: float = Field(ge=0, le=10, description="Clarity and conciseness (0-10)")
    overall: float = Field(ge=0, le=100, description="Overall weighted score out of 100")


class TurnSubmitRequest(BaseModel):
    turn_number: int = Field(ge=1)
    answer_transcript: str = Field(min_length=1)
    time_taken_s: float = Field(default=0.0, ge=0.0)


class TurnEvaluationResponse(BaseModel):
    model_config = {"protected_namespaces": ()}
    turn_number: int
    question: str
    topic: str | None = None
    answer_transcript: str
    scores: RubricScores
    feedback: str
    model_answer: str
    time_taken_s: float = 0.0
    is_complete: bool = False
    next_question: str | None = None
    next_turn_number: int | None = None


class QuestionItem(BaseModel):
    turn_number: int
    topic: str
    question: str
    context_hint: str | None = None


class NextQuestionResponse(BaseModel):
    session_id: str
    turn_number: int
    total_questions: int
    is_complete: bool
    question: QuestionItem | None = None


class SessionSummaryResponse(BaseModel):
    session_id: str
    user_id: str
    round_type: RoundType
    target_role: str
    status: SessionStatus
    total_questions: int
    completed_turns: int
    overall_score: float
    summary_feedback: str
    strengths: list[str]
    improvements: list[str]
    turns: list[dict] = []
