from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path

from qdrant_client.async_qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from aigate.storage.db import create_engine, create_sessionmaker
from aigate_assistant.core.config import get_assistant_settings
from aigate_assistant.rag.chunking import chunk_text
from aigate_assistant.rag.embeddings import Embedder
from aigate_assistant.rag.qdrant_store import ensure_collection, upsert_chunks
from aigate_assistant.storage.repos import (
    get_job,
    set_job_failed,
    set_job_progress,
    set_job_running,
    set_job_succeeded,
    upsert_document,
)

log = logging.getLogger(__name__)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _iter_source_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    out: list[Path] = []
    for p in root.rglob("*.md"):
        if p.is_file():
            out.append(p)
    return sorted(out)


async def process_job(
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    redis,
    qdrant: AsyncQdrantClient,
    embedder: Embedder,
    job_id: str,
) -> None:
    settings = get_assistant_settings()

    async with sessionmaker() as session:
        job = await get_job(session=session, job_id=job_id)
        if job is None:
            log.warning("assistant.job_not_found", extra={"job_id": job_id})
            return

        await set_job_running(session=session, job_id=job_id)

        kb_id = job.kb_id

    try:
        docs_root = Path("/app/docs")
        mb_root = Path("/app/memory-bank")
        docs_files = _iter_source_files(docs_root)
        mb_files = _iter_source_files(mb_root)
        files = docs_files + mb_files
        if not files:
            async with sessionmaker() as session:
                await set_job_succeeded(
                    session=session,
                    job_id=job_id,
                    stats={"files": 0, "chunks": 0, "points": 0, "note": "No .md files found"},
                )
            return

        total_files = len(files)
        total_chunks = 0
        total_points = 0

        # Ensure collection exists (needs dim). We'll infer dim from the first non-empty chunk.
        collection_ready = False
        collection_dim = None

        for idx, path in enumerate(files, start=1):
            raw = path.read_bytes()
            text = raw.decode("utf-8", errors="replace")
            content_hash = _sha256_hex(raw)

            rel_uri = str(path.relative_to(Path("/app")))

            chunks = chunk_text(
                text=text,
                chunk_size=settings.assistant_chunk_size_chars,
                overlap=settings.assistant_chunk_overlap_chars,
            )
            if not chunks:
                async with sessionmaker() as session:
                    await upsert_document(
                        session=session,
                        kb_id=kb_id,
                        source_type="directory",
                        source_uri=rel_uri,
                        content_hash=content_hash,
                    )
                    await set_job_progress(
                        session=session,
                        job_id=job_id,
                        progress=idx / total_files,
                        stats={
                            "sources": {
                                "docs": {"root": str(docs_root), "files": len(docs_files)},
                                "memory_bank": {"root": str(mb_root), "files": len(mb_files)},
                            },
                            "files_total": total_files,
                            "files_done": idx,
                            "chunks": total_chunks,
                            "points": total_points,
                        },
                    )
                continue

            emb = embedder.embed_texts(chunks)
            if not collection_ready:
                collection_dim = emb.dim
                await ensure_collection(qdrant=qdrant, collection=settings.assistant_qdrant_collection, vector_dim=emb.dim)
                collection_ready = True

            points = await upsert_chunks(
                qdrant=qdrant,
                collection=settings.assistant_qdrant_collection,
                kb_id=kb_id,
                source_uri=rel_uri,
                vectors=emb.vectors,
                chunks=chunks,
                extra_payload={"content_hash": content_hash},
            )

            total_chunks += len(chunks)
            total_points += points

            async with sessionmaker() as session:
                await upsert_document(
                    session=session,
                    kb_id=kb_id,
                    source_type="directory",
                    source_uri=rel_uri,
                    content_hash=content_hash,
                )
                await set_job_progress(
                    session=session,
                    job_id=job_id,
                    progress=idx / total_files,
                    stats={
                        "sources": {
                            "docs": {"root": str(docs_root), "files": len(docs_files)},
                            "memory_bank": {"root": str(mb_root), "files": len(mb_files)},
                        },
                        "files_total": total_files,
                        "files_done": idx,
                        "chunks": total_chunks,
                        "points": total_points,
                        "collection_dim": collection_dim,
                    },
                )

        async with sessionmaker() as session:
            await set_job_succeeded(
                session=session,
                job_id=job_id,
                stats={
                    "sources": {
                        "docs": {"root": str(docs_root), "files": len(docs_files)},
                        "memory_bank": {"root": str(mb_root), "files": len(mb_files)},
                    },
                    "files_total": total_files,
                    "chunks": total_chunks,
                    "points": total_points,
                    "collection_dim": collection_dim,
                },
            )
    except Exception as e:
        async with sessionmaker() as session:
            await set_job_failed(session=session, job_id=job_id, error=str(e))
        raise


async def main() -> None:
    settings = get_assistant_settings()
    logging.basicConfig(level=logging.INFO)

    db_engine: AsyncEngine = create_engine(database_url=settings.database_url)
    sessionmaker = create_sessionmaker(db_engine)

    from redis.asyncio import Redis as RedisClient

    redis = RedisClient.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    qdrant = AsyncQdrantClient(url=settings.assistant_qdrant_url)
    embedder = Embedder(model_name=settings.assistant_embed_model)

    log.info("assistant.worker_start", extra={"queue": settings.assistant_redis_queue_key})
    try:
        while True:
            item = await redis.brpop(settings.assistant_redis_queue_key, timeout=5)
            if not item:
                await asyncio.sleep(0.2)
                continue
            _, job_id = item
            log.info("assistant.job_received", extra={"job_id": job_id})
            try:
                await process_job(
                    sessionmaker=sessionmaker,
                    redis=redis,
                    qdrant=qdrant,
                    embedder=embedder,
                    job_id=job_id,
                )
                log.info("assistant.job_done", extra={"job_id": job_id})
            except Exception as e:
                log.exception("assistant.job_failed", extra={"job_id": job_id, "err": str(e)})
    finally:
        await qdrant.close()
        await redis.aclose()
        await db_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

