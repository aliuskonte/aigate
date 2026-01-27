from __future__ import annotations

from functools import lru_cache

from aigate.providers.registry import ProviderRegistry


@lru_cache
def get_provider_registry() -> ProviderRegistry:
    # MVP-skeleton: empty registry. Adapters are added in next iterations.
    return ProviderRegistry()
