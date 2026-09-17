"""Add llm_usage table for LLM token usage & cost accounting

Revision ID: 003_llm_usage_table
Revises: 002_symbols_table
Create Date: 2026-09-17 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "003_llm_usage_table"
down_revision: str | None = "002_symbols_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_usage",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("model", sa.String(), nullable=False, index=True),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), default=0),
        sa.Column("completion_tokens", sa.Integer(), default=0),
        sa.Column("total_tokens", sa.Integer(), default=0),
        sa.Column("input_price_per_1m", sa.Float(), default=0.0),
        sa.Column("output_price_per_1m", sa.Float(), default=0.0),
        sa.Column("cost_usd", sa.Float(), default=0.0),
    )


def downgrade() -> None:
    op.drop_table("llm_usage")