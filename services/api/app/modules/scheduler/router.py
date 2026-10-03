from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"module": "scheduler", "status": "stub"}
