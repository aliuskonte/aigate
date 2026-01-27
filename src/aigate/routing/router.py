from __future__ import annotations

from dataclasses import dataclass

from aigate.core.errors import bad_request
from aigate.domain.chat import ChatRequest, ChatResponse
from aigate.providers.registry import ProviderRegistry


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


async def route_and_call(registry: ProviderRegistry, req: ChatRequest) -> ChatResponse:
    target = parse_explicit_model(req.model)
    try:
        adapter = registry.get(target.provider)
    except KeyError as e:
        raise bad_request(f"Unknown provider: {target.provider}") from e

    # Keep canonical request; adapters may use target.provider_model later.
    # For MVP-skeleton, we just pass through req as-is.
    return await adapter.chat_completions(req)
