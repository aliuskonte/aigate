"""Idempotency: cache ChatResponse by Idempotency-Key to avoid double billing/usage."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from aigate.domain.chat import ChatResponse

if TYPE_CHECKING:
    from redis.asyncio import Redis

KEY_PREFIX = "idempotency"


def _cache_key(org_id: str, idem_key: str) -> str:
    return f"{KEY_PREFIX}:{org_id}:{idem_key}"


async def get_cached_response(
    redis: Redis,
    org_id: str,
    idem_key: str,
    request_hash: str,
) -> ChatResponse | str | None:
    """
    Return cached ChatResponse if key exists and request_hash matches.
    Return "conflict" if key exists but request_hash differs (caller should 409).
    Return None if key missing.
    """
    key = _cache_key(org_id, idem_key)
    raw = await redis.get(key)
    if raw is None:
        return None
    data = json.loads(raw)
    stored_hash = data.get("request_hash")
    if stored_hash != request_hash:
        return "conflict"
    return ChatResponse.model_validate(data["response"])


async def set_cached_response(
    redis: Redis,
    org_id: str,
    idem_key: str,
    request_hash: str,
    response: ChatResponse,
    ttl_seconds: int,
) -> None:
    """Store response in Redis with TTL."""
    key = _cache_key(org_id, idem_key)
    payload = {
        "request_hash": request_hash,
        "response": response.model_dump(mode="json"),
    }
    await redis.set(key, json.dumps(payload), ex=ttl_seconds)
