from __future__ import annotations

from aigate_assistant.rag.qdrant_store import RetrievedChunk, _dedupe, _mmr_select


def test_dedupe_keeps_best_score_per_chunk_identity():
    c1 = RetrievedChunk(score=0.5, text="a", source_uri="f.md", payload={"section_path": "S", "chunk_index": 1})
    c2 = RetrievedChunk(score=0.9, text="a2", source_uri="f.md", payload={"section_path": "S", "chunk_index": 1})
    c3 = RetrievedChunk(score=0.7, text="b", source_uri="f.md", payload={"section_path": "S", "chunk_index": 2})

    out = _dedupe([c1, c2, c3])
    assert len(out) == 2
    assert out[0].score == 0.9
    assert out[0].payload["chunk_index"] == 1


def test_mmr_select_prefers_diverse_candidates():
    # query vector points to x-axis
    q = [1.0, 0.0]
    # Two very similar candidates (close to query)
    a = RetrievedChunk(score=1.0, text="a", source_uri="a.md", payload={}, vector=[0.99, 0.01])
    b = RetrievedChunk(score=0.99, text="b", source_uri="b.md", payload={}, vector=[0.98, 0.02])
    # One diverse but still relevant-ish candidate
    c = RetrievedChunk(score=0.8, text="c", source_uri="c.md", payload={}, vector=[0.7, -0.7])

    selected = _mmr_select(query_vector=q, candidates=[a, b, c], k=2, lambda_mult=0.5)
    assert len(selected) == 2
    assert selected[0].text in {"a", "b"}
    # Expect diversity: c should be picked over the near-duplicate
    assert selected[1].text == "c"

