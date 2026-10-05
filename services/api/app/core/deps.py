from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import verify_supabase_jwt

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    payload = verify_supabase_jwt(credentials.credentials)
    if payload is None:
        from app.core.config import settings
        if settings.app_env == "development" and not settings.jwt_secret and not settings.jwt_jwks_url:
            return {
                "id": "dev-student-1",
                "sub": "dev-student-1",
                "email": "student@prepos.local",
                "full_name": "Demo Student",
            }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    payload["id"] = payload["sub"]
    return payload
