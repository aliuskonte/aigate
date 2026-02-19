"""Agent run/trace and ticket API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aigate.storage.models import AssistantTicket
from aigate_assistant.agent.context import RAGGraphContext
from aigate_assistant.agent.graph import build_rag_graph
from aigate_assistant.core.auth import require_assistant_api_key
from aigate_assistant.core.deps import (
    get_aigate_http,
    get_db_session,
    get_embedder,
    get_qdrant,
)
from aigate_assistant.core.config import get_assistant_settings
from aigate_assistant.rag.embeddings import Embedder
from aigate_assistant.storage.repos import (
    add_agent_run_step,
    create_agent_run,
    create_ticket,
    get_agent_run,
    get_or_create_kb,
    list_agent_run_steps,
    set_agent_run_finished,
)

router = APIRouter(prefix="/v1/agent", dependencies=[Depends(require_assistant_api_key)])


class AgentRunRequest(BaseModel):
    kb_name: str = Field(default="default", min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=20_000)
    create_ticket: bool = Field(default=False, description="Create a ticket with run result for audit")


class AgentRunResponse(BaseModel):
    run_id: str
    ticket_id: str | None = None


class StepOut(BaseModel):
    node_name: str
    step_order: int
    started_at: str
    finished_at: str | None
    latency_ms: int | None
    input_snapshot: dict[str, Any] | None
    output_snapshot: dict[str, Any] | None
    error: str | None


class AgentRunDetailResponse(BaseModel):
    run_id: str
    kb_id: str
    status: str
    query: str
    input_payload: dict[str, Any] | None
    output_payload: dict[str, Any] | None
    error: str | None
    created_at: str
    finished_at: str | None
    trace: list[StepOut]
    ticket_id: str | None


@router.post("/run", response_model=AgentRunResponse)
async def run_agent(
    body: AgentRunRequest,
    session: AsyncSession | None = Depends(get_db_session),
    qdrant=Depends(get_qdrant),
    aigate_http=Depends(get_aigate_http),
    embedder: Embedder | None = Depends(get_embedder),
    x_aigate_api_key: str | None = Header(default=None, alias="X-AIGATE-API-KEY"),
):
    if session is None:
        raise HTTPException(status_code=500, detail="DB is not configured")
    if qdrant is None or aigate_http is None or embedder is None:
        raise HTTPException(status_code=500, detail="Qdrant or AIGate or Embedder not configured")

    settings = get_assistant_settings()
    kb = await get_or_create_kb(session=session, name=body.kb_name)

    run = await create_agent_run(
        session=session,
        kb_id=kb.id,
        query=body.message,
        input_payload={"kb_name": body.kb_name, "create_ticket": body.create_ticket},
    )

    ctx = RAGGraphContext(
        qdrant=qdrant,
        embedder=embedder,
        aigate_http=aigate_http,
        settings=settings,
        aigate_api_key_override=x_aigate_api_key,
    )
    graph = build_rag_graph(ctx)
    try:
        final = await graph.ainvoke({"query": body.message, "kb_id": kb.id})
    except Exception as e:
        await set_agent_run_finished(
            session=session,
            run_id=run.id,
            status="failed",
            error=str(e),
        )
        raise HTTPException(status_code=502, detail=f"Graph execution failed: {e}") from e

    steps = final.get("steps") or []
    for i, st in enumerate(steps):
        started_ts = st.get("started_at") or 0
        finished_ts = st.get("finished_at")
        started_dt = datetime.fromtimestamp(started_ts, tz=timezone.utc) if isinstance(started_ts, (int, float)) else datetime.now(tz=timezone.utc)
        finished_dt = datetime.fromtimestamp(finished_ts, tz=timezone.utc) if isinstance(finished_ts, (int, float)) else None
        await add_agent_run_step(
            session=session,
            run_id=run.id,
            node_name=st.get("node_name") or "unknown",
            step_order=i,
            started_at=started_dt,
            finished_at=finished_dt,
            latency_ms=st.get("latency_ms"),
            input_snapshot=st.get("input_snapshot"),
            output_snapshot=st.get("output_snapshot"),
            error=st.get("error"),
        )

    run_error = final.get("error")
    if run_error:
        await set_agent_run_finished(
            session=session,
            run_id=run.id,
            status="failed",
            output_payload={
                "formatted_answer": final.get("formatted_answer"),
                "sources": final.get("sources"),
                "steps_count": len(steps),
            },
            error=run_error,
        )
    else:
        await set_agent_run_finished(
            session=session,
            run_id=run.id,
            status="succeeded",
            output_payload={
                "formatted_answer": final.get("formatted_answer"),
                "answer": final.get("answer"),
                "model": final.get("model"),
                "sources": final.get("sources"),
                "steps_count": len(steps),
            },
        )

    ticket_id = None
    if body.create_ticket and not run_error:
        ticket = await create_ticket(
            session=session,
            run_id=run.id,
            ticket_type="run_summary",
            title=f"Agent run: {body.message[:80]}...",
            context={
                "run_id": run.id,
                "query": body.message[:1000],
                "answer_preview": (final.get("formatted_answer") or "")[:500],
                "sources_count": len(final.get("sources") or []),
            },
            severity="normal",
        )
        ticket_id = ticket.id

    return AgentRunResponse(run_id=run.id, ticket_id=ticket_id)


@router.get("/runs/{run_id}", response_model=AgentRunDetailResponse)
async def get_run(
    run_id: str,
    session: AsyncSession | None = Depends(get_db_session),
):
    if session is None:
        raise HTTPException(status_code=500, detail="DB is not configured")

    run = await get_agent_run(session=session, run_id=run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    steps = await list_agent_run_steps(session=session, run_id=run_id)
    ticket_row = await session.scalar(
        select(AssistantTicket).where(AssistantTicket.run_id == run_id).limit(1)
    )
    ticket_id = str(ticket_row.id) if ticket_row else None

    trace = [
        StepOut(
            node_name=s.node_name,
            step_order=s.step_order,
            started_at=s.started_at.isoformat() if s.started_at else "",
            finished_at=s.finished_at.isoformat() if s.finished_at else None,
            latency_ms=s.latency_ms,
            input_snapshot=s.input_snapshot,
            output_snapshot=s.output_snapshot,
            error=s.error,
        )
        for s in steps
    ]

    return AgentRunDetailResponse(
        run_id=run.id,
        kb_id=run.kb_id,
        status=run.status,
        query=run.query,
        input_payload=run.input_payload,
        output_payload=run.output_payload,
        error=run.error,
        created_at=run.created_at.isoformat() if run.created_at else "",
        finished_at=run.finished_at.isoformat() if run.finished_at else None,
        trace=trace,
        ticket_id=ticket_id,
    )
