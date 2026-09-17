"""Add symbols table for DB-backed dynamic trading symbol management

Revision ID: 002_symbols_table
Revises: 001_initial_schema
Create Date: 2026-09-17 20:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "002_symbols_table"
down_revision: str | None = "001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "symbols",
        sa.Column("symbol", sa.String(), primary_key=True),
        sa.Column("asset_class", sa.String(), default="crypto"),
        sa.Column("category", sa.String(), default="spot"),
        sa.Column("timeframe", sa.String(), default="1h"),
        sa.Column("active", sa.Boolean(), nullable=False, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("symbols")
