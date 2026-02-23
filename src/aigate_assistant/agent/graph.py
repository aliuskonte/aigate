"""LangGraph RAG graph: retrieve → planner → [tools] → generate → format → ticket_create."""

from __future__ import annotations

import json
import re
import time
from typing import Any, TypedDict

from langgraph.graph import StateGraph

from aigate_assistant.agent.context import RAGGraphContext
from aigate_assistant.agent.tools import explain_request, get_metrics, search_logs
from aigate_assistant.rag.qdrant_store import search as qdrant_search
from aigate_assistant.storage.repos import create_ticket


class RAGState(TypedDict, total=False):
    query: str
    kb_id: str
    run_id: str
    chunks: list[dict[str, Any]]
    context_blocks: list[str]
    sources: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    answer: str
    model: str
    formatted_answer: str
    steps: list[dict[str, Any]]
    error: str
    ticket_id: str | None


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


def _serialize_tool_results(tool_results: list[dict[str, Any]]) -> str:
    parts = []
    for i, r in enumerate(tool_results, 1):
        parts.append(f"Инструмент {i} ({r.get('tool', '?')}): ok={r.get('ok')}\n{json.dumps(r.get('data', r), ensure_ascii=False, default=str)[:4000]}")
    return "\n\n".join(parts)


async def generate_node(state: RAGState, *, ctx: RAGGraphContext) -> dict[str, Any]:
    if state.get("error"):
        return {}
    query = state["query"]
    context_blocks = state.get("context_blocks") or []
    tool_results = state.get("tool_results") or []
    steps = list(state.get("steps") or [])
    started = time.time()
    input_snap = {"query": query[:500], "context_blocks_count": len(context_blocks), "tool_results_count": len(tool_results)}
    system_parts = [
        "Ты внутренний ассистент по проекту AIGate.\n"
        "Отвечай кратко и технически.\n"
        "Если используешь контекст ниже — ссылайся на источники в формате [N].\n\n"
        "КОНТЕКСТ:\n",
        "\n\n".join(context_blocks) if context_blocks else "(пусто)",
    ]
    if tool_results:
        system_parts.append("\n\nРЕЗУЛЬТАТЫ ВЫЗОВОВ ИНСТРУМЕНТОВ:\n")
        system_parts.append(_serialize_tool_results(tool_results))
    system_prompt = "".join(system_parts)
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


# UUID/request_id pattern (hex or uuid-like)
_REQUEST_ID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[0-9a-fA-F]{32}")


def _planner_heuristic(query: str) -> list[dict[str, Any]]:
    """Return at most one tool call based on query keywords."""
    q = (query or "").strip().lower()
    tool_calls: list[dict[str, Any]] = []

    # explain_request: query contains request_id (UUID or 32-char hex)
    m = _REQUEST_ID_RE.search(query or "")
    if m:
        tool_calls.append({"tool": "explain_request", "args": {"request_id": m.group(0)}})
        return tool_calls

    if "лог" in q or "log" in q or "ошибк" in q:
        tool_calls.append({
            "tool": "search_logs",
            "args": {"query": "{job=~'.+'}", "since_seconds": 3600, "limit": 50},
        })
        return tool_calls

    if "метрик" in q or "metrics" in q or "rps" in q or "latency" in q:
        tool_calls.append({
            "tool": "get_metrics",
            "args": {"query": "aigate_requests_total", "step": "15s"},
        })
        return tool_calls

    return tool_calls


async def planner_node(state: RAGState, *, ctx: RAGGraphContext) -> dict[str, Any]:
    if state.get("error"):
        return {}
    query = state["query"]
    steps = list(state.get("steps") or [])
    started = time.time()
    tool_calls = _planner_heuristic(query)
    finished = time.time()
    steps.append(
        _step_record(
            "planner",
            started,
            finished,
            {"query": query[:500]},
            {"tool_calls_count": len(tool_calls), "tool_calls": tool_calls},
        )
    )
    return {"tool_calls": tool_calls, "steps": steps}


