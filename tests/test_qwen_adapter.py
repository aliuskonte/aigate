from __future__ import annotations

import contextlib
import json
from unittest.mock import MagicMock

import httpx
import pytest

from aigate.domain.chat import ChatRequest, ImageUrl, ImageUrlPart, Message, TextPart
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
async def test_qwen_adapter_vision_content_image_url() -> None:
    """Vision: content as list with text + image_url (URL) is passed through to provider."""
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        msgs = payload["messages"]
        assert len(msgs) == 1
        content = msgs[0]["content"]
        assert isinstance(content, list)
        assert content[0] == {"type": "text", "text": "What's in the image?"}
        assert content[1]["type"] == "image_url"
        assert content[1]["image_url"]["url"] == "https://example.com/img.png"

        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-vl-1",
                "created": 1735120033,
                "model": "qwen-vl-max",
                "choices": [
                    {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "A dog."}}
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 2, "total_tokens": 102},
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
            ChatRequest(
                model="qwen-vl-max",
                messages=[
                    Message(
                        role="user",
                        content=[
                            TextPart(text="What's in the image?"),
                            ImageUrlPart(image_url=ImageUrl(url="https://example.com/img.png")),
                        ],
                    )
                ],
            )
        )

    assert resp.choices[0].message.content == "A dog."


@pytest.mark.asyncio
async def test_qwen_adapter_vision_content_base64() -> None:
    """Vision: image_url with data:image/...;base64,... is passed through."""
    base64_data = "data:image/png;base64,iVBORw0KGgo="

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        content = payload["messages"][0]["content"]
        assert content[1]["image_url"]["url"] == base64_data

        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-vl-2",
                "created": 1735120033,
                "model": "qwen-vl-max",
                "choices": [
                    {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}
                ],
                "usage": {"prompt_tokens": 50, "completion_tokens": 1, "total_tokens": 51},
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
            ChatRequest(
                model="qwen-vl-max",
                messages=[
                    Message(
                        role="user",
                        content=[
                            TextPart(text="Describe"),
                            ImageUrlPart(image_url=ImageUrl(url=base64_data)),
                        ],
                    )
                ],
            )
        )

    assert resp.choices[0].message.content == "ok"


@pytest.mark.asyncio
async def test_qwen_adapter_stream_chat_completions() -> None:
    """Streaming: yields SSE chunks with model prefix applied."""
    lines = [
        'data: {"id":"c1","model":"qwen-plus","choices":[{"index":0,"delta":{"role":"assistant","content":""}}]}',
        'data: {"id":"c1","model":"qwen-plus","choices":[{"index":0,"delta":{"content":"Hi"}}]}',
        'data: {"id":"c1","model":"qwen-plus","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":1}}',
        "data: [DONE]",
    ]

    async def aiter_lines():
        for line in lines:
            yield line

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.aiter_lines = aiter_lines

    @contextlib.asynccontextmanager
    async def fake_stream(*args, **kwargs):
        yield mock_resp

    transport = httpx.MockTransport(lambda r: httpx.Response(200))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        headers={"Authorization": "Bearer test-key"},
    ) as client:
        adapter = QwenAdapter(client=client)
        adapter._client.stream = fake_stream
        chunks = []
        async for chunk in adapter.stream_chat_completions(
            ChatRequest(model="qwen-plus", messages=[Message(role="user", content="hi")], stream=True)
        ):
            chunks.append(chunk)

    assert len(chunks) == 4
    assert b"qwen:qwen-plus" in chunks[0]
    assert chunks[3] == b"data: [DONE]\n"


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
