from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any, Literal

import httpx

from aigate.core.errors import bad_gateway, gateway_timeout
from aigate.domain.chat import ChatRequest, ChatResponse, Choice, Message, Usage
from aigate.domain.models import Capabilities, ModelInfo
from aigate.providers.base import ProviderAdapter

log = logging.getLogger(__name__)


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
            log.exception("Qwen models request timed out: %s", e)
            raise gateway_timeout("Qwen models request timed out") from e
        except httpx.HTTPError as e:
            log.exception("Qwen models request failed: %s", e)
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

    def _serialize_content(self, content: str | list) -> str | list[dict[str, Any]]:
        if isinstance(content, str):
            return content
        return [p.model_dump(mode="json") for p in content]

    async def chat_completions(self, req: ChatRequest) -> ChatResponse:
        def _serialize_content(content: str | list) -> str | list[dict[str, Any]]:
            return self._serialize_content(content)

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
            log.exception("Qwen chat completion timed out: %s", e)
            raise gateway_timeout("Qwen chat completion timed out") from e
        except httpx.HTTPError as e:
            log.exception("Qwen chat completion failed: %s", e)
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

    async def stream_chat_completions(self, req: ChatRequest) -> AsyncIterator[bytes]:
        payload: dict[str, Any] = {
            "model": req.model,
            "messages": [
                {"role": m.role, "content": self._serialize_content(m.content)} for m in req.messages
            ],
            "stream": True,
        }
        if req.temperature is not None:
            payload["temperature"] = req.temperature

        try:
            async with self._client.stream("POST", "/chat/completions", json=payload) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    detail = body.decode("utf-8", errors="replace")[:500]
                    raise bad_gateway(f"Qwen returned {resp.status_code}: {detail}")

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_part = line[6:]
                    if data_part.strip() == "[DONE]":
                        yield b"data: [DONE]\n"
                        continue
                    try:
                        obj = json.loads(data_part)
                    except json.JSONDecodeError:
                        yield (line + "\n").encode("utf-8")
                        continue
                    if "model" in obj and obj["model"]:
                        obj["model"] = f"{self.name}:{obj['model']}"
                    yield ("data: " + json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
        except httpx.TimeoutException as e:
            log.exception("Qwen streaming timed out: %s", e)
            raise gateway_timeout("Qwen streaming timed out") from e
        except httpx.HTTPError as e:
            log.exception("Qwen streaming failed: %s", e)
            raise bad_gateway("Qwen streaming request failed") from e
