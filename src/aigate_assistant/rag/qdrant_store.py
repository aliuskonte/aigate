from __future__ import annotations

import hashlib
import math
import re
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


def _slugify(s: str, *, max_len: int = 64) -> str:
    s = (s or "").strip().lower()
    s = s.replace("/", "__")
    s = re.sub(r"[^a-z0-9_\\-\\.]", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:max_len] if len(s) > max_len else s


def build_collection_name(*, base_alias: str, embed_model: str, vector_dim: int) -> str:
    """
    Build a versioned collection name derived from:
    - base alias (stable name used by API)
    - embed model
    - vector dim
    """

    alias = _slugify(base_alias, max_len=48) or "kb"
    model = _slugify(embed_model, max_len=64) or "embed"
    dim = int(vector_dim)
    return f"{alias}__{model}__dim{dim}"


async def set_collection_alias(
    *,
    qdrant: AsyncQdrantClient,
    alias_name: str,
    collection_name: str,
) -> None:
    """
    Ensure alias points to the target collection.
    Safe to call repeatedly.
    """

    # If alias already points to collection, do nothing.
    aliases = await qdrant.get_aliases()
    for a in aliases.aliases:
        if a.alias_name == alias_name and a.collection_name == collection_name:
            return

    ops = [
        qmodels.DeleteAliasOperation(delete_alias=qmodels.DeleteAlias(alias_name=alias_name)),
        qmodels.CreateAliasOperation(
            create_alias=qmodels.CreateAlias(collection_name=collection_name, alias_name=alias_name)
        ),
    ]
    try:
        await qdrant.update_collection_aliases(ops)
    except Exception:
        # If delete failed because alias didn't exist, try create only.
        await qdrant.update_collection_aliases(
            [
                qmodels.CreateAliasOperation(
                    create_alias=qmodels.CreateAlias(
                        collection_name=collection_name,
                        alias_name=alias_name,
                    )
                )
            ]
        )


async def delete_by_source_uri(
    *,
    qdrant: AsyncQdrantClient,
    collection: str,
    kb_id: str,
    source_uri: str,
) -> None:
    """
    Delete all points for a specific (kb_id, source_uri) in the given collection/alias.
    """

    await qdrant.delete(
        collection_name=collection,
        points_selector=qmodels.FilterSelector(
            filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="kb_id",
                        match=qmodels.MatchValue(value=kb_id),
                    ),
                    qmodels.FieldCondition(
                        key="source_uri",
                        match=qmodels.MatchValue(value=source_uri),
                    ),
                ]
            )
        ),
        wait=True,
    )


@dataclass(frozen=True)
class RetrievedChunk:
    score: float
    text: str
    source_uri: str
    payload: dict[str, Any]
    vector: list[float] | None = None


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b, strict=True):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _dedupe(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """
    Remove duplicates by (source_uri, section_path, chunk_index). Keep best score.
    """

    best: dict[tuple[str, str, int], RetrievedChunk] = {}
    for c in chunks:
        section = str((c.payload or {}).get("section_path") or "")
        idx = int((c.payload or {}).get("chunk_index") or 0)
        key = (c.source_uri, section, idx)
        prev = best.get(key)
        if prev is None or c.score > prev.score:
            best[key] = c
    return sorted(best.values(), key=lambda x: x.score, reverse=True)


def _mmr_select(
    *,
    query_vector: list[float],
    candidates: list[RetrievedChunk],
    k: int,
    lambda_mult: float,
) -> list[RetrievedChunk]:
    """
    MMR (Maximal Marginal Relevance): pick chunks relevant to the query but diverse
    relative to already selected chunks.
    """

    k = max(0, int(k))
    if k == 0 or not candidates:
        return []

    lambda_mult = max(0.0, min(1.0, float(lambda_mult)))

    # If vectors are missing, fall back to score-only selection.
    if not query_vector or any(c.vector is None for c in candidates):
        return candidates[:k]

    selected: list[RetrievedChunk] = []
    remaining = candidates[:]

    while remaining and len(selected) < k:
        best_item: RetrievedChunk | None = None
        best_mmr: float | None = None

        for cand in remaining:
            sim_to_query = _cosine(query_vector, cand.vector or [])
            if not selected:
                mmr = sim_to_query
            else:
                max_sim_to_selected = max(
                    _cosine((cand.vector or []), (s.vector or [])) for s in selected
                )
                mmr = lambda_mult * sim_to_query - (1.0 - lambda_mult) * max_sim_to_selected

            if best_mmr is None or mmr > best_mmr:
                best_mmr = mmr
                best_item = cand

        if best_item is None:
            break
        selected.append(best_item)
        remaining.remove(best_item)

    return selected


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
    candidate_k: int | None = None,
    dedupe_enabled: bool = True,
    mmr_enabled: bool = True,
    mmr_lambda: float = 0.65,
) -> list[RetrievedChunk]:
    if not query_vector:
        return []

    top_k = max(1, int(top_k))
    candidate_k = int(candidate_k or (top_k * 4))
    candidate_k = max(top_k, min(candidate_k, 100))

    res = await qdrant.query_points(
        collection_name=collection,
        query=query_vector,
        limit=candidate_k,
        with_payload=True,
        with_vectors=True,
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
        vec: list[float] | None = None
        try:
            # For single-vector collections, Qdrant returns a list[float].
            if isinstance(p.vector, list):
                vec = [float(x) for x in p.vector]
            # Some clients/versions can return dict[name -> vector].
            elif isinstance(p.vector, dict) and p.vector:
                first = next(iter(p.vector.values()))
                if isinstance(first, list):
                    vec = [float(x) for x in first]
        except Exception:
            vec = None
        out.append(
            RetrievedChunk(
                score=float(p.score),
                text=str(payload.get("text") or ""),
                source_uri=str(payload.get("source_uri") or ""),
                payload=payload,
                vector=vec,
            )
        )

    if dedupe_enabled:
        out = _dedupe(out)
    if mmr_enabled:
        out = _mmr_select(query_vector=query_vector, candidates=out, k=top_k, lambda_mult=mmr_lambda)
    else:
        out = out[:top_k]
    return out

