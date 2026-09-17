"""Initial PostgreSQL schema for orders, positions, and AI experiments

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-09-17 19:55:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create orders table
    op.create_table(
        'orders',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('symbol', sa.String(), nullable=False, index=True),
        sa.Column('side', sa.String(), nullable=False),
        sa.Column('order_type', sa.String(), nullable=False),
        sa.Column('price', sa.Float(), nullable=True),
        sa.Column('size', sa.Float(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('filled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('avg_fill_price', sa.Float(), nullable=True),
        sa.Column('stop_loss', sa.Float(), nullable=True),
        sa.Column('take_profit', sa.Float(), nullable=True),
        sa.Column('commission', sa.Float(), default=0.0),
        sa.Column('strategy_name', sa.String(), default=""),
    )

    # Create positions table
    op.create_table(
        'positions',
        sa.Column('symbol', sa.String(), primary_key=True),
        sa.Column('side', sa.String(), nullable=False),
        sa.Column('size', sa.Float(), nullable=False),
        sa.Column('entry_price', sa.Float(), nullable=False),
        sa.Column('current_price', sa.Float(), nullable=False),
        sa.Column('unrealized_pnl', sa.Float(), default=0.0),
        sa.Column('realized_pnl', sa.Float(), default=0.0),
        sa.Column('stop_loss', sa.Float(), nullable=True),
        sa.Column('take_profit', sa.Float(), nullable=True),
        sa.Column('opened_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_updated', sa.DateTime(timezone=True), nullable=True),
    )

    # Create ai_experiments table
    op.create_table(
        'ai_experiments',
        sa.Column('experiment_id', sa.String(), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('hypothesis', sa.Text(), nullable=False),
        sa.Column('strategy_name', sa.String(), nullable=False, index=True),
        sa.Column('dataset_range', sa.String(), nullable=False),
        sa.Column('parameters', sa.JSON(), default=dict),
        sa.Column('metrics', sa.JSON(), default=dict),
        sa.Column('promoted', sa.Boolean(), default=False),
        sa.Column('notes', sa.Text(), default=""),
    )


def downgrade() -> None:
    op.drop_table('ai_experiments')
    op.drop_table('positions')
    op.drop_table('orders')
