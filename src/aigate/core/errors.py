from __future__ import annotations

from fastapi import HTTPException


def bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def conflict(detail: str = "Idempotency-Key already used with different request body") -> HTTPException:
    return HTTPException(status_code=409, detail=detail)


def unauthorized(detail: str = "Unauthorized") -> HTTPException:
    return HTTPException(status_code=401, detail=detail)


def not_implemented(detail: str = "Not implemented") -> HTTPException:
    return HTTPException(status_code=501, detail=detail)


def bad_gateway(detail: str = "Bad gateway") -> HTTPException:
    return HTTPException(status_code=502, detail=detail)


def gateway_timeout(detail: str = "Gateway timeout") -> HTTPException:
    return HTTPException(status_code=504, detail=detail)


def too_many_requests(
    detail: str = "Rate limit exceeded",
    retry_after_seconds: int | None = None,
) -> HTTPException:
    headers = {}
    if retry_after_seconds is not None:
        headers["Retry-After"] = str(retry_after_seconds)
    return HTTPException(status_code=429, detail=detail, headers=headers or None)
