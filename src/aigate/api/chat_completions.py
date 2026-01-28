from __future__ import annotations

import hashlib
import json
import logging
import time

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from aigate.core.auth import AuthContext, get_auth_context
from aigate.core.config import get_settings
from aigate.core.deps import get_db_session, get_provider_registry
from aigate.core.errors import conflict, not_implemented
from aigate.limits.rate_limit import check_rate_limit
from aigate.core.logging import LogContext, with_context
from aigate.domain.chat import ChatRequest, ChatResponse, Choice, Message
from aigate.limits.idempotency import get_cached_response, set_cached_response
from aigate.providers.registry import ProviderRegistry
from aigate.routing.router import parse_explicit_model, route_and_call
from aigate.storage.repos import compute_billed_cost, create_request_log, create_usage_event

router = APIRouter()
log = logging.getLogger(__name__)


def _hash_request(body: ChatRequest) -> str:
    payload = body.model_dump(mode="json")
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@router.post("/chat/completions", response_model=ChatResponse)
async def chat_completions(
    request: Request,
    body: ChatRequest,
    auth: AuthContext = Depends(get_auth_context),
    registry: ProviderRegistry = Depends(get_provider_registry),
    session: AsyncSession | None = Depends(get_db_session),
) -> ChatResponse:
    request_id = getattr(request.state, "request_id", None)
    logger = with_context(
        log,
        LogContext(request_id=request_id, org_id=auth.org_id),
    )

    if not registry.list_providers():
        raise not_implemented("No providers are registered yet")

    target = parse_explicit_model(body.model)
    idem_key = request.headers.get("Idempotency-Key")
    request_hash = _hash_request(body)
    settings = get_settings()
    redis = getattr(request.app.state, "redis", None)

    # Idempotency: return cached response if same key + same body
    if idem_key and redis:
        cached = await get_cached_response(redis, auth.org_id, idem_key, request_hash)
        if cached == "conflict":
            raise conflict()
        if isinstance(cached, ChatResponse):
            request.state.idempotency_restored = True
            return cached

    if redis:
        await check_rate_limit(redis, auth.org_id, settings.rate_limit_rpm_default)

    started = time.perf_counter()
    status_code = 200
    resp: ChatResponse | None = None

    logger.info("chat.completions.request", extra={"provider": target.provider, "model": target.provider_model})
    try:
        resp = await route_and_call(registry, body)
        if idem_key and redis and resp is not None:
            await set_cached_response(
                redis,
                auth.org_id,
                idem_key,
                request_hash,
                resp,
                settings.idempotency_ttl_seconds,
            )
        return resp
    except Exception as e:
        # Best-effort capture of status code for ledger (FastAPI HTTPException has .status_code).
        status_code = getattr(e, "status_code", 500)
        raise
    finally:
        latency_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "chat.completions.done",
            extra={
                "provider": target.provider,
                "model": target.provider_model,
                "status": status_code,
                "latency_ms": latency_ms,
            },
        )

        if getattr(request.state, "idempotency_restored", False):
            return

        if session is not None and request_id:
            try:
                req_row = await create_request_log(
                    session,
                    request_id=str(request_id),
                    org_id=auth.org_id,
                    provider=target.provider,
                    model=target.provider_model,
                    status_code=int(status_code),
                    latency_ms=latency_ms,
                    request_hash=request_hash,
                    idempotency_key=idem_key,
                )

                if resp is not None and resp.usage is not None:
                    raw_cost, billed_cost = await compute_billed_cost(
                        session,
                        org_id=auth.org_id,
                        provider=target.provider,
                        model=target.provider_model,
                        prompt_tokens=resp.usage.prompt_tokens,
                        completion_tokens=resp.usage.completion_tokens,
                        raw_cost_from_provider=resp.usage.raw_cost,
                    )
                    if billed_cost is not None:
                        resp.usage.billed_cost = billed_cost

                    await create_usage_event(
                        session,
                        org_id=auth.org_id,
                        request_db_id=req_row.id,
                        provider=target.provider,
                        model=target.provider_model,
                        prompt_tokens=resp.usage.prompt_tokens,
                        completion_tokens=resp.usage.completion_tokens,
                        total_tokens=resp.usage.total_tokens,
                        raw_cost=raw_cost,
                        billed_cost=billed_cost,
                        currency=resp.usage.currency,
                    )

                await session.commit()
            except Exception:
                await session.rollback()


def make_echo_response(req: ChatRequest) -> ChatResponse:
    # Handy for early local testing, not wired by default.
    last_user = next((m.content for m in reversed(req.messages) if m.role == "user"), "")
    return ChatResponse(
        model=req.model,
        choices=[
            Choice(
                index=0,
                message=Message(role="assistant", content=f"echo: {last_user}"),
                finish_reason="stop",
            )
        ],
    )
