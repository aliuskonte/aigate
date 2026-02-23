from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class AssistantSettings(BaseSettings):
    """
    Settings for `assistant-api` and `assistant-worker`.

    NOTE: We intentionally keep env_prefix="" to reuse the repo's `.env` pattern.
    """

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    # Security
    assistant_api_key: str | None = None

    # Dependencies
    database_url: str
    redis_url: str

    assistant_aigate_base_url: str = "http://aigate:8000"
    assistant_aigate_api_key: str | None = None
    assistant_llm_model: str = "qwen:qwen-plus"

    assistant_qdrant_url: str = "http://qdrant:6333"
    assistant_qdrant_collection: str = "aigate_kb_default"

    # Supported by fastembed (see TextEmbedding.list_supported_models()).
    # Default prioritizes multilingual quality (RU/EN).
    assistant_embed_model: str = "intfloat/multilingual-e5-large"

    # Ingestion
    assistant_redis_queue_key: str = "assistant:ingest:queue"

    # RAG defaults
    assistant_chunk_size_chars: int = 1200
    assistant_chunk_overlap_chars: int = 200
    assistant_chunk_size_tokens: int = 420
    assistant_chunk_overlap_tokens: int = 80
    assistant_top_k: int = 6
    assistant_retrieval_candidate_k: int = 24
    assistant_dedupe_enabled: bool = True
    assistant_mmr_enabled: bool = True
    assistant_mmr_lambda: float = 0.65

    # Indexing behaviour
    assistant_incremental_indexing: bool = True
    assistant_cleanup_stale: bool = True
    assistant_cleanup_changed: bool = True

    # Agent tools (optional: leave empty to disable)
    assistant_loki_url: str = ""  # e.g. http://loki:3100
    assistant_prometheus_url: str = ""  # e.g. http://prometheus:9090


@lru_cache
def get_assistant_settings() -> AssistantSettings:
    return AssistantSettings()

