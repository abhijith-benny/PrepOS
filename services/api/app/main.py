from __future__ import annotations

from importlib import import_module

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.core.deps import get_current_user
from app.shared.events import AttemptRecorded
from app.shared.learner_model import EVENT_BUS, apply_evidence, get_skill_vector
from app.shared.repositories import attempt_repository
from app.shared.schemas import AttemptCreate, AttemptResponse, HealthResponse, MeResponse, TopicRead, UserProfileUpdate

app = FastAPI(title="PrepOS API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/interview/ui")


@app.get("/health")
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/me")
def read_me(current_user=Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        id=current_user.get("id", current_user.get("sub")),
        email=current_user.get("email"),
        full_name=current_user.get("full_name"),
    )


@app.patch("/me")
def update_me(
    payload: UserProfileUpdate,
    current_user=Depends(get_current_user),
) -> MeResponse:
    return MeResponse(
        id=current_user.get("id"),
        email=current_user.get("email"),
        full_name=current_user.get("full_name") or payload.full_name,
    )


@app.get("/topics")
def list_topics() -> list[TopicRead]:
    return []


@app.get("/skills/me")
def skills_me(current_user=Depends(get_current_user)) -> dict[str, dict[str, float]]:
    user_id = current_user.get("id", current_user.get("sub"))
    return {topic_id: state.model_dump() for topic_id, state in get_skill_vector(user_id).items()}


@app.post("/attempts", response_model=AttemptResponse)
def create_attempt(
    payload: AttemptCreate,
    current_user=Depends(get_current_user),
) -> AttemptResponse:
    user_id = str(current_user.get("id", current_user.get("sub")))
    score = 1.0 if payload.correct else 0.0
    attempt_repository.create(user_id, payload.model_dump())
    skill_vector = apply_evidence(user_id, payload.topic_id, score, payload.source, payload.weight)
    event = AttemptRecorded(
        user_id=user_id,
        payload={
            "question_id": payload.question_id,
            "topic_id": payload.topic_id,
            "correct": payload.correct,
            "source": payload.source,
            "weight": payload.weight,
        },
    )
    EVENT_BUS.emit(event)
    return AttemptResponse(
        user_id=user_id,
        topic_id=payload.topic_id,
        score=score,
        skill_vector=skill_vector,
    )


for module_name in ["diagnostic", "scheduler", "srs", "interview"]:
    try:
        module = import_module(f"app.modules.{module_name}.router")
        app.include_router(module.router)
    except ImportError:
        pass
