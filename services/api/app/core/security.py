from __future__ import annotations

from typing import Any

import jwt
from jwt import PyJWKClient

from app.core.config import settings


def verify_supabase_jwt(token: str) -> dict[str, Any] | None:
    try:
        if settings.jwt_jwks_url:
            signing_key = PyJWKClient(settings.jwt_jwks_url).get_signing_key_from_jwt(token).key
            payload = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256", "ES256"],
                audience=settings.jwt_audience,
                issuer=settings.jwt_issuer or None,
                options={"require": ["sub", "exp"]},
            )
        elif settings.jwt_secret:
            payload = jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=["HS256"],
                audience=settings.jwt_audience,
                issuer=settings.jwt_issuer or None,
                options={"require": ["sub", "exp"]},
            )
        else:
            return None
    except Exception:
        return None
    if not payload.get("email"):
        return None
    return payload
