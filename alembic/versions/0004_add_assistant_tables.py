"""add assistant tables for RAG ingestion jobs

Revision ID: 0004_assistant
Revises: 0003_base_prices
Create Date: 2026-02-09

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_assistant"
down_revision = "0003_base_prices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_kbs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_assistant_kbs_name"),
    )

    op.create_table(
        "assistant_documents",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "kb_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("assistant_kbs.id"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_uri", sa.String(length=512), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("kb_id", "source_uri", name="uq_assistant_documents_source"),
    )
    op.create_index("ix_assistant_documents_kb_id", "assistant_documents", ["kb_id"])

    op.create_table(
        "assistant_ingest_jobs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "kb_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("assistant_kbs.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("error", sa.String(length=1024), nullable=True),
        sa.Column("stats", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_assistant_ingest_jobs_kb_id", "assistant_ingest_jobs", ["kb_id"])


def downgrade() -> None:
    op.drop_index("ix_assistant_ingest_jobs_kb_id", table_name="assistant_ingest_jobs")
    op.drop_table("assistant_ingest_jobs")

    op.drop_index("ix_assistant_documents_kb_id", table_name="assistant_documents")
    op.drop_table("assistant_documents")

    op.drop_table("assistant_kbs")

