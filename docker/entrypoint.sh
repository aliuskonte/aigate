#!/bin/bash
set -e

echo "Waiting for Postgres..."
python -c "
import os, sys, time
import asyncio
import asyncpg

async def wait():
    url = os.getenv('DATABASE_URL', '').replace('postgresql+asyncpg://', 'postgresql://')
    for i in range(60):
        try:
            conn = await asyncpg.connect(url)
            await conn.close()
            return
        except Exception as e:
            print(f'  attempt {i+1}/60: {e}')
            await asyncio.sleep(1)
    sys.exit(1)

asyncio.run(wait())
"
echo "Postgres ready."

echo "Running migrations..."
alembic upgrade head

echo "Starting uvicorn..."
exec uvicorn aigate.main:app --host 0.0.0.0 --port 8000
