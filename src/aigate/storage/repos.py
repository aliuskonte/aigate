from __future__ import annotations

import hashlib
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aigate.storage.models import ApiKey, PriceRule, RequestLog, UsageEvent


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def key_prefix(api_key: str, length: int = 8) -> str:
    return api_key[:length]


async def get_active_api_key_by_hash(session: AsyncSession, *, key_hash: str) -> ApiKey | None:
    stmt = select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_markup_pct(session: AsyncSession, *, org_id: str, provider: str, model: str) -> Decimal:
    # Priority:
    # 1) exact (org, provider, model)
    # 2) provider default (org, provider, NULL)
    # 3) global default (org, "qwen", NULL) etc. (not implemented yet)
    stmt = (
        select(PriceRule)
        .where(PriceRule.org_id == org_id, PriceRule.provider == provider)
        .order_by(PriceRule.model.is_(None), PriceRule.created_at.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    for row in rows:
        if row.model is None or row.model == model:
            return Decimal(row.markup_pct)
    return Decimal("0")


async def create_request_log(
    session: AsyncSession,
    *,
    request_id: str,
    org_id: str,
    provider: str,
    model: str,
    status_code: int,
    latency_ms: int,
    request_hash: str,
    idempotency_key: str | None,
) -> RequestLog:
    row = RequestLog(
        request_id=request_id,
        org_id=org_id,
        provider=provider,
        model=model,
        status_code=status_code,
        latency_ms=latency_ms,
        request_hash=request_hash,
        idempotency_key=idempotency_key,
    )
    session.add(row)
    await session.flush()
    return row


async def create_usage_event(
    session: AsyncSession,
    *,
    org_id: str,
    request_db_id: str,
    provider: str,
    model: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    total_tokens: int | None,
    raw_cost: Decimal | None,
    billed_cost: Decimal | None,
    currency: str,
) -> UsageEvent:
    row = UsageEvent(
        org_id=org_id,
        request_db_id=request_db_id,
        provider=provider,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        raw_cost=raw_cost,
        billed_cost=billed_cost,
        currency=currency,
    )
    session.add(row)
    await session.flush()
    return row
