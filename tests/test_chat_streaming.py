"""Tests for streaming chat completions (stream=true)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from aigate.domain.chat import ChatRequest, ChatResponse, Choice, Message
from aigate.main import create_app
from aigate.providers.base import ProviderAdapter
from aigate.providers.registry import ProviderRegistry


class StreamingDummyAdapter(ProviderAdapter):
    name = "qwen"

    async def list_models(self):
        return []

    async def chat_completions(self, req: ChatRequest) -> ChatResponse:
        return ChatResponse(
            model=req.model,
            choices=[Choice(index=0, message=Message(role="assistant", content="ok"), finish_reason="stop")],
        )

    async def stream_chat_completions(self, req: ChatRequest) -> AsyncIterator[bytes]:
        # Adapter adds provider prefix to model (like QwenAdapter)
        model = f"{self.name}:{req.model}"
        yield (f'data: {{"id":"c1","model":"{model}","choices":[{{"index":0,"delta":{{"role":"assistant","content":""}}}}]}}\n').encode()
        yield (f'data: {{"id":"c1","model":"{model}","choices":[{{"index":0,"delta":{{"content":"Hello"}}}}]}}\n').encode()
        yield (f'data: {{"id":"c1","model":"{model}","choices":[{{"index":0,"delta":{{}},"finish_reason":"stop"}}],"usage":{{"prompt_tokens":2,"completion_tokens":1}}}}\n').encode()
        yield b"data: [DONE]\n"


def test_chat_completions_streaming_returns_sse() -> None:
    """Streaming request returns SSE with model prefix and chunks."""
    from aigate.core.auth import AuthContext, get_auth_context
    from aigate.core.deps import get_db_session, get_provider_registry

    app = create_app()
    registry = ProviderRegistry()
    registry.register(StreamingDummyAdapter())

    def _auth_override():
        return AuthContext(org_id="org-1", api_key="agk_test")

    class _FakeSession:
        def add(self, _obj) -> None:
            pass

        async def flush(self) -> None:
            pass

        async def commit(self) -> None:
            pass

        async def rollback(self) -> None:
            pass

        async def close(self) -> None:
            pass

    async def _db_override():
        yield _FakeSession()

    def _registry_override(_=None):
        return registry

    app.dependency_overrides[get_auth_context] = _auth_override
    app.dependency_overrides[get_provider_registry] = _registry_override
    app.dependency_overrides[get_db_session] = _db_override

    client = TestClient(app)
    body = {
        "model": "qwen:qwen-plus",
        "messages": [{"role": "user", "content": "Hi"}],
        "stream": True,
    }
    r = client.post("/v1/chat/completions", headers={"Authorization": "Bearer agk_test"}, json=body)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("text/event-stream")

    chunks = r.text.strip().split("\n")
    data_lines = [c for c in chunks if c.startswith("data: ")]
    assert len(data_lines) == 4
    assert "qwen:qwen-plus" in data_lines[0]
    assert data_lines[3] == "data: [DONE]"


def test_chat_completions_streaming_rejects_idempotency_key() -> None:
    """Streaming with Idempotency-Key returns 400."""
    from aigate.core.auth import AuthContext, get_auth_context
    from aigate.core.deps import get_db_session, get_provider_registry

    app = create_app()
    registry = ProviderRegistry()
    registry.register(StreamingDummyAdapter())

    def _auth_override():
        return AuthContext(org_id="org-1", api_key="agk_test")

    async def _db_override():
        yield None

    def _registry_override(_=None):
        return registry

    app.dependency_overrides[get_auth_context] = _auth_override
    app.dependency_overrides[get_provider_registry] = _registry_override
    app.dependency_overrides[get_db_session] = _db_override

    client = TestClient(app)
    body = {"model": "qwen:qwen-plus", "messages": [{"role": "user", "content": "Hi"}], "stream": True}
    r = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer agk_test", "Idempotency-Key": "key-123"},
        json=body,
    )
    assert r.status_code == 400
    assert "idempotency" in r.json().get("detail", "").lower()
