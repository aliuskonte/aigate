from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from aigate_assistant.eval.metrics import citation_validity, hit_at_k, mrr, parse_citations, recall_at_k


@dataclass(frozen=True)
class EvalCase:
    id: str
    kb_name: str
    query: str
    expected_sources: set[str]
    top_k: int
    run_chat: bool


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        rows.append(json.loads(s))
    return rows


def load_cases(path: Path, *, default_top_k: int, run_chat: bool) -> list[EvalCase]:
    raw = _load_jsonl(path)
    out: list[EvalCase] = []
    for r in raw:
        out.append(
            EvalCase(
                id=str(r["id"]),
                kb_name=str(r.get("kb_name") or "default"),
                query=str(r["query"]),
                expected_sources=set(r.get("expected_sources") or []),
                top_k=int(r.get("top_k") or default_top_k),
                run_chat=bool(r.get("run_chat") if "run_chat" in r else run_chat),
            )
        )
    return out


async def _post(
    client: httpx.AsyncClient,
    *,
    url: str,
    json_body: dict[str, Any],
    bearer_token: str | None,
    x_aigate_api_key: str | None,
) -> dict[str, Any]:
    headers: dict[str, str] = {}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    if x_aigate_api_key:
        headers["X-AIGATE-API-KEY"] = x_aigate_api_key
    r = await client.post(url, json=json_body, headers=headers, timeout=60)
    r.raise_for_status()
    return r.json()


async def run_eval(
    *,
    base_url: str,
    eval_path: Path,
    assistant_api_key: str | None,
    aigate_api_key: str | None,
    default_top_k: int,
    run_chat: bool,
) -> int:
    cases = load_cases(eval_path, default_top_k=default_top_k, run_chat=run_chat)
    if not cases:
        print("No cases found.")
        return 2

    base_url = base_url.rstrip("/")
    retrieve_url = f"{base_url}/v1/assistant/retrieve"
    chat_url = f"{base_url}/v1/assistant/chat"

    totals = {
        "cases": 0,
        "hit_at_k_sum": 0.0,
        "mrr_sum": 0.0,
        "recall_sum": 0.0,
        "recall_count": 0,
        "cit_valid": 0,
        "cit_invalid_low": 0,
        "cit_invalid_high": 0,
    }

    async with httpx.AsyncClient() as client:
        for c in cases:
            ret = await _post(
                client,
                url=retrieve_url,
                json_body={"kb_name": c.kb_name, "message": c.query, "top_k": c.top_k},
                bearer_token=assistant_api_key,
                x_aigate_api_key=None,
            )
            sources = ret.get("sources") or []
            ranked_uris = [str(s.get("source_uri") or "") for s in sources]

            h = hit_at_k(expected=c.expected_sources, ranked=ranked_uris, k=c.top_k)
            r = recall_at_k(expected=c.expected_sources, ranked=ranked_uris, k=c.top_k)
            rr = mrr(expected=c.expected_sources, ranked=ranked_uris)

            totals["cases"] += 1
            totals["hit_at_k_sum"] += float(h)
            totals["mrr_sum"] += float(rr)
            if r is not None:
                totals["recall_sum"] += float(r)
                totals["recall_count"] += 1

            per_case: dict[str, Any] = {
                "id": c.id,
                "kb_name": c.kb_name,
                "top_k": c.top_k,
                "expected_sources": sorted(c.expected_sources),
                "retrieved_sources": ranked_uris[: c.top_k],
                "hit_at_k": h,
                "mrr": rr,
                "recall_at_k": r,
            }

            if c.run_chat:
                chat = await _post(
                    client,
                    url=chat_url,
                    json_body={"kb_name": c.kb_name, "message": c.query, "top_k": c.top_k},
                    bearer_token=assistant_api_key,
                    x_aigate_api_key=aigate_api_key,
                )
                answer = str(chat.get("answer") or "")
                chat_sources = chat.get("sources") or sources
                citations = parse_citations(answer)
                v = citation_validity(citations=citations, n_sources=len(chat_sources))
                totals["cit_valid"] += v["valid"]
                totals["cit_invalid_low"] += v["invalid_low"]
                totals["cit_invalid_high"] += v["invalid_high"]

                per_case.update(
                    {
                        "citations": citations,
                        "citation_validity": v,
                    }
                )

            print(json.dumps(per_case, ensure_ascii=False))

    summary = {
        "cases": totals["cases"],
        "hit_at_k": (totals["hit_at_k_sum"] / max(1, totals["cases"])),
        "mrr": (totals["mrr_sum"] / max(1, totals["cases"])),
        "recall_at_k": (
            (totals["recall_sum"] / max(1, totals["recall_count"])) if totals["recall_count"] else None
        ),
        "citations": {
            "valid": totals["cit_valid"],
            "invalid_low": totals["cit_invalid_low"],
            "invalid_high": totals["cit_invalid_high"],
        },
    }
    print("---")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="Assistant RAG evaluation runner")
    p.add_argument("--base-url", default="http://localhost:8010", help="assistant-api base url")
    p.add_argument("--eval", dest="eval_path", default="eval/assistant_eval.jsonl", help="path to eval jsonl")
    p.add_argument("--assistant-api-key", default=None, help="Bearer token for assistant-api (ASSISTANT_API_KEY)")
    p.add_argument("--aigate-api-key", default=None, help="AIGate client key for chat mode (X-AIGATE-API-KEY)")
    p.add_argument("--top-k", type=int, default=6, help="default top_k for cases")
    p.add_argument(
        "--chat",
        action="store_true",
        help="also call /v1/assistant/chat and validate [N] citations (costs LLM tokens)",
    )
    args = p.parse_args()

    rc = asyncio.run(
        run_eval(
            base_url=args.base_url,
            eval_path=Path(args.eval_path),
            assistant_api_key=args.assistant_api_key,
            aigate_api_key=args.aigate_api_key,
            default_top_k=args.top_k,
            run_chat=bool(args.chat),
        )
    )
    raise SystemExit(rc)


if __name__ == "__main__":
    main()