async def tools_node(state: RAGState, *, ctx: RAGGraphContext) -> dict[str, Any]:
    if state.get("error"):
        return {}
    tool_calls = state.get("tool_calls") or []
    steps = list(state.get("steps") or [])
    started = time.time()
    input_snap = {"tool_calls": tool_calls}
    results: list[dict[str, Any]] = []
    for tc in tool_calls:
        name = tc.get("tool") or ""
        args = tc.get("args") or {}
        if name == "explain_request" and ctx.session:
            out = await explain_request(session=ctx.session, request_id=args.get("request_id", ""))
            results.append({"tool": name, "ok": out.get("ok"), "data": out})
        elif name == "search_logs":
            out = await search_logs(
                loki_url=ctx.loki_url,
                query=args.get("query", "{job=~'.+'}"),
                since_seconds=int(args.get("since_seconds", 3600)),
                limit=int(args.get("limit", 50)),
            )
            results.append({"tool": name, "ok": out.get("ok"), "data": out})
        elif name == "get_metrics":
            out = await get_metrics(
                prometheus_url=ctx.prometheus_url,
                query=args.get("query", "aigate_requests_total"),
                step=args.get("step", "15s"),
            )
            results.append({"tool": name, "ok": out.get("ok"), "data": out})
        else:
            results.append({"tool": name, "ok": False, "error": "unsupported or missing session"})
    finished = time.time()
    steps.append(
        _step_record(
            "tools",
            started,
            finished,
            input_snap,
            {"results_count": len(results), "results": results},
        )
    )
    return {"tool_results": results, "steps": steps}


async def ticket_create_node(state: RAGState, *, ctx: RAGGraphContext) -> dict[str, Any]:
    if state.get("error"):
        return {}
    formatted = state.get("formatted_answer") or ""
    run_id = state.get("run_id") or ""
    query = state.get("query") or ""
    steps = list(state.get("steps") or [])
    started = time.time()
    input_snap = {"formatted_length": len(formatted), "run_id": run_id}
    ticket_id: str | None = None
    if "ACTION:" in formatted and ctx.session and run_id:
        title = "Action request"
        for line in formatted.splitlines():
            if "ACTION:" in line:
                title = line.replace("ACTION:", "").strip()[:512] or "Action request"
                break
        try:
            ticket = await create_ticket(
                session=ctx.session,
                run_id=run_id,
                ticket_type="action_request",
                title=title,
                context={
                    "run_id": run_id,
                    "query": query[:1000],
                    "answer_preview": formatted[:500],
                },
                severity="normal",
            )
            ticket_id = ticket.id
        except Exception as e:
            steps.append(
                _step_record("ticket_create", started, time.time(), input_snap, {}, error=str(e))
            )
            return {"steps": steps}
    finished = time.time()
    steps.append(
        _step_record(
            "ticket_create",
            started,
            finished,
            input_snap,
            {"ticket_id": ticket_id, "created": ticket_id is not None},
        )
    )
    return {"ticket_id": ticket_id, "steps": steps}


def _planner_route(state: RAGState) -> str:
    """Route after planner: 'tools' if we have tool_calls, else 'generate'."""
    tool_calls = state.get("tool_calls") or []
    return "tools" if tool_calls else "generate"


def build_rag_graph(ctx: RAGGraphContext):
    """Build and compile the RAG graph: retrieve → planner → [tools] → generate → format → ticket_create."""
    graph = StateGraph(RAGState)

    def make_retrieve(s: RAGState):
        return retrieve_node(s, ctx=ctx)

    def make_planner(s: RAGState):
        return planner_node(s, ctx=ctx)

    def make_tools(s: RAGState):
        return tools_node(s, ctx=ctx)

    def make_generate(s: RAGState):
        return generate_node(s, ctx=ctx)

    def make_format(s: RAGState):
        return format_node(s, ctx=ctx)

    def make_ticket_create(s: RAGState):
        return ticket_create_node(s, ctx=ctx)

    graph.add_node("retrieve", make_retrieve)
    graph.add_node("planner", make_planner)
    graph.add_node("tools", make_tools)
    graph.add_node("generate", make_generate)
    graph.add_node("format", make_format)
    graph.add_node("ticket_create", make_ticket_create)

    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "planner")
    graph.add_conditional_edges("planner", _planner_route, {"tools": "tools", "generate": "generate"})
    graph.add_edge("tools", "generate")
    graph.add_edge("generate", "format")
    graph.add_edge("format", "ticket_create")
    graph.set_finish_point("ticket_create")

    return graph.compile()
