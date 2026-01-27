from __future__ import annotations

from dataclasses import dataclass, field

from aigate.domain.models import ModelInfo
from aigate.providers.base import ProviderAdapter


@dataclass
class ProviderRegistry:
    _providers: dict[str, ProviderAdapter] = field(default_factory=dict)

    def register(self, adapter: ProviderAdapter) -> None:
        self._providers[adapter.name] = adapter

    def get(self, provider: str) -> ProviderAdapter:
        return self._providers[provider]

    def list_providers(self) -> list[str]:
        return sorted(self._providers.keys())

    async def list_models(self) -> list[ModelInfo]:
        items: list[ModelInfo] = []
        for adapter in self._providers.values():
            items.extend(await adapter.list_models())
        return items
