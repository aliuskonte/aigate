"""add base price columns to price_rules for billed_cost when raw_cost absent

Revision ID: 0003_base_prices
Revises: 0002_ledger
Create Date: 2026-01-27

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_base_prices"
down_revision = "0002_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "price_rules",
        sa.Column("input_price_per_1k", sa.Numeric(18, 8), nullable=True),
    )
    op.add_column(
        "price_rules",
        sa.Column("output_price_per_1k", sa.Numeric(18, 8), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("price_rules", "output_price_per_1k")
    op.drop_column("price_rules", "input_price_per_1k")
