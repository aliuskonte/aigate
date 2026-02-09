from __future__ import annotations

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_db_session(request: Request):
    sessionmaker = getattr(request.app.state, "db_sessionmaker", None)
    if sessionmaker is None:
        yield None
        return

    session: AsyncSession = sessionmaker()
    try:
        yield session
    finally:
        await session.close()


def get_redis(request: Request):
    return getattr(request.app.state, "redis", None)


def get_qdrant(request: Request):
    return getattr(request.app.state, "qdrant", None)


def get_aigate_http(request: Request):
    return getattr(request.app.state, "aigate_http", None)


def get_embedder(request: Request):
    return getattr(request.app.state, "embedder", None)

