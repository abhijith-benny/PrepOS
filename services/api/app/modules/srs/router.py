from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/srs", tags=["srs"])


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"module": "srs", "status": "stub"}
