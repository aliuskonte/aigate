from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any, Literal

import httpx

from aigate.core.errors import bad_gateway, gateway_timeout, not_implemented
from aigate.domain.chat import ChatRequest, ChatResponse, Choice, Message, Usage
from aigate.domain.models import Capabilities, ModelInfo
from aigate.providers.base import ProviderAdapter


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _as_role(value: Any) -> Literal["system", "user", "assistant"]:
    if value in ("system", "user", "assistant"):
        return value
    return "assistant"


class QwenAdapter(ProviderAdapter):
    name = "qwen"

    def __init__(self, *, client: httpx.AsyncClient):
        self._client = client

    async def list_models(self) -> list[ModelInfo]:
        try:
            resp = await self._client.get("/models")
        except httpx.TimeoutException as e:
            raise gateway_timeout("Qwen models request timed out") from e
        except httpx.HTTPError as e:
            raise bad_gateway("Qwen models request failed") from e

        if resp.status_code == 404:
            return []

        if resp.status_code >= 400:
            raise bad_gateway(f"Qwen models request failed ({resp.status_code})")

        data = resp.json()
        items = data.get("data") or []

        caps = Capabilities(
            supports_stream=True,
            supports_tools=True,
            supports_vision=True,
            supports_json_schema=True,
        )

        out: list[ModelInfo] = []
        for item in items:
            model_id = item.get("id")
            if not model_id:
                continue
            out.append(ModelInfo(id=str(model_id), provider=self.name, display_name=str(model_id), capabilities=caps))
        return out

    async def chat_completions(self, req: ChatRequest) -> ChatResponse:
        if req.stream:
            raise not_implemented("Streaming is not implemented in MVP yet")

        def _serialize_content(content: str | list) -> str | list[dict[str, Any]]:
            if isinstance(content, str):
                return content
            return [p.model_dump(mode="json") for p in content]

        payload: dict[str, Any] = {
            "model": req.model,
            "messages": [
                {"role": m.role, "content": _serialize_content(m.content)} for m in req.messages
            ],
        }
        if req.temperature is not None:
            payload["temperature"] = req.temperature

        try:
            resp = await self._client.post("/chat/completions", json=payload)
        except httpx.TimeoutException as e:
            raise gateway_timeout("Qwen chat completion timed out") from e
        except httpx.HTTPError as e:
            raise bad_gateway("Qwen chat completion request failed") from e

        if resp.status_code >= 400:
            detail = _safe_text(resp.text)
            if len(detail) > 500:
                detail = detail[:500] + "…"
            raise bad_gateway(f"Qwen returned {resp.status_code}: {detail}")

        data = resp.json()
        usage = data.get("usage") or {}
        out_usage = Usage(
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )

        choices: list[Choice] = []
        for ch in data.get("choices") or []:
            msg = ch.get("message") or {}
            choices.append(
                Choice(
                    index=int(ch.get("index") or 0),
                    message=Message(role=_as_role(msg.get("role")), content=_safe_text(msg.get("content"))),
                    finish_reason=ch.get("finish_reason"),
                )
            )

        if not choices:
            raise bad_gateway(f"Qwen returned no choices: {json.dumps(data)[:500]}")

        response_id = _safe_text(data.get("id")) or f"chatcmpl_{uuid4().hex}"
        created = int(data.get("created") or int(datetime.now(tz=timezone.utc).timestamp()))

        return ChatResponse(
            id=response_id,
            created=created,
            model=_safe_text(data.get("model")) or req.model,
            choices=choices,
            usage=out_usage,
        )
