from __future__ import annotations

import json

import httpx
import pytest

from aigate.domain.chat import ChatRequest, Message
from aigate.providers.qwen_adapter import QwenAdapter


@pytest.mark.asyncio
async def test_qwen_adapter_maps_chat_completion() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        assert request.headers.get("authorization") == "Bearer test-key"

        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == "qwen-plus"

        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-1",
                "created": 1735120033,
                "model": "qwen-plus",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "hello"},
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        headers={"Authorization": "Bearer test-key"},
    ) as client:
        adapter = QwenAdapter(client=client)
        resp = await adapter.chat_completions(
            ChatRequest(model="qwen-plus", messages=[Message(role="user", content="hi")])
        )

    assert resp.id == "chatcmpl-1"
    assert resp.model == "qwen-plus"
    assert resp.choices[0].message.content == "hello"
    assert resp.usage.total_tokens == 3


@pytest.mark.asyncio
async def test_qwen_adapter_list_models_404_returns_empty() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/models")
        return httpx.Response(404, json={"error": "not found"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        headers={"Authorization": "Bearer test-key"},
    ) as client:
        adapter = QwenAdapter(client=client)
        models = await adapter.list_models()

    assert models == []
