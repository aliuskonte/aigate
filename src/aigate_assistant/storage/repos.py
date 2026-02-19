from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from aigate.storage.models import (
    AgentRun,
    AgentRunStep,
    AssistantDocument,
    AssistantIngestJob,
    AssistantKnowledgeBase,
    AssistantTicket,
)


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


async def get_or_create_kb(*, session: AsyncSession, name: str) -> AssistantKnowledgeBase:
    kb = await session.scalar(select(AssistantKnowledgeBase).where(AssistantKnowledgeBase.name == name))
    if kb is not None:
        return kb

    kb = AssistantKnowledgeBase(name=name)
    session.add(kb)
    await session.commit()
    await session.refresh(kb)
    return kb


async def create_ingest_job(*, session: AsyncSession, kb_id: str) -> AssistantIngestJob:
    job = AssistantIngestJob(kb_id=kb_id, status="queued", progress=0.0, created_at=utcnow())
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def set_job_running(*, session: AsyncSession, job_id: str) -> None:
    await session.execute(
        update(AssistantIngestJob)
        .where(AssistantIngestJob.id == job_id)
        .values(status="running", started_at=utcnow(), error=None)
    )
    await session.commit()


async def set_job_progress(*, session: AsyncSession, job_id: str, progress: float, stats: dict | None = None) -> None:
    await session.execute(
        update(AssistantIngestJob)
        .where(AssistantIngestJob.id == job_id)
        .values(progress=float(progress), stats=stats)
    )
    await session.commit()


async def set_job_failed(*, session: AsyncSession, job_id: str, error: str) -> None:
    await session.execute(
        update(AssistantIngestJob)
        .where(AssistantIngestJob.id == job_id)
        .values(status="failed", finished_at=utcnow(), error=error, progress=1.0)
    )
    await session.commit()


async def set_job_succeeded(*, session: AsyncSession, job_id: str, stats: dict | None = None) -> None:
    await session.execute(
        update(AssistantIngestJob)
        .where(AssistantIngestJob.id == job_id)
        .values(status="succeeded", finished_at=utcnow(), progress=1.0, stats=stats)
    )
    await session.commit()


async def get_job(*, session: AsyncSession, job_id: str) -> AssistantIngestJob | None:
    return await session.scalar(select(AssistantIngestJob).where(AssistantIngestJob.id == job_id))


async def get_document(
    *,
    session: AsyncSession,
    kb_id: str,
    source_uri: str,
) -> AssistantDocument | None:
    return await session.scalar(
        select(AssistantDocument).where(
            AssistantDocument.kb_id == kb_id,
            AssistantDocument.source_uri == source_uri,
        )
    )


async def list_documents_by_kb(*, session: AsyncSession, kb_id: str) -> list[AssistantDocument]:
    res = await session.execute(select(AssistantDocument).where(AssistantDocument.kb_id == kb_id))
    return list(res.scalars().all())


async def delete_document(*, session: AsyncSession, kb_id: str, source_uri: str) -> None:
    await session.execute(
        delete(AssistantDocument).where(
            AssistantDocument.kb_id == kb_id,
            AssistantDocument.source_uri == source_uri,
        )
    )
    await session.commit()


async def upsert_document(
    *,
    session: AsyncSession,
    kb_id: str,
    source_type: str,
    source_uri: str,
    content_hash: str,
) -> None:
    stmt = insert(AssistantDocument).values(
        kb_id=kb_id,
        source_type=source_type,
        source_uri=source_uri,
        content_hash=content_hash,
        updated_at=utcnow(),
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_assistant_documents_source",
        set_={"content_hash": content_hash, "updated_at": utcnow()},
    )
    await session.execute(stmt)
    await session.commit()


# --- Agent runs, steps, tickets ---


async def create_agent_run(
    *,
    session: AsyncSession,
    kb_id: str,
    query: str,
    input_payload: dict | None = None,
) -> AgentRun:
    run = AgentRun(
        kb_id=kb_id,
        status="running",
        query=query,
        input_payload=input_payload,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def set_agent_run_finished(
    *,
    session: AsyncSession,
    run_id: str,
    status: str,
    output_payload: dict | None = None,
    error: str | None = None,
) -> None:
    await session.execute(
        update(AgentRun)
        .where(AgentRun.id == run_id)
        .values(
            status=status,
            output_payload=output_payload,
            error=error,
            finished_at=utcnow(),
        )
    )
    await session.commit()


async def add_agent_run_step(
    *,
    session: AsyncSession,
    run_id: str,
    node_name: str,
    step_order: int,
    started_at: datetime,
    finished_at: datetime | None = None,
    latency_ms: int | None = None,
    input_snapshot: dict | None = None,
    output_snapshot: dict | None = None,
    error: str | None = None,
) -> None:
    step = AgentRunStep(
        run_id=run_id,
        node_name=node_name,
        step_order=step_order,
        started_at=started_at,
        finished_at=finished_at,
        latency_ms=latency_ms,
        input_snapshot=input_snapshot,
        output_snapshot=output_snapshot,
        error=error,
    )
    session.add(step)
    await session.commit()


async def get_agent_run(*, session: AsyncSession, run_id: str) -> AgentRun | None:
    return await session.scalar(select(AgentRun).where(AgentRun.id == run_id))


async def list_agent_run_steps(*, session: AsyncSession, run_id: str) -> list[AgentRunStep]:
    res = await session.execute(
        select(AgentRunStep).where(AgentRunStep.run_id == run_id).order_by(AgentRunStep.step_order)
    )
    return list(res.scalars().all())


async def create_ticket(
    *,
    session: AsyncSession,
    run_id: str | None,
    ticket_type: str,
    title: str,
    context: dict | None = None,
    severity: str = "normal",
) -> AssistantTicket:
    ticket = AssistantTicket(
        run_id=run_id,
        ticket_type=ticket_type,
        title=title,
        context=context,
        severity=severity,
        status="open",
    )
    session.add(ticket)
    await session.commit()
    await session.refresh(ticket)
    return ticket


async def get_ticket(*, session: AsyncSession, ticket_id: str) -> AssistantTicket | None:
    return await session.scalar(select(AssistantTicket).where(AssistantTicket.id == ticket_id))

