"""Agent tools: read-only (logs, metrics, usage) + create_ticket for audit."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aigate.storage.models import RequestLog, UsageEvent

log = logging.getLogger(__name__)


async def search_logs(
    *,
    loki_url: str,
    query: str,
    since_seconds: int = 3600,
    limit: int = 50,
) -> dict[str, Any]:
    """Query Loki log API. Returns structured result or error."""
    if not loki_url:
        return {"ok": False, "error": "LOKI_URL not configured"}
    try:
        # Loki query range API
        import time as t
        end_ns = int(t.time() * 1e9)
        start_ns = end_ns - since_seconds * 1_000_000_000
        url = f"{loki_url.rstrip('/')}/loki/api/v1/query_range"
        params = {"query": query or "{job=~'.+'}"}
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                url,
                params={
                    **params,
                    "start": start_ns,
                    "end": end_ns,
                    "limit": str(min(limit, 100)),
                },
            )
        if r.status_code >= 400:
            return {"ok": False, "error": f"Loki {r.status_code}", "body": r.text[:500]}
        data = r.json()
        return {"ok": True, "data": data}
    except Exception as e:
        log.exception("search_logs failed")
        return {"ok": False, "error": str(e)}


async def get_metrics(
    *,
    prometheus_url: str,
    query: str,
    from_ts: int | None = None,
    to_ts: int | None = None,
    step: str = "15s",
) -> dict[str, Any]:
    """Query Prometheus range API. Returns structured result or error."""
    if not prometheus_url:
        return {"ok": False, "error": "PROMETHEUS_URL not configured"}
    try:
        url = f"{prometheus_url.rstrip('/')}/api/v1/query_range"
        params = {"query": query, "step": step}
        if from_ts is not None:
            params["start"] = from_ts
        if to_ts is not None:
            params["end"] = to_ts
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(url, params=params)
        if r.status_code >= 400:
            return {"ok": False, "error": f"Prometheus {r.status_code}", "body": r.text[:500]}
        data = r.json()
        return {"ok": True, "data": data}
    except Exception as e:
        log.exception("get_metrics failed")
        return {"ok": False, "error": str(e)}


async def get_org_usage(
    *,
    session: AsyncSession,
    org_id: str,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
) -> dict[str, Any]:
    """Aggregate usage for an org from ledger (usage_events)."""
    if from_ts is None:
        from_ts = datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    if to_ts is None:
        to_ts = datetime.now(tz=timezone.utc)
    q = (
        select(
            func.count(UsageEvent.id).label("event_count"),
            func.coalesce(func.sum(UsageEvent.billed_cost), 0).label("total_billed_cost"),
            func.coalesce(func.sum(UsageEvent.prompt_tokens), 0).label("total_prompt_tokens"),
            func.coalesce(func.sum(UsageEvent.completion_tokens), 0).label("total_completion_tokens"),
        )
        .where(
            UsageEvent.org_id == org_id,
            UsageEvent.created_at >= from_ts,
            UsageEvent.created_at <= to_ts,
        )
    )
    row = (await session.execute(q)).one_or_none()
    if not row:
        return {"ok": True, "event_count": 0, "total_billed_cost": 0, "total_prompt_tokens": 0, "total_completion_tokens": 0}
    return {
        "ok": True,
        "event_count": row.event_count or 0,
        "total_billed_cost": float(row.total_billed_cost or 0),
        "total_prompt_tokens": int(row.total_prompt_tokens or 0),
        "total_completion_tokens": int(row.total_completion_tokens or 0),
    }


async def explain_request(
    *,
    session: AsyncSession,
    request_id: str,
) -> dict[str, Any]:
    """Get request + usage for a given request_id (from ledger)."""
    rlog = await session.scalar(
        select(RequestLog).where(RequestLog.request_id == request_id)
    )
    if not rlog:
        return {"ok": False, "error": "request not found"}
    usage_rows = (
        await session.execute(
            select(UsageEvent).where(UsageEvent.request_db_id == rlog.id)
        )
    ).scalars().all()
    usage = [
        {
            "provider": u.provider,
            "model": u.model,
            "prompt_tokens": u.prompt_tokens,
            "completion_tokens": u.completion_tokens,
            "billed_cost": float(u.billed_cost) if u.billed_cost is not None else None,
        }
        for u in usage_rows
    ]
    return {
        "ok": True,
        "request_id": rlog.request_id,
        "org_id": rlog.org_id,
        "provider": rlog.provider,
        "model": rlog.model,
        "status_code": rlog.status_code,
        "latency_ms": rlog.latency_ms,
        "usage": usage,
    }


