"""Rate limiting: RPM (requests per minute) per org via Redis."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from aigate.core.errors import too_many_requests

if TYPE_CHECKING:
    from redis.asyncio import Redis

KEY_PREFIX = "ratelimit"
WINDOW_TTL_SECONDS = 120  # expire key after 2 min so keys don't pile up

# Lua: INCR key, set EXPIRE on first incr, return new count
_SCRIPT_INCR = """
local c = redis.call('INCR', KEYS[1])
if c == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return c
"""


def _retry_after_seconds() -> int:
    """Seconds until next minute (for Retry-After header)."""
    return max(1, 60 - (int(time.time()) % 60))


async def check_rate_limit(redis: Redis, org_id: str, rpm_limit: int) -> None:
    """
    Increment request count for org in current 1-min window. Raise 429 if over limit.
    """
    window = int(time.time()) // 60
    key = f"{KEY_PREFIX}:{org_id}:{window}"
    count = await redis.eval(_SCRIPT_INCR, 1, key, WINDOW_TTL_SECONDS)
    if count > rpm_limit:
        raise too_many_requests(retry_after_seconds=_retry_after_seconds())
