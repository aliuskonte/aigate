from __future__ import annotations

from abc import ABC, abstractmethod

from aigate.domain.chat import ChatRequest, ChatResponse
from aigate.domain.models import ModelInfo


class ProviderAdapter(ABC):
    name: str

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        raise NotImplementedError

    @abstractmethod
    async def chat_completions(self, req: ChatRequest) -> ChatResponse:
        raise NotImplementedError
