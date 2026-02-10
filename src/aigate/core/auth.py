from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from aigate.core.config import Settings, get_settings
from aigate.core.deps import get_db_session
from aigate.core.errors import unauthorized
from aigate.storage.repos import get_active_api_key_by_hash, hash_api_key


@dataclass(frozen=True)
class AuthContext:
    org_id: str
    api_key: str


def _parse_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2:
        return None
    scheme, value = parts[0].lower(), parts[1].strip()
    if scheme != "bearer" or not value:
        return None
    return value


async def get_auth_context(
    authorization: str | None = Header(default=None, alias="Authorization"),
    settings: Settings = Depends(get_settings),
    session: AsyncSession | None = Depends(get_db_session),
) -> AuthContext:
    api_key = _parse_bearer(authorization)
    if not api_key:
        raise unauthorized("Missing or invalid Authorization header")

    # Preferred behaviour: validate key via Postgres when configured.
    if session is not None:
        row = await get_active_api_key_by_hash(session, key_hash=hash_api_key(api_key))
        if row is None:
            raise unauthorized("Invalid API key")
        return AuthContext(org_id=row.org_id, api_key=api_key)

    # Fallback: local/dev/test without DB configured.
    # `dev` is a backward-compatible alias of `local`.
    if settings.aigate_env in ("local", "dev", "test"):
        return AuthContext(org_id="dev-org", api_key=api_key)

    raise unauthorized("API key validation is not configured")
