from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

from aigate.core.errors import bad_request
from aigate.domain.chat import ChatRequest, ChatResponse
from aigate.providers.registry import ProviderRegistry

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RoutedTarget:
    provider: str
    provider_model: str


def parse_explicit_model(model: str) -> RoutedTarget:
    # Expected: "<provider>:<model_id>"
    if ":" not in model:
        raise bad_request('Invalid model format. Expected "provider:model_id"')
    provider, provider_model = model.split(":", 1)
    provider = provider.strip()
    provider_model = provider_model.strip()
    if not provider or not provider_model:
        raise bad_request('Invalid model format. Expected "provider:model_id"')
    return RoutedTarget(provider=provider, provider_model=provider_model)


async def route_and_call(
    registry: ProviderRegistry, req: ChatRequest, timeout_seconds: float | None = None
) -> ChatResponse:
    target = parse_explicit_model(req.model)
    try:
        adapter = registry.get(target.provider)
    except KeyError as e:
        log.warning("Unknown provider: %s", target.provider)
        raise bad_request(f"Unknown provider: {target.provider}") from e

    provider_req = req.model_copy(update={"model": target.provider_model})
    resp = await adapter.chat_completions(provider_req, timeout_seconds=timeout_seconds)
    return resp.model_copy(update={"model": f"{target.provider}:{target.provider_model}"})


async def route_and_stream(
    registry: ProviderRegistry, req: ChatRequest, timeout_seconds: float | None = None
) -> AsyncIterator[bytes]:
    """Stream chat completions from the appropriate provider. Model prefix is applied by adapter."""
    target = parse_explicit_model(req.model)
    try:
        adapter = registry.get(target.provider)
    except KeyError as e:
        log.warning("Unknown provider: %s", target.provider)
        raise bad_request(f"Unknown provider: {target.provider}") from e

    provider_req = req.model_copy(update={"model": target.provider_model})
    async for chunk in adapter.stream_chat_completions(
        provider_req, timeout_seconds=timeout_seconds
    ):
        yield chunk
