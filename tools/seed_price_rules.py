"""Seed price_rules for an org (dev). Fills markup_pct and base prices per 1k tokens for billing when provider does not return raw_cost."""

from __future__ import annotations

import os
from decimal import Decimal
from datetime import datetime, timezone

from sqlalchemy import select

from aigate.core.config import get_settings
from aigate.storage.db import create_engine, create_sessionmaker
from aigate.storage.models import Organization, PriceRule


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


DEFAULT_RULES = [
    # Provider-default rule (model=NULL) applies to any qwen:* model unless overridden by a model-specific rule.
    {"provider": "qwen", "model": None, "markup_pct": Decimal("0")},
    {"provider": "qwen", "model": "qwen-flash", "markup_pct": Decimal("0")},
    {"provider": "qwen", "model": "qwen-turbo", "markup_pct": Decimal("0")},
    {"provider": "qwen", "model": "qwen-plus", "markup_pct": Decimal("0")},
    {"provider": "qwen", "model": "qwen-max", "markup_pct": Decimal("0")},
    {"provider": "qwen", "model": "qwen-vl-max", "markup_pct": Decimal("0")},
    {"provider": "qwen", "model": "qwen-vl-plus", "markup_pct": Decimal("0")},
]


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Seed price_rules for an org")
    parser.add_argument("--org-name", default="dev-org", help="Organization name")
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is not set")

    settings = get_settings()
    engine = create_engine(database_url=database_url)
    sessionmaker = create_sessionmaker(engine)

    async with sessionmaker() as session:
        org = (await session.execute(select(Organization).where(Organization.name == args.org_name))).scalar_one_or_none()
        if org is None:
            raise SystemExit(f"Organization '{args.org_name}' not found. Create it first (e.g. seed_dev_api_key).")

        inserted = 0
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
                input_price_per_1k=settings.qwen_default_input_price_per_1k,
                output_price_per_1k=settings.qwen_default_output_price_per_1k,
                created_at=utcnow(),
            )
            session.add(rule)
            inserted += 1
        await session.commit()

    await engine.dispose()
    print(f"Seeded {inserted} price_rules for org '{args.org_name}'.")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
