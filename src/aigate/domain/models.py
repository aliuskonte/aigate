from __future__ import annotations

from pydantic import BaseModel, Field


class Capabilities(BaseModel):
    supports_stream: bool = False
    supports_tools: bool = False
    supports_vision: bool = False
    supports_json_schema: bool = False
    max_context: int | None = None


class ModelInfo(BaseModel):
    id: str = Field(..., description="Provider-scoped model id")
    provider: str = Field(..., description="Provider name, e.g. openai/qwen")
    display_name: str | None = None
    capabilities: Capabilities = Field(default_factory=Capabilities)
