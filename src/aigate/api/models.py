from __future__ import annotations

from fastapi import APIRouter, Depends

from aigate.core.deps import get_provider_registry
from aigate.domain.models import ModelInfo
from aigate.providers.registry import ProviderRegistry

router = APIRouter()


@router.get("/models", response_model=list[ModelInfo])
async def list_models(registry: ProviderRegistry = Depends(get_provider_registry)) -> list[ModelInfo]:
    return await registry.list_models()
