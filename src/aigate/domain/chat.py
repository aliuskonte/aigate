from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal, Union
from uuid import uuid4

from pydantic import BaseModel, Field


class TextPart(BaseModel):
    """OpenAI-compatible text content part."""

    type: Literal["text"] = "text"
    text: str


class ImageUrl(BaseModel):
    """Image URL: https://... or data:image/<type>;base64,..."""

    url: str


class ImageUrlPart(BaseModel):
    """OpenAI-compatible image content part."""

    type: Literal["image_url"] = "image_url"
    image_url: ImageUrl


ContentPart = Annotated[Union[TextPart, ImageUrlPart], Field(discriminator="type")]


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str | list[ContentPart]


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
