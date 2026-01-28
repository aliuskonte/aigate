"""Tests for rate limiting (check_rate_limit)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from aigate.core.errors import too_many_requests
from aigate.limits.rate_limit import check_rate_limit


class FakeRedis:
    """Mock Redis with configurable eval return (request count in window)."""

    def __init__(self, incr_returns: list[int] | None = None) -> None:
        self._returns = iter(incr_returns) if incr_returns else iter([1])
        self.eval = AsyncMock(side_effect=self._eval)

    async def _eval(self, script: str, numkeys: int, *args: object) -> int:
        return next(self._returns, 1)


@pytest.mark.asyncio
async def test_check_rate_limit_under_limit_passes() -> None:
    redis = FakeRedis(incr_returns=[1])
    await check_rate_limit(redis, "org-1", 60)
    redis.eval.assert_called_once()


@pytest.mark.asyncio
async def test_check_rate_limit_at_limit_passes() -> None:
    redis = FakeRedis(incr_returns=[60])
    await check_rate_limit(redis, "org-1", 60)


@pytest.mark.asyncio
async def test_check_rate_limit_over_limit_raises_429() -> None:
    redis = FakeRedis(incr_returns=[61])
    with pytest.raises(type(too_many_requests())) as exc_info:
        await check_rate_limit(redis, "org-1", 60)
    assert exc_info.value.status_code == 429
    assert "Retry-After" in (exc_info.value.headers or {})
