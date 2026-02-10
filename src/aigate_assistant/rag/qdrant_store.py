from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from qdrant_client.async_qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels


def _stable_point_id(*, kb_id: str, source_uri: str, chunk_index: int, chunk_text: str) -> str:
    h = hashlib.sha256()
    h.update(kb_id.encode("utf-8"))
    h.update(b"|")
    h.update(source_uri.encode("utf-8"))
    h.update(b"|")
    h.update(str(chunk_index).encode("utf-8"))
    h.update(b"|")
    h.update(chunk_text.encode("utf-8"))
    # UUID5 expects a namespace UUID. Use a fixed one derived from the hash prefix.
    ns = uuid.UUID("00000000-0000-0000-0000-000000000000")
    return str(uuid.uuid5(ns, h.hexdigest()))


@dataclass(frozen=True)
class RetrievedChunk:
    score: float
    text: str
    source_uri: str
    payload: dict[str, Any]


async def ensure_collection(
    *,
    qdrant: AsyncQdrantClient,
    collection: str,
    vector_dim: int,
) -> None:
    try:
        info = await qdrant.get_collection(collection_name=collection)
        existing_dim = info.config.params.vectors.size  # type: ignore[attr-defined]
        if int(existing_dim) != int(vector_dim):
            raise RuntimeError(
                f"Qdrant collection '{collection}' has dim={existing_dim}, expected {vector_dim}"
            )
        return
    except Exception:
        # Create if missing (or if get failed). If create fails due to race, ignore.
        try:
            await qdrant.create_collection(
                collection_name=collection,
                vectors_config=qmodels.VectorParams(
                    size=vector_dim,
                    distance=qmodels.Distance.COSINE,
                ),
            )
        except Exception:
            # likely already created by another worker
            return


async def upsert_chunks(
    *,
    qdrant: AsyncQdrantClient,
    collection: str,
    kb_id: str,
    source_uri: str,
    vectors: list[list[float]],
    chunks: list[str],
    per_chunk_payload: list[dict[str, Any]] | None = None,
    extra_payload: dict[str, Any] | None = None,
) -> int:
    extra_payload = extra_payload or {}
    if per_chunk_payload is not None and len(per_chunk_payload) != len(chunks):
        raise ValueError("per_chunk_payload must have same length as chunks")
    points: list[qmodels.PointStruct] = []
    for idx, (vec, chunk) in enumerate(zip(vectors, chunks, strict=True)):
        pid = _stable_point_id(kb_id=kb_id, source_uri=source_uri, chunk_index=idx, chunk_text=chunk)
        chunk_payload = per_chunk_payload[idx] if per_chunk_payload is not None else {}
        payload = {
            "kb_id": kb_id,
            "source_uri": source_uri,
            "chunk_index": idx,
            "text": chunk,
            **chunk_payload,
            **extra_payload,
        }
        points.append(qmodels.PointStruct(id=pid, vector=vec, payload=payload))

    if not points:
        return 0

    await qdrant.upsert(
        collection_name=collection,
        points=points,
        wait=True,
    )
    return len(points)


async def search(
    *,
    qdrant: AsyncQdrantClient,
    collection: str,
    query_vector: list[float],
    top_k: int,
    kb_id: str,
) -> list[RetrievedChunk]:
    if not query_vector:
        return []

    res = await qdrant.query_points(
        collection_name=collection,
        query=query_vector,
        limit=top_k,
        with_payload=True,
        query_filter=qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="kb_id",
                    match=qmodels.MatchValue(value=kb_id),
                )
            ]
        ),
    )

    out: list[RetrievedChunk] = []
    for p in res.points:
        payload = dict(p.payload or {})
        out.append(
            RetrievedChunk(
                score=float(p.score),
                text=str(payload.get("text") or ""),
                source_uri=str(payload.get("source_uri") or ""),
                payload=payload,
            )
        )
    return out

