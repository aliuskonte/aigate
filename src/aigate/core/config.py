from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    aigate_env: Literal["dev", "test", "prod"] = "dev"
    aigate_log_level: str = "INFO"
    aigate_request_id_header: str = "X-Request-ID"

    # Providers (optional in skeleton)
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"

    qwen_api_key: str | None = None
    qwen_base_url: str | None = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

    # Storage/Redis
    database_url: str | None = None
    redis_url: str | None = None
    idempotency_ttl_seconds: int = 86400  # 24h
    rate_limit_rpm_default: int = 60  # requests per minute per org


@lru_cache
def get_settings() -> Settings:
    return Settings()
