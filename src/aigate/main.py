from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from aigate import __version__
from aigate.api import api_router
from aigate.core.config import get_settings
from aigate.core.logging import configure_logging
from aigate.core.middleware import RequestIdMiddleware
from aigate.storage.db import create_engine, create_sessionmaker

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(level=settings.aigate_log_level)
    log.info("app.start", extra={"env": settings.aigate_env})
    qwen_client: httpx.AsyncClient | None = None
    db_engine: AsyncEngine | None = None
    db_sessionmaker: async_sessionmaker | None = None
    if settings.qwen_api_key and settings.qwen_base_url:
        qwen_client = httpx.AsyncClient(
            base_url=settings.qwen_base_url,
            headers={"Authorization": f"Bearer {settings.qwen_api_key}"},
            timeout=httpx.Timeout(60.0, connect=10.0),
        )
        app.state.qwen_http_client = qwen_client

    if settings.database_url:
        db_engine = create_engine(database_url=settings.database_url)
        db_sessionmaker = create_sessionmaker(db_engine)
        app.state.db_engine = db_engine
        app.state.db_sessionmaker = db_sessionmaker
    yield
    if qwen_client is not None:
        await qwen_client.aclose()
    if db_engine is not None:
        await db_engine.dispose()
    log.info("app.stop")


def create_app() -> FastAPI:
    app = FastAPI(title="AIGate", version=__version__, lifespan=lifespan)
    app.add_middleware(RequestIdMiddleware)
    app.include_router(api_router)
    return app


app = create_app()
