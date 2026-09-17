"""PostgreSQL async relational storage for transactions, orders, and experiment registry with SSL support."""

import asyncio
import logging
import ssl
import urllib.parse
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    select,
)
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


from app.config import settings
from app.core.models import ExperimentRecord, Order, SymbolSpec

logger = logging.getLogger("PostgresStorage")


class DBOrder(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    symbol = Column(String, nullable=False, index=True)
    side = Column(String, nullable=False)
    order_type = Column(String, nullable=False)
    price = Column(Float, nullable=True)
    size = Column(Float, nullable=False)
    status = Column(String, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
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
    opened_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    last_updated = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class DBExperiment(Base):
    __tablename__ = "ai_experiments"

    experiment_id = Column(String, primary_key=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    hypothesis = Column(Text, nullable=False)
    strategy_name = Column(String, nullable=False, index=True)
    dataset_range = Column(String, nullable=False)
    parameters = Column(JSON, default=dict)
    metrics = Column(JSON, default=dict)
    promoted = Column(Boolean, default=False)
    notes = Column(Text, default="")


class DBSymbol(Base):
    __tablename__ = "symbols"

    symbol = Column(String, primary_key=True)
    asset_class = Column(String, default="crypto")
    category = Column(String, default="spot")
    timeframe = Column(String, default="1h")
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class DBLLMUsage(Base):
    __tablename__ = "llm_usage"

    id = Column(String, primary_key=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)
    model = Column(String, nullable=False, index=True)
    provider = Column(String, default="")
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    input_price_per_1m = Column(Float, default=0.0)
    output_price_per_1m = Column(Float, default=0.0)
    cost_usd = Column(Float, default=0.0)


def sanitize_asyncpg_url(raw_url: str) -> tuple[str, dict]:
    """
    Sanitize Neon/Postgres connection URLs for asyncpg driver.
    Converts sslmode / channel_binding into valid asyncpg SSL context.
    """
    parsed = urllib.parse.urlparse(raw_url)
    query_params = urllib.parse.parse_qs(parsed.query)

    connect_args: dict[str, Any] = {}
    # Only force an SSL context when the URL actually requires it. Local
    # Postgres uses sslmode=disable and has no SSL enabled; sending a client
    # certificate upgrade there makes the server reject the handshake.
    sslmode = (query_params.get("sslmode") or [""])[0].lower()
    explicit_ssl = (query_params.get("ssl") or [""])[0].lower() in {"true", "1", "require"}
    requires_ssl = sslmode in {"require", "verify-ca", "verify-full"} or explicit_ssl
    if requires_ssl:
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        connect_args["ssl"] = ssl_ctx

    # Strip asyncpg-incompatible query parameters from URL
    incompatible = {"sslmode", "channel_binding", "ssl"}
    filtered_query = {k: v for k, v in query_params.items() if k not in incompatible}
    new_query = urllib.parse.urlencode(filtered_query, doseq=True)
    clean_url = urllib.parse.urlunparse(parsed._replace(query=new_query))

    return clean_url, connect_args


class PostgresStorage:
    def __init__(self):
        clean_url, connect_args = sanitize_asyncpg_url(settings.database_url)
        self.engine = create_async_engine(
            clean_url,
            connect_args=connect_args,
            echo=False,
            pool_pre_ping=True,
        )
        self.session_maker = async_sessionmaker(self.engine, expire_on_commit=False)

    async def init_db(self):
        from alembic.config import Config

        from alembic import command

        try:
            cfg = Config(str(settings.alembic_config_path))
            cfg.set_main_option("script_location", str(settings.alembic_script_location))
            await asyncio.to_thread(command.upgrade, cfg, "head")
            logger.info("PostgreSQL database migrations applied successfully.")
        except Exception:
            logger.exception("Error running PostgreSQL database migrations")

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

    async def get_orders(self, limit: int = 50) -> list[dict[str, Any]]:
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

    async def get_active_symbols(self) -> list[str]:
        """Return active trading symbols from the DB symbols table."""
        try:
            async with self.session_maker() as session:
                result = await session.execute(
                    select(DBSymbol.symbol).where(DBSymbol.active.is_(True)).order_by(DBSymbol.symbol)
                )
                return [row[0] for row in result.fetchall()]
        except Exception as e:
            logger.error("Failed to load symbols from DB: %s", e)
            return []

    async def get_symbol_catalog(self, limit: int = 200, active_only: bool = False) -> list[dict[str, Any]]:
        """Return symbol rows with metadata (asset class, category, timeframe, active)."""
        try:
            async with self.session_maker() as session:
                stmt = select(DBSymbol).order_by(DBSymbol.symbol).limit(limit)
                if active_only:
                    stmt = stmt.where(DBSymbol.active.is_(True))
                result = await session.execute(stmt)
                rows = result.scalars().all()
                return [
                    {
                        "symbol": r.symbol,
                        "asset_class": r.asset_class,
                        "category": r.category,
                        "timeframe": r.timeframe,
                        "active": r.active,
                        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error("Failed to load symbol catalog from DB: %s", e)
            return []

    async def get_symbol(self, symbol: str) -> SymbolSpec | None:
        async with self.session_maker() as session:
            row = await session.get(DBSymbol, symbol)
            if not row:
                return None
            return SymbolSpec(
                symbol=row.symbol,
                asset_class=row.asset_class,
                category=row.category,
                timeframe=row.timeframe,
            )

    async def bulk_upsert_symbols(self, specs: Sequence[SymbolSpec]) -> int:
        upserted = 0
        async with self.session_maker() as session:
            for spec in specs:
                existing = await session.get(DBSymbol, spec.symbol)
                if existing:
                    existing.active = True
                    existing.asset_class = spec.asset_class
                    existing.category = spec.category
                    existing.timeframe = spec.timeframe
                    existing.updated_at = datetime.now(UTC)
                else:
                    session.add(
                        DBSymbol(
                            symbol=spec.symbol,
                            asset_class=spec.asset_class,
                            category=spec.category,
                            timeframe=spec.timeframe,
                        )
                    )
                upserted += 1
            await session.commit()
        return upserted

    async def upsert_symbol(
        self,
        symbol: str,
        asset_class: str = "crypto",
        timeframe: str = "1h",
        category: str = "spot",
    ):
        async with self.session_maker() as session:
            existing = await session.get(DBSymbol, symbol)
            if existing:
                existing.active = True
                existing.asset_class = asset_class
                existing.category = category
                existing.timeframe = timeframe
                existing.updated_at = datetime.now(UTC)
            else:
                session.add(
                    DBSymbol(
                        symbol=symbol,
                        asset_class=asset_class,
                        category=category,
                        timeframe=timeframe,
                    )
                )
            await session.commit()

    async def deactivate_symbol(self, symbol: str):
        async with self.session_maker() as session:
            existing = await session.get(DBSymbol, symbol)
            if existing:
                existing.active = False
                await session.commit()

    async def save_llm_usage(
        self,
        *,
        id: str,
        model: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        input_price_per_1m: float,
        output_price_per_1m: float,
        cost_usd: float,
    ):
        async with self.session_maker() as session:
            session.add(
                DBLLMUsage(
                    id=id,
                    model=model,
                    provider=provider,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    input_price_per_1m=input_price_per_1m,
                    output_price_per_1m=output_price_per_1m,
                    cost_usd=cost_usd,
                )
            )
            await session.commit()

    async def get_llm_usage_summary(self, limit: int = 100) -> list[dict[str, Any]]:
        async with self.session_maker() as session:
            result = await session.execute(select(DBLLMUsage).order_by(DBLLMUsage.created_at.desc()).limit(limit))
            rows = result.scalars().all()
            return [
                {
                    "id": r.id,
                    "model": r.model,
                    "provider": r.provider,
                    "prompt_tokens": r.prompt_tokens,
                    "completion_tokens": r.completion_tokens,
                    "total_tokens": r.total_tokens,
                    "cost_usd": r.cost_usd,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]
