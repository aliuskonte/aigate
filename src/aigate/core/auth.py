from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header

from aigate.core.config import Settings, get_settings
from aigate.core.errors import unauthorized


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


def get_auth_context(
    authorization: str | None = Header(default=None, alias="Authorization"),
    settings: Settings = Depends(get_settings),
) -> AuthContext:
    api_key = _parse_bearer(authorization)
    if not api_key:
        raise unauthorized("Missing or invalid Authorization header")

    # MVP-skeleton behaviour:
    # - in dev/test: accept any bearer key and use a fixed org_id
    # - in prod: real validation must be implemented via Postgres (api_keys table)
    if settings.aigate_env in ("dev", "test"):
        return AuthContext(org_id="dev-org", api_key=api_key)

    raise unauthorized("API key validation is not configured")
