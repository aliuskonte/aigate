"""add agent_runs, agent_run_steps, assistant_tickets

Revision ID: 0005_agent
Revises: 0004_assistant
Create Date: 2026-02-09

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005_agent"
down_revision = "0004_assistant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "kb_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("assistant_kbs.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("query", sa.String(length=20_000), nullable=False),
        sa.Column("input_payload", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("output_payload", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.String(length=2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_runs_kb_id", "agent_runs", ["kb_id"])

    op.create_table(
        "agent_run_steps",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "run_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("agent_runs.id"),
            nullable=False,
        ),
        sa.Column("node_name", sa.String(length=64), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("input_snapshot", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("output_snapshot", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.String(length=2048), nullable=True),
    )
    op.create_index("ix_agent_run_steps_run_id", "agent_run_steps", ["run_id"])

    op.create_table(
        "assistant_tickets",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "run_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("agent_runs.id"),
            nullable=True,
        ),
        sa.Column("ticket_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("context", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_assistant_tickets_run_id", "assistant_tickets", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_assistant_tickets_run_id", table_name="assistant_tickets")
    op.drop_table("assistant_tickets")

    op.drop_index("ix_agent_run_steps_run_id", table_name="agent_run_steps")
    op.drop_table("agent_run_steps")

    op.drop_index("ix_agent_runs_kb_id", table_name="agent_runs")
    op.drop_table("agent_runs")
