from __future__ import annotations

import argparse
import os
import secrets
from datetime import datetime, timezone

from sqlalchemy import select

from aigate.storage.db import create_engine, create_sessionmaker
from aigate.storage.models import ApiKey, Organization
from aigate.storage.repos import hash_api_key, key_prefix


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Create org + API key (dev)")
    parser.add_argument("--org-name", default="dev-org", help="Organization name")
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is not set")

    engine = create_engine(database_url=database_url)
    sessionmaker = create_sessionmaker(engine)

    api_key_plain = "agk_" + secrets.token_urlsafe(24)

    async with sessionmaker() as session:
        org = (await session.execute(select(Organization).where(Organization.name == args.org_name))).scalar_one_or_none()
        if org is None:
            org_row = Organization(name=args.org_name, created_at=utcnow())
            session.add(org_row)
            await session.flush()
            org_id = org_row.id
        else:
            org_id = org.id

        key_row = ApiKey(
            org_id=str(org_id),
            key_hash=hash_api_key(api_key_plain),
            key_prefix=key_prefix(api_key_plain),
            is_active=True,
            created_at=utcnow(),
        )
        session.add(key_row)
        await session.commit()

    await engine.dispose()

    print(api_key_plain)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
