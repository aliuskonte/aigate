from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from aigate_assistant.core.auth import require_assistant_api_key
from aigate_assistant.core.deps import (
    get_aigate_http,
    get_db_session,
    get_embedder,
    get_qdrant,
    get_redis,
)
from aigate_assistant.core.config import get_assistant_settings
from aigate_assistant.rag.embeddings import Embedder
from aigate_assistant.rag.qdrant_store import search as qdrant_search
from aigate_assistant.storage.repos import create_ingest_job, get_job, get_or_create_kb


router = APIRouter(dependencies=[Depends(require_assistant_api_key)])


class IngestRequest(BaseModel):
    kb_name: str = Field(default="default", min_length=1, max_length=200)


class IngestResponse(BaseModel):
    job_id: str
    kb_id: str
    status: str


class JobResponse(BaseModel):
    job_id: str
    kb_id: str
    status: str
    progress: float
    error: str | None = None
    stats: dict[str, Any] | None = None


class ChatRequest(BaseModel):
    kb_name: str = Field(default="default", min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=20_000)
    top_k: int | None = Field(default=None, ge=1, le=20)


class Source(BaseModel):
    source_uri: str
    score: float
    text_preview: str
    section_path: str | None = None


class ChatResponse(BaseModel):
    answer: str
    model: str
    sources: list[Source]


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/v1/assistant/ingest", response_model=IngestResponse)
async def ingest(
    body: IngestRequest,
    session: AsyncSession | None = Depends(get_db_session),
    redis=Depends(get_redis),
):
    if session is None:
        raise HTTPException(status_code=500, detail="DB is not configured")
    if redis is None:
        raise HTTPException(status_code=500, detail="Redis is not configured")

    settings = get_assistant_settings()
    kb = await get_or_create_kb(session=session, name=body.kb_name)
    job = await create_ingest_job(session=session, kb_id=kb.id)

    # Queue job for worker (Redis list)
    await redis.lpush(settings.assistant_redis_queue_key, job.id)

    return IngestResponse(job_id=job.id, kb_id=kb.id, status=job.status)


@router.get("/v1/assistant/ingest/jobs/{job_id}", response_model=JobResponse)
async def ingest_job_status(
    job_id: str,
    session: AsyncSession | None = Depends(get_db_session),
):
    if session is None:
        raise HTTPException(status_code=500, detail="DB is not configured")

    job = await get_job(session=session, job_id=job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobResponse(
        job_id=job.id,
        kb_id=job.kb_id,
        status=job.status,
        progress=float(job.progress),
        error=job.error,
        stats=job.stats,
    )


@router.post("/v1/assistant/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    session: AsyncSession | None = Depends(get_db_session),
    qdrant=Depends(get_qdrant),
    aigate_http=Depends(get_aigate_http),
    embedder: Embedder | None = Depends(get_embedder),
    x_aigate_api_key: str | None = Header(default=None, alias="X-AIGATE-API-KEY"),
):
    if session is None:
        raise HTTPException(status_code=500, detail="DB is not configured")
    if qdrant is None:
        raise HTTPException(status_code=500, detail="Qdrant is not configured")
    if aigate_http is None:
        raise HTTPException(status_code=500, detail="AIGate HTTP client is not configured")
    if embedder is None:
        raise HTTPException(status_code=500, detail="Embedder is not configured")

    settings = get_assistant_settings()
    kb = await get_or_create_kb(session=session, name=body.kb_name)

    top_k = body.top_k or settings.assistant_top_k
    query_vec = embedder.embed_query(body.message)
    try:
        chunks = await qdrant_search(
            qdrant=qdrant,
            collection=settings.assistant_qdrant_collection,
            query_vector=query_vec,
            top_k=top_k,
            kb_id=kb.id,
            candidate_k=settings.assistant_retrieval_candidate_k,
            dedupe_enabled=settings.assistant_dedupe_enabled,
            mmr_enabled=settings.assistant_mmr_enabled,
            mmr_lambda=settings.assistant_mmr_lambda,
        )
    except Exception as e:
        # Common case: alias/collection not created yet (run ingest first).
        raise HTTPException(
            status_code=409,
            detail=f"KB is not indexed yet (run /v1/assistant/ingest). Qdrant error: {e}",
        ) from e

    context_blocks: list[str] = []
    sources: list[Source] = []
    for i, c in enumerate(chunks, start=1):
        section_path = (c.payload or {}).get("section_path")
        prefix = f"[{i}] ({c.source_uri}"
        if section_path:
            prefix += f" — {section_path}"
        prefix += ")"
        context_blocks.append(f"{prefix}\n{c.text}")
        sources.append(
            Source(
                source_uri=c.source_uri,
                score=c.score,
                text_preview=c.text[:200].replace("\n", " ").strip(),
                section_path=str(section_path) if section_path else None,
            )
        )

    system_prompt = (
        "Ты внутренний ассистент по проекту AIGate.\n"
        "Отвечай кратко и технически.\n"
        "Если используешь контекст ниже — ссылайся на источники в формате [N].\n\n"
        "КОНТЕКСТ:\n"
        + ("\n\n".join(context_blocks) if context_blocks else "(пусто)")
    )

    payload = {
        "model": settings.assistant_llm_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": body.message},
        ],
        "temperature": 0.2,
    }

    req_headers = None
    # Allow request-level override for demos and multi-tenant usage.
    if x_aigate_api_key:
        req_headers = {"Authorization": f"Bearer {x_aigate_api_key}"}

    try:
        resp = await aigate_http.post("/v1/chat/completions", json=payload, headers=req_headers)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AIGate request failed: {e}") from e

    if resp.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AIGate error {resp.status_code}: {resp.text}",
        )

    data = resp.json()
    try:
        answer = data["choices"][0]["message"]["content"]
    except Exception:
        raise HTTPException(status_code=502, detail="Unexpected AIGate response format")

    return ChatResponse(answer=answer, model=settings.assistant_llm_model, sources=sources)

