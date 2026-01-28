"""Seed price_rules for an org (dev). Fills markup_pct and base prices per 1k tokens for billing when provider does not return raw_cost."""

from __future__ import annotations

import os
from decimal import Decimal
from datetime import datetime, timezone

from sqlalchemy import select

from aigate.storage.db import create_engine, create_sessionmaker
from aigate.storage.models import Organization, PriceRule


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


# Placeholder base prices (USD per 1k tokens). Replace with real provider prices.
QWEN_DEFAULT_INPUT_PER_1K = Decimal("0.0005")
QWEN_DEFAULT_OUTPUT_PER_1K = Decimal("0.001")

DEFAULT_RULES = [
    {"provider": "qwen", "model": "qwen-turbo", "markup_pct": Decimal("0")},
    {"provider": "qwen", "model": "qwen-plus", "markup_pct": Decimal("0")},
    {"provider": "qwen", "model": "qwen-max", "markup_pct": Decimal("0")},
]


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Seed price_rules for an org")
    parser.add_argument("--org-name", default="dev-org", help="Organization name")
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is not set")

    engine = create_engine(database_url=database_url)
    sessionmaker = create_sessionmaker(engine)

    async with sessionmaker() as session:
        org = (await session.execute(select(Organization).where(Organization.name == args.org_name))).scalar_one_or_none()
        if org is None:
            raise SystemExit(f"Organization '{args.org_name}' not found. Create it first (e.g. seed_dev_api_key).")

        for r in DEFAULT_RULES:
            existing = (
                await session.execute(
                    select(PriceRule).where(
                        PriceRule.org_id == org.id,
                        PriceRule.provider == r["provider"],
                        PriceRule.model == r["model"],
                    )
                )
            ).scalar_one_or_none()
            if existing:
                continue
            rule = PriceRule(
                org_id=org.id,
                provider=r["provider"],
                model=r["model"],
                markup_pct=r["markup_pct"],
                input_price_per_1k=QWEN_DEFAULT_INPUT_PER_1K,
                output_price_per_1k=QWEN_DEFAULT_OUTPUT_PER_1K,
                created_at=utcnow(),
            )
            session.add(rule)
        await session.commit()

    await engine.dispose()
    print(f"Seeded {len(DEFAULT_RULES)} price_rules for org '{args.org_name}'.")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
