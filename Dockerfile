FROM python:3.11-slim

WORKDIR /app

# Install runtime deps (no build deps for psycopg-binary)
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY requirements.txt .

# Install Python deps
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY src/ ./src/
COPY docs/ ./docs/
COPY memory-bank/ ./memory-bank/
COPY alembic/ ./alembic/
COPY alembic.ini .
COPY tools/ ./tools/

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Entrypoint: wait for DB, migrate, run
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
