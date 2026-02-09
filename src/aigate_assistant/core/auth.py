from __future__ import annotations

from fastapi import Header, HTTPException, status

from aigate_assistant.core.config import get_assistant_settings


def require_assistant_api_key(authorization: str | None = Header(default=None)) -> None:
    """
    Optional auth for internal demo.

    If ASSISTANT_API_KEY is set, require `Authorization: Bearer <key>`.
    If not set, allow all requests.
    """

    settings = get_assistant_settings()
    if not settings.assistant_api_key:
        return

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization: Bearer token",
        )

    token = authorization.split(" ", 1)[1].strip()
    if token != settings.assistant_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

