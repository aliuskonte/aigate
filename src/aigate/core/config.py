from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    # `local` is the preferred name for development environment.
    # Backward-compatibility: `dev` is accepted as an alias of `local`.
    aigate_env: Literal["local", "dev", "test", "prod"] = "local"
    aigate_log_level: str = "INFO"
    aigate_request_id_header: str = "X-Request-ID"

    # Providers (optional in skeleton)
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"

    qwen_api_key: str | None = None
    qwen_base_url: str | None = "https://dashscope-us.aliyuncs.com/compatible-mode/v1"
    qwen_timeout_default_seconds: float = 120.0
    qwen_timeout_max_seconds: float = 300.0
    qwen_default_input_price_per_1k: Decimal = Decimal("0.0005")
    qwen_default_output_price_per_1k: Decimal = Decimal("0.001")

    # Storage/Redis
    postgres_user: str = "postgres"
    postgres_password: str | None = None
    postgres_db: str = "aigate"
    database_url: str | None = None
    redis_url: str | None = None
    idempotency_ttl_seconds: int = 86400  # 24h
    rate_limit_rpm_default: int = 60  # requests per minute per org


@lru_cache
def get_settings() -> Settings:
    return Settings()
