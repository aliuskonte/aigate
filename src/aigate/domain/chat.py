from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: list[Message]
    temperature: float | None = None
    stream: bool = False


class Usage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    raw_cost: Decimal | None = None
    billed_cost: Decimal | None = None
    currency: str = "USD"


class Choice(BaseModel):
    index: int = 0
    message: Message
    finish_reason: str | None = None


class ChatResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl_{uuid4().hex}")
    created: int = Field(default_factory=lambda: int(datetime.now(tz=timezone.utc).timestamp()))
    model: str
    choices: list[Choice]
    usage: Usage = Field(default_factory=Usage)
