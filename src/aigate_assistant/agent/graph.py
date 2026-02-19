"""LangGraph RAG graph: retrieve → generate → format."""

from __future__ import annotations

import time
from typing import Any, TypedDict

from langgraph.graph import StateGraph

from aigate_assistant.agent.context import RAGGraphContext
from aigate_assistant.rag.qdrant_store import search as qdrant_search


class RAGState(TypedDict, total=False):
    query: str
    kb_id: str
    chunks: list[dict[str, Any]]
    context_blocks: list[str]
    sources: list[dict[str, Any]]
    answer: str
    model: str
    formatted_answer: str
    steps: list[dict[str, Any]]
    error: str


def _step_record(
    node_name: str,
    started_at: float,
    finished_at: float,
    input_snapshot: dict[str, Any],
    output_snapshot: dict[str, Any],
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "node_name": node_name,
        "started_at": started_at,
        "finished_at": finished_at,
        "latency_ms": int((finished_at - started_at) * 1000),
        "input_snapshot": input_snapshot,
        "output_snapshot": output_snapshot,
        "error": error,
    }


async def retrieve_node(state: RAGState, *, ctx: RAGGraphContext) -> dict[str, Any]:
    query = state["query"]
    kb_id = state["kb_id"]
    steps = list(state.get("steps") or [])
    started = time.time()
    input_snap = {"query": query[:500], "kb_id": kb_id}
    try:
        query_vec = ctx.embedder.embed_query(query)
        chunks = await qdrant_search(
            qdrant=ctx.qdrant,
            collection=ctx.settings.assistant_qdrant_collection,
            query_vector=query_vec,
            top_k=ctx.settings.assistant_top_k,
            kb_id=kb_id,
            candidate_k=ctx.settings.assistant_retrieval_candidate_k,
            dedupe_enabled=ctx.settings.assistant_dedupe_enabled,
            mmr_enabled=ctx.settings.assistant_mmr_enabled,
            mmr_lambda=ctx.settings.assistant_mmr_lambda,
        )
    except Exception as e:
        finished = time.time()
        steps.append(
            _step_record(
                "retrieve",
                started,
                finished,
                input_snap,
                {},
                error=str(e),
            )
        )
        return {"steps": steps, "error": str(e)}

    context_blocks = []
    sources = []
    chunks_ser = []
    for i, c in enumerate(chunks, start=1):
        section_path = (c.payload or {}).get("section_path")
        prefix = f"[{i}] ({c.source_uri}"
        if section_path:
            prefix += f" — {section_path}"
        prefix += ")"
        context_blocks.append(f"{prefix}\n{c.text}")
        sources.append({
            "source_uri": c.source_uri,
            "score": c.score,
            "text_preview": (c.text[:200].replace("\n", " ").strip()),
            "section_path": str(section_path) if section_path else None,
        })
        chunks_ser.append({
            "source_uri": c.source_uri,
            "score": c.score,
            "text_preview": (c.text[:200].replace("\n", " ").strip()),
        })

    finished = time.time()
    steps.append(
        _step_record(
            "retrieve",
            started,
            finished,
            input_snap,
            {"chunks_count": len(chunks), "sources_count": len(sources)},
        )
    )
    return {
        "chunks": chunks_ser,
        "context_blocks": context_blocks,
        "sources": sources,
        "steps": steps,
    }


async def generate_node(state: RAGState, *, ctx: RAGGraphContext) -> dict[str, Any]:
    if state.get("error"):
        return {}
    query = state["query"]
    context_blocks = state.get("context_blocks") or []
    steps = list(state.get("steps") or [])
    started = time.time()
    input_snap = {"query": query[:500], "context_blocks_count": len(context_blocks)}
    system_prompt = (
        "Ты внутренний ассистент по проекту AIGate.\n"
        "Отвечай кратко и технически.\n"
        "Если используешь контекст ниже — ссылайся на источники в формате [N].\n\n"
        "КОНТЕКСТ:\n"
        + ("\n\n".join(context_blocks) if context_blocks else "(пусто)")
    )
    payload = {
        "model": ctx.settings.assistant_llm_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ],
        "temperature": 0.2,
    }
    headers = None
    if ctx.aigate_api_key_override:
        headers = {"Authorization": f"Bearer {ctx.aigate_api_key_override}"}
    try:
        resp = await ctx.aigate_http.post(
            "/v1/chat/completions",
            json=payload,
            headers=headers,
        )
    except Exception as e:
        finished = time.time()
        steps.append(
            _step_record("generate", started, finished, input_snap, {}, error=str(e))
        )
        return {"steps": steps, "error": str(e)}

    if resp.status_code >= 400:
        finished = time.time()
        steps.append(
            _step_record(
                "generate",
                started,
                finished,
                input_snap,
                {},
                error=f"AIGate {resp.status_code}: {resp.text[:500]}",
            )
        )
        return {"steps": steps, "error": f"AIGate {resp.status_code}"}

    data = resp.json()
    try:
        answer = data["choices"][0]["message"]["content"]
    except Exception as e:
        finished = time.time()
        steps.append(
            _step_record("generate", started, finished, input_snap, {}, error=str(e))
        )
        return {"steps": steps, "error": str(e)}

    finished = time.time()
    steps.append(
        _step_record(
            "generate",
            started,
            finished,
            input_snap,
            {"answer_length": len(answer), "model": ctx.settings.assistant_llm_model},
        )
    )
    return {
        "answer": answer,
        "model": ctx.settings.assistant_llm_model,
        "steps": steps,
    }


async def format_node(state: RAGState, *, ctx: RAGGraphContext) -> dict[str, Any]:
    if state.get("error"):
        return {}
    answer = state.get("answer") or ""
    sources = state.get("sources") or []
    steps = list(state.get("steps") or [])
    started = time.time()
    input_snap = {"answer_length": len(answer), "sources_count": len(sources)}
    # For now we don't transform the answer; just pass through. Could add citation check.
    formatted = answer.strip()
    finished = time.time()
    steps.append(
        _step_record(
            "format",
            started,
            finished,
            input_snap,
            {"formatted_length": len(formatted)},
        )
    )
    return {"formatted_answer": formatted, "steps": steps}


def build_rag_graph(ctx: RAGGraphContext):
    """Build and compile the RAG graph (retrieve → generate → format)."""
    graph = StateGraph(RAGState)

    def make_retrieve(s: RAGState):
        return retrieve_node(s, ctx=ctx)

    def make_generate(s: RAGState):
        return generate_node(s, ctx=ctx)

    def make_format(s: RAGState):
        return format_node(s, ctx=ctx)

    graph.add_node("retrieve", make_retrieve)
    graph.add_node("generate", make_generate)
    graph.add_node("format", make_format)

    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", "format")
    graph.set_finish_point("format")

    return graph.compile()
