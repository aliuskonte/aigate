from fastapi import APIRouter

from aigate_assistant.api.routes import router as assistant_router

api_router = APIRouter()
api_router.include_router(assistant_router)

