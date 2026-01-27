"""add ledger tables

Revision ID: 0002_ledger
Revises: 0001_init
Create Date: 2026-01-27

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_ledger"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "price_rules",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("org_id", sa.dialects.postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("markup_pct", sa.Numeric(10, 4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "provider", "model", name="uq_price_rules_scope"),
    )
    op.create_index("ix_price_rules_org_id", "price_rules", ["org_id"])

    op.create_table(
        "requests",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("org_id", sa.dialects.postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_requests_request_id", "requests", ["request_id"])
    op.create_index("ix_requests_org_id", "requests", ["org_id"])

    op.create_table(
        "usage_events",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("org_id", sa.dialects.postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("request_db_id", sa.dialects.postgresql.UUID(as_uuid=False), sa.ForeignKey("requests.id"), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("raw_cost", sa.Numeric(18, 8), nullable=True),
        sa.Column("billed_cost", sa.Numeric(18, 8), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_usage_events_org_id", "usage_events", ["org_id"])
    op.create_index("ix_usage_events_request_db_id", "usage_events", ["request_db_id"])


def downgrade() -> None:
    op.drop_index("ix_usage_events_request_db_id", table_name="usage_events")
    op.drop_index("ix_usage_events_org_id", table_name="usage_events")
    op.drop_table("usage_events")

    op.drop_index("ix_requests_org_id", table_name="requests")
    op.drop_index("ix_requests_request_id", table_name="requests")
    op.drop_table("requests")

    op.drop_index("ix_price_rules_org_id", table_name="price_rules")
    op.drop_table("price_rules")
