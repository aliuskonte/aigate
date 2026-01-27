from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from aigate.core.auth import AuthContext, get_auth_context
from aigate.core.deps import get_provider_registry
from aigate.core.errors import not_implemented
from aigate.core.logging import LogContext, with_context
from aigate.domain.chat import ChatRequest, ChatResponse, Choice, Message
from aigate.providers.registry import ProviderRegistry
from aigate.routing.router import route_and_call

router = APIRouter()
log = logging.getLogger(__name__)


@router.post("/chat/completions", response_model=ChatResponse)
async def chat_completions(
    request: Request,
    body: ChatRequest,
    auth: AuthContext = Depends(get_auth_context),
    registry: ProviderRegistry = Depends(get_provider_registry),
) -> ChatResponse:
    request_id = getattr(request.state, "request_id", None)
    logger = with_context(
        log,
        LogContext(request_id=request_id, org_id=auth.org_id),
    )

    if not registry.list_providers():
        raise not_implemented("No providers are registered yet")

    logger.info("chat.completions.request", extra={"model": body.model})
    resp = await route_and_call(registry, body)
    logger.info("chat.completions.response", extra={"model": resp.model})
    return resp


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
