"""Tests for idempotency cache (get_cached_response / set_cached_response)."""

from __future__ import annotations

import pytest

from aigate.domain.chat import ChatResponse, Choice, Message
from aigate.limits.idempotency import get_cached_response, set_cached_response


class FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = value


@pytest.mark.asyncio
async def test_set_then_get_returns_same_response() -> None:
    redis = FakeRedis()
    resp = ChatResponse(
        model="qwen:qwen-turbo",
        choices=[Choice(index=0, message=Message(role="assistant", content="hi"), finish_reason="stop")],
    )
    await set_cached_response(redis, "org-1", "idem-abc", "hash1", resp, ttl_seconds=60)

    out = await get_cached_response(redis, "org-1", "idem-abc", "hash1")
    assert out is not None and out != "conflict"
    assert isinstance(out, ChatResponse)
    assert out.model == "qwen:qwen-turbo"
    assert out.choices[0].message.content == "hi"


@pytest.mark.asyncio
async def test_get_different_request_hash_returns_conflict() -> None:
    redis = FakeRedis()
    resp = ChatResponse(
        model="qwen:qwen-turbo",
        choices=[Choice(index=0, message=Message(role="assistant", content="hi"), finish_reason="stop")],
    )
    await set_cached_response(redis, "org-1", "idem-abc", "hash1", resp, ttl_seconds=60)

    out = await get_cached_response(redis, "org-1", "idem-abc", "hash2")
    assert out == "conflict"


@pytest.mark.asyncio
async def test_get_missing_key_returns_none() -> None:
    redis = FakeRedis()
    out = await get_cached_response(redis, "org-1", "idem-xyz", "hash1")
    assert out is None
