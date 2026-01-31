from __future__ import annotations

import pytest
from collections.abc import AsyncIterator

from aigate.domain.chat import ChatRequest, ChatResponse, Choice, Message
from aigate.providers.base import ProviderAdapter
from aigate.providers.registry import ProviderRegistry
from aigate.routing.router import route_and_call, route_and_stream


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

    async def stream_chat_completions(self, req: ChatRequest) -> AsyncIterator[bytes]:
        yield b"data: [DONE]\n"


@pytest.mark.asyncio
async def test_route_and_call_passes_provider_model_and_restores_prefix() -> None:
    registry = ProviderRegistry()
    registry.register(DummyAdapter())

    req = ChatRequest(model="qwen:qwen-plus", messages=[Message(role="user", content="hi")])
    resp = await route_and_call(registry, req)

    assert resp.model == "qwen:qwen-plus"


@pytest.mark.asyncio
async def test_route_and_stream_yields_from_adapter() -> None:
    registry = ProviderRegistry()
    registry.register(DummyAdapter())

    req = ChatRequest(model="qwen:qwen-plus", messages=[Message(role="user", content="hi")], stream=True)
    chunks = []
    async for chunk in route_and_stream(registry, req):
        chunks.append(chunk)

    assert chunks == [b"data: [DONE]\n"]
