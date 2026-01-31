"""Tests for GET /v1/models fallback when provider returns 502/504."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import HTTPException
from fastapi.testclient import TestClient

from aigate.api.models import MODELS_FALLBACK_ALLOWLIST
from aigate.domain.chat import ChatRequest, ChatResponse
from aigate.domain.models import ModelInfo
from aigate.main import create_app
from aigate.providers.base import ProviderAdapter
from aigate.providers.registry import ProviderRegistry


class FailingModelsAdapter(ProviderAdapter):
    name = "qwen"

    async def list_models(self) -> list[ModelInfo]:
        raise HTTPException(status_code=502, detail="Bad gateway")

    async def chat_completions(self, req: ChatRequest) -> ChatResponse:
        raise NotImplementedError

    async def stream_chat_completions(self, req: ChatRequest) -> AsyncIterator[bytes]:
        raise NotImplementedError


def test_models_fallback_on_502() -> None:
    from aigate.core.deps import get_provider_registry

    app = create_app()
    registry = ProviderRegistry()
    registry.register(FailingModelsAdapter())

    def get_registry(_=None):
        return registry

    app.dependency_overrides[get_provider_registry] = get_registry
    client = TestClient(app)
    resp = client.get("/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    ids = [m["id"] for m in data]
    assert ids == [m.id for m in MODELS_FALLBACK_ALLOWLIST]
    assert all(m["provider"] == "qwen" for m in data)


def test_models_fallback_on_504() -> None:
    from aigate.core.deps import get_provider_registry

    class TimeoutAdapter(ProviderAdapter):
        name = "qwen"

        async def list_models(self) -> list[ModelInfo]:
            raise HTTPException(status_code=504, detail="Gateway timeout")

        async def chat_completions(self, req: ChatRequest) -> ChatResponse:
            raise NotImplementedError

        async def stream_chat_completions(self, req: ChatRequest) -> AsyncIterator[bytes]:
            raise NotImplementedError

    app = create_app()
    registry = ProviderRegistry()
    registry.register(TimeoutAdapter())

    def get_registry(_=None):
        return registry

    app.dependency_overrides[get_provider_registry] = get_registry
    client = TestClient(app)
    resp = client.get("/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert [m["id"] for m in data] == [m.id for m in MODELS_FALLBACK_ALLOWLIST]
