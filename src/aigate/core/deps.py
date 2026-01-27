from __future__ import annotations

from fastapi import Request

from aigate.core.config import get_settings
from aigate.providers.qwen_adapter import QwenAdapter
from aigate.providers.registry import ProviderRegistry


def get_provider_registry(request: Request) -> ProviderRegistry:
    settings = get_settings()
    registry = ProviderRegistry()

    qwen_client = getattr(request.app.state, "qwen_http_client", None)
    if qwen_client is not None and settings.qwen_api_key:
        registry.register(QwenAdapter(client=qwen_client))

    return registry
