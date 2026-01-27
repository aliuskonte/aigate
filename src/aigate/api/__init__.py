from fastapi import APIRouter

from aigate.api.chat_completions import router as chat_completions_router
from aigate.api.health import router as health_router
from aigate.api.models import router as models_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(models_router, prefix="/v1")
api_router.include_router(chat_completions_router, prefix="/v1")

__all__ = ["api_router"]
