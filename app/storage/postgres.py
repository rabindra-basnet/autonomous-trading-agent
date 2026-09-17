"""PostgreSQL async relational storage for transactions, orders, and experiment registry."""

from datetime import datetime, timezone
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    Column,
    String,
    Float,
    DateTime,
    Boolean,
    JSON,
    Integer,
    Text,
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, selectinload
from sqlalchemy import select, update
from app.config import settings
from app.core.models import Order, Position, ExperimentRecord

logger = logging.getLogger("PostgresStorage")

Base = declarative_base()


class DBOrder(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    symbol = Column(String, nullable=False, index=True)
    side = Column(String, nullable=False)
    order_type = Column(String, nullable=False)
    price = Column(Float, nullable=True)
    size = Column(Float, nullable=False)
    status = Column(String, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    filled_at = Column(DateTime(timezone=True), nullable=True)
    avg_fill_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    commission = Column(Float, default=0.0)
    strategy_name = Column(String, default="")


class DBPosition(Base):
    __tablename__ = "positions"

    symbol = Column(String, primary_key=True)
    side = Column(String, nullable=False)
    size = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=False)
    unrealized_pnl = Column(Float, default=0.0)
    realized_pnl = Column(Float, default=0.0)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    opened_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_updated = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class DBExperiment(Base):
    __tablename__ = "ai_experiments"

    experiment_id = Column(String, primary_key=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    hypothesis = Column(Text, nullable=False)
    strategy_name = Column(String, nullable=False, index=True)
    dataset_range = Column(String, nullable=False)
    parameters = Column(JSON, default=dict)
    metrics = Column(JSON, default=dict)
    promoted = Column(Boolean, default=False)
    notes = Column(Text, default="")


class PostgresStorage:
    def __init__(self):
        self.engine = create_async_engine(settings.database_url, echo=False)
        self.session_maker = async_sessionmaker(self.engine, expire_on_commit=False)

    async def init_db(self):
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("PostgreSQL database tables verified and created.")
        except Exception as e:
            logger.error(f"Error initializing PostgreSQL tables: {e}")

    async def save_order(self, order: Order):
        async with self.session_maker() as session:
            db_order = DBOrder(
                id=order.id,
                symbol=order.symbol,
                side=order.side.value,
                order_type=order.order_type.value,
                price=order.price,
                size=order.size,
                status=order.status.value,
                created_at=order.created_at,
                filled_at=order.filled_at,
                avg_fill_price=order.avg_fill_price,
                stop_loss=order.stop_loss,
                take_profit=order.take_profit,
                commission=order.commission,
                strategy_name=order.strategy_name,
            )
            session.add(db_order)
            await session.commit()

    async def get_orders(self, limit: int = 50) -> List[Dict[str, Any]]:
        async with self.session_maker() as session:
            result = await session.execute(select(DBOrder).order_by(DBOrder.created_at.desc()).limit(limit))
            rows = result.scalars().all()
            return [
                {
                    "id": r.id,
                    "symbol": r.symbol,
                    "side": r.side,
                    "size": r.size,
                    "status": r.status,
                    "price": r.avg_fill_price or r.price,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]

    async def save_experiment(self, exp: ExperimentRecord):
        async with self.session_maker() as session:
            db_exp = DBExperiment(
                experiment_id=exp.experiment_id,
                created_at=exp.created_at,
                hypothesis=exp.hypothesis,
                strategy_name=exp.strategy_name,
                dataset_range=exp.dataset_range,
                parameters=exp.parameters,
                metrics=exp.metrics,
                promoted=exp.promoted,
                notes=exp.notes,
            )
            session.add(db_exp)
            await session.commit()
