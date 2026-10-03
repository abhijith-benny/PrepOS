from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/interview", tags=["interview"])


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"module": "interview", "status": "stub"}
