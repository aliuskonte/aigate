"""Tests for vision (image) content in chat completions."""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from aigate.domain.chat import ChatRequest, ChatResponse, Choice, Message, Usage
from aigate.main import create_app
from aigate.providers.base import ProviderAdapter
from aigate.providers.registry import ProviderRegistry


class DummyVisionAdapter(ProviderAdapter):
    name = "qwen"

    async def list_models(self):
        return []

    async def chat_completions(self, req: ChatRequest) -> ChatResponse:
        # Echo back that we received vision content
        content = req.messages[-1].content if req.messages else ""
        if isinstance(content, list):
            text_parts = [p.text for p in content if hasattr(p, "text")]
            received = " ".join(text_parts) + " [vision]"
        else:
            received = str(content)
        return ChatResponse(
            model=req.model,
            choices=[
                Choice(
                    index=0,
                    message=Message(role="assistant", content=received),
                    finish_reason="stop",
                ),
            ],
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )


def test_api_accepts_vision_content_image_url() -> None:
    """API accepts content as list with text + image_url."""
    from aigate.core.auth import AuthContext, get_auth_context
    from aigate.core.deps import get_db_session, get_provider_registry

    import aigate.api.chat_completions as cc

    app = create_app()
    registry = ProviderRegistry()
    registry.register(DummyVisionAdapter())

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

    async def _compute_billed_cost(*args, **kwargs):
        return (None, Decimal("0.00001"))

    app.dependency_overrides[get_auth_context] = _auth_override
    app.dependency_overrides[get_provider_registry] = _registry_override
    app.dependency_overrides[get_db_session] = _db_override
    cc.compute_billed_cost = _compute_billed_cost  # type: ignore[assignment]

    client = TestClient(app)
    body = {
        "model": "qwen:qwen-vl-max",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What's in the image?"},
                    {"type": "image_url", "image_url": {"url": "https://example.com/img.png"}},
                ],
            }
        ],
    }
    r = client.post("/v1/chat/completions", headers={"Authorization": "Bearer agk_test"}, json=body)
    assert r.status_code == 200
    j = r.json()
    assert "What's in the image? [vision]" in j["choices"][0]["message"]["content"]
