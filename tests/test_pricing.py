"""Tests for compute_billed_cost (billed_cost from raw_cost+markup or from base prices)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from aigate.storage.repos import compute_billed_cost


class _FakeRule:
    def __init__(
        self,
        markup_pct: Decimal,
        input_price_per_1k: Decimal | None = None,
        output_price_per_1k: Decimal | None = None,
    ) -> None:
        self.markup_pct = markup_pct
        self.input_price_per_1k = input_price_per_1k
        self.output_price_per_1k = output_price_per_1k


@pytest.mark.asyncio
async def test_compute_billed_cost_with_raw_cost_applies_markup() -> None:
    session = AsyncMock()
    with patch("aigate.storage.repos.get_price_rule", new_callable=AsyncMock) as get_rule:
        get_rule.return_value = _FakeRule(markup_pct=Decimal("10"))
        raw, billed = await compute_billed_cost(
            session,
            org_id="org-1",
            provider="qwen",
            model="qwen-turbo",
            prompt_tokens=100,
            completion_tokens=50,
            raw_cost_from_provider=Decimal("0.01"),
        )
    assert raw == Decimal("0.01")
    assert billed == Decimal("0.011")  # 0.01 * 1.1


@pytest.mark.asyncio
async def test_compute_billed_cost_without_raw_uses_base_prices() -> None:
    session = AsyncMock()
    with patch("aigate.storage.repos.get_price_rule", new_callable=AsyncMock) as get_rule:
        get_rule.return_value = _FakeRule(
            markup_pct=Decimal("0"),
            input_price_per_1k=Decimal("0.001"),
            output_price_per_1k=Decimal("0.002"),
        )
        raw, billed = await compute_billed_cost(
            session,
            org_id="org-1",
            provider="qwen",
            model="qwen-turbo",
            prompt_tokens=1000,
            completion_tokens=500,
            raw_cost_from_provider=None,
        )
    assert raw is None
    # 1 * 0.001 + 0.5 * 0.002 = 0.001 + 0.001 = 0.002
    assert billed == Decimal("0.002")


@pytest.mark.asyncio
async def test_compute_billed_cost_no_rule_returns_none_none() -> None:
    session = AsyncMock()
    with patch("aigate.storage.repos.get_price_rule", new_callable=AsyncMock) as get_rule:
        get_rule.return_value = None
        raw, billed = await compute_billed_cost(
            session,
            org_id="org-1",
            provider="qwen",
            model="qwen-turbo",
            prompt_tokens=100,
            completion_tokens=50,
            raw_cost_from_provider=None,
        )
    assert raw is None
    assert billed is None
