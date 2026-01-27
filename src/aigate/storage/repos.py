from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aigate.storage.models import ApiKey


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def key_prefix(api_key: str, length: int = 8) -> str:
    return api_key[:length]


async def get_active_api_key_by_hash(session: AsyncSession, *, key_hash: str) -> ApiKey | None:
    stmt = select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
