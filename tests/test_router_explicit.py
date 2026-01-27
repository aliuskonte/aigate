from __future__ import annotations

import pytest

from aigate.domain.chat import ChatRequest, ChatResponse, Choice, Message
from aigate.providers.base import ProviderAdapter
from aigate.providers.registry import ProviderRegistry
from aigate.routing.router import route_and_call


class DummyAdapter(ProviderAdapter):
    name = "qwen"

    async def list_models(self):
        return []

    async def chat_completions(self, req: ChatRequest) -> ChatResponse:
        # returns provider model (no "qwen:" prefix)
        return ChatResponse(
            model=req.model,
            choices=[Choice(index=0, message=Message(role="assistant", content="ok"), finish_reason="stop")],
        )


@pytest.mark.asyncio
async def test_route_and_call_passes_provider_model_and_restores_prefix() -> None:
    registry = ProviderRegistry()
    registry.register(DummyAdapter())

    req = ChatRequest(model="qwen:qwen-plus", messages=[Message(role="user", content="hi")])
    resp = await route_and_call(registry, req)

    assert resp.model == "qwen:qwen-plus"
