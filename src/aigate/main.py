from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from aigate import __version__
from aigate.api import api_router
from aigate.core.config import get_settings
from aigate.core.logging import configure_logging
from aigate.core.middleware import RequestIdMiddleware

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(level=settings.aigate_log_level)
    log.info("app.start", extra={"env": settings.aigate_env})
    yield
    log.info("app.stop")


def create_app() -> FastAPI:
    app = FastAPI(title="AIGate", version=__version__, lifespan=lifespan)
    app.add_middleware(RequestIdMiddleware)
    app.include_router(api_router)
    return app


app = create_app()
