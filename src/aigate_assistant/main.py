from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from qdrant_client.async_qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from aigate.core.logging import configure_logging
from aigate.core.middleware import RequestIdMiddleware
from aigate.storage.db import create_engine, create_sessionmaker
from aigate_assistant.api import api_router
from aigate_assistant.core.config import get_assistant_settings
from aigate_assistant.rag.embeddings import Embedder

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_assistant_settings()
    configure_logging(level="INFO")

    db_engine: AsyncEngine | None = None
    db_sessionmaker: async_sessionmaker | None = None
    redis_client = None
    qdrant: AsyncQdrantClient | None = None
    aigate_http: httpx.AsyncClient | None = None
    embedder: Embedder | None = None

    log.info("assistant.start")

    db_engine = create_engine(database_url=settings.database_url)
    db_sessionmaker = create_sessionmaker(db_engine)
    app.state.db_engine = db_engine
    app.state.db_sessionmaker = db_sessionmaker

    from redis.asyncio import Redis as RedisClient

    redis_client = RedisClient.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    app.state.redis = redis_client

    qdrant = AsyncQdrantClient(url=settings.assistant_qdrant_url)
    app.state.qdrant = qdrant

    headers = {}
    if settings.assistant_aigate_api_key:
        headers["Authorization"] = f"Bearer {settings.assistant_aigate_api_key}"

    aigate_http = httpx.AsyncClient(base_url=settings.assistant_aigate_base_url, headers=headers, timeout=60.0)
    app.state.aigate_http = aigate_http

    embedder = Embedder(model_name=settings.assistant_embed_model)
    app.state.embedder = embedder

    yield

    if aigate_http is not None:
        await aigate_http.aclose()
    if qdrant is not None:
        await qdrant.close()
    if redis_client is not None:
        await redis_client.aclose()
    if db_engine is not None:
        await db_engine.dispose()

    log.info("assistant.stop")


def create_app() -> FastAPI:
    app = FastAPI(title="AIGate Assistant", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestIdMiddleware)
    app.include_router(api_router)
    return app


app = create_app()

