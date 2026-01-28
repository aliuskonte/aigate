from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from fastapi import HTTPException

from aigate.core.deps import get_provider_registry
from aigate.domain.models import Capabilities, ModelInfo
from aigate.providers.registry import ProviderRegistry

router = APIRouter()
log = logging.getLogger(__name__)

# Fallback when provider GET /models is unavailable (502/504)
MODELS_FALLBACK_ALLOWLIST: list[ModelInfo] = [
    ModelInfo(
        id="qwen-turbo",
        provider="qwen",
        display_name="qwen-turbo",
        capabilities=Capabilities(supports_stream=True, supports_tools=True, supports_vision=True, supports_json_schema=True),
    ),
    ModelInfo(
        id="qwen-plus",
        provider="qwen",
        display_name="qwen-plus",
        capabilities=Capabilities(supports_stream=True, supports_tools=True, supports_vision=True, supports_json_schema=True),
    ),
    ModelInfo(
        id="qwen-max",
        provider="qwen",
        display_name="qwen-max",
        capabilities=Capabilities(supports_stream=True, supports_tools=True, supports_vision=True, supports_json_schema=True),
    ),
]


@router.get("/models", response_model=list[ModelInfo])
async def list_models(registry: ProviderRegistry = Depends(get_provider_registry)) -> list[ModelInfo]:
    try:
        return await registry.list_models()
    except HTTPException as e:
        if e.status_code in (502, 504):
            log.warning("models.fallback_used", extra={"status_code": e.status_code, "detail": e.detail})
            return MODELS_FALLBACK_ALLOWLIST
        raise
