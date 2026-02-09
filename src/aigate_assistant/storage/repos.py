from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from aigate.storage.models import AssistantDocument, AssistantIngestJob, AssistantKnowledgeBase


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

