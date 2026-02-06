from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from aigate.domain.chat import ChatRequest, ChatResponse
from aigate.domain.models import ModelInfo


class ProviderAdapter(ABC):
    name: str

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        raise NotImplementedError

    @abstractmethod
    async def chat_completions(
        self, req: ChatRequest, timeout_seconds: float | None = None
    ) -> ChatResponse:
        raise NotImplementedError

    @abstractmethod
    async def stream_chat_completions(
        self, req: ChatRequest, timeout_seconds: float | None = None
    ) -> AsyncIterator[bytes]:
        """Stream chat completions as SSE bytes. Yields complete SSE events (data: ...\\n)."""
        raise NotImplementedError
