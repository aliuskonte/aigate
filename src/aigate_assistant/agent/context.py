"""Context passed into the RAG graph (dependencies injected at build time)."""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from qdrant_client.async_qdrant_client import AsyncQdrantClient

from aigate_assistant.core.config import AssistantSettings
from aigate_assistant.rag.embeddings import Embedder


@dataclass
class RAGGraphContext:
    """Dependencies for the RAG graph nodes."""

    qdrant: AsyncQdrantClient
    embedder: Embedder
    aigate_http: httpx.AsyncClient
    settings: AssistantSettings
    aigate_api_key_override: str | None = None  # request-level X-AIGATE-API-KEY
