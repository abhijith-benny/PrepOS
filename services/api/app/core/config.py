from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = Field(default="development", alias="APP_ENV")
    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_anon_key: str = Field(default="", alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str = Field(default="", alias="SUPABASE_SERVICE_ROLE_KEY")
    jwt_secret: str = Field(default="", alias="JWT_SECRET")
    jwt_jwks_url: str = Field(default="", alias="JWT_JWKS_URL")
    jwt_issuer: str = Field(default="", alias="JWT_ISSUER")
    jwt_audience: str = Field(default="authenticated", alias="JWT_AUDIENCE")
    api_base_url: str = Field(default="http://localhost:8000", alias="API_BASE_URL")
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    groq_model: str = Field(default="openai/gpt-oss-120b", alias="GROQ_MODEL")
    admin_secret: str = Field(default="prepos-admin-secret-dev", alias="ADMIN_SECRET")
    srs_algorithm: str = Field(default="sm2", alias="SRS_ALGORITHM")
    srs_daily_new_limit: int = Field(default=10, alias="SRS_DAILY_NEW_LIMIT")
    srs_daily_review_limit: int = Field(default=50, alias="SRS_DAILY_REVIEW_LIMIT")
    srs_evidence_weight: float = Field(default=0.5, alias="SRS_EVIDENCE_WEIGHT")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
