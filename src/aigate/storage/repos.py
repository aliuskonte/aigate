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


def _pick_price_rule(rows: list[PriceRule], model: str) -> PriceRule | None:
    for row in rows:
        if row.model is None or row.model == model:
            return row
    return None


async def get_price_rule(
    session: AsyncSession, *, org_id: str, provider: str, model: str
) -> PriceRule | None:
    """Best-matching price rule: exact (org, provider, model) then provider default (model=NULL)."""
    stmt = (
        select(PriceRule)
        .where(PriceRule.org_id == org_id, PriceRule.provider == provider)
        .order_by(PriceRule.model.is_(None), PriceRule.created_at.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return _pick_price_rule(list(rows), model)


async def get_markup_pct(session: AsyncSession, *, org_id: str, provider: str, model: str) -> Decimal:
    rule = await get_price_rule(session, org_id=org_id, provider=provider, model=model)
    return Decimal(rule.markup_pct) if rule else Decimal("0")


async def compute_billed_cost(
    session: AsyncSession,
    *,
    org_id: str,
    provider: str,
    model: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    raw_cost_from_provider: Decimal | None,
) -> tuple[Decimal | None, Decimal | None]:
    """
    Return (raw_cost, billed_cost). When provider sends raw_cost: apply markup.
    When raw_cost absent: use price_rule base prices (input/output per 1k) + markup if set.
    """
    rule = await get_price_rule(session, org_id=org_id, provider=provider, model=model)
    markup_pct = Decimal(rule.markup_pct) if rule else Decimal("0")
    mult = Decimal("1") + markup_pct / Decimal("100")

    if raw_cost_from_provider is not None:
        billed = (raw_cost_from_provider * mult).quantize(Decimal("0.00000001"))
        return (raw_cost_from_provider, billed)

    if rule is None or rule.input_price_per_1k is None or rule.output_price_per_1k is None:
        return (None, None)

    prompt = Decimal(prompt_tokens or 0)
    completion = Decimal(completion_tokens or 0)
    base = (prompt / 1000 * rule.input_price_per_1k + completion / 1000 * rule.output_price_per_1k).quantize(
        Decimal("0.00000001")
    )
    billed = (base * mult).quantize(Decimal("0.00000001"))
    return (None, billed)


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
