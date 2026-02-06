from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal

from fastapi.testclient import TestClient

from aigate.domain.chat import ChatRequest, ChatResponse, Choice, Message, Usage
from aigate.main import create_app
from aigate.providers.base import ProviderAdapter
from aigate.providers.registry import ProviderRegistry


class FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = value

    async def eval(self, script: str, numkeys: int, *args: object) -> int:
        # For rate limiting in chat_completions; always allow.
        return 1


class DummyAdapter(ProviderAdapter):
    name = "qwen"

    async def list_models(self):
        return []

    async def stream_chat_completions(
        self, req: ChatRequest, timeout_seconds: float | None = None
    ) -> AsyncIterator[bytes]:
        yield b"data: [DONE]\n"

    async def chat_completions(
        self, req: ChatRequest, timeout_seconds: float | None = None
    ) -> ChatResponse:
        return ChatResponse(
            model=req.model,
            choices=[
                Choice(index=0, message=Message(role="assistant", content="ok"), finish_reason="stop"),
            ],
            usage=Usage(prompt_tokens=9, completion_tokens=11, total_tokens=20),
        )


def test_idempotency_cached_response_keeps_billed_cost() -> None:
    # Override deps so we don't need real DB/auth/provider clients.
    from aigate.core.auth import AuthContext
    from aigate.core.auth import get_auth_context
    from aigate.core.deps import get_db_session, get_provider_registry

    app = create_app()
    app.state.redis = FakeRedis()

    registry = ProviderRegistry()
    registry.register(DummyAdapter())

    def _auth_override():
        return AuthContext(org_id="org-1", api_key="agk_test")

    class _FakeSession:
        def add(self, _obj) -> None:  # noqa: ANN001
            return None

        async def flush(self) -> None:
            return None

        async def commit(self) -> None:
            return None

        async def rollback(self) -> None:
            return None

        async def close(self) -> None:
            return None

    async def _db_override():
        # Non-None so billing is computed before caching; implements minimal session API for ledger best-effort.
        yield _FakeSession()

    def _registry_override(_=None):
        return registry

    app.dependency_overrides[get_auth_context] = _auth_override
    app.dependency_overrides[get_provider_registry] = _registry_override
    app.dependency_overrides[get_db_session] = _db_override

    # Patch billing to return a deterministic billed_cost
    import aigate.api.chat_completions as cc

    async def _compute_billed_cost(*args, **kwargs):
        return (None, Decimal("0.00001550"))

    cc.compute_billed_cost = _compute_billed_cost  # type: ignore[assignment]

    client = TestClient(app)
    headers = {
        "Authorization": "Bearer agk_test",
        "Idempotency-Key": "demo-123",
    }
    body = {"model": "qwen:qwen-flash", "messages": [{"role": "user", "content": "Hi"}]}

    r1 = client.post("/v1/chat/completions", headers=headers, json=body)
    assert r1.status_code == 200
    j1 = r1.json()
    assert j1["usage"]["billed_cost"] == "0.00001550"

    r2 = client.post("/v1/chat/completions", headers=headers, json=body)
    assert r2.status_code == 200
    j2 = r2.json()
    assert j2["id"] == j1["id"]
    assert j2["usage"]["billed_cost"] == "0.00001550"

