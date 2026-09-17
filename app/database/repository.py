"""Generic and feature-oriented repositories.

``DatabaseRepository`` is a reusable generic wrapper around an ``AsyncSession``
that provides ``create``, ``get`` and ``filter``. Feature repositories layer
domain methods on top, keeping endpoint/worker code free of ORM details.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import BinaryExpression, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import ExperimentRecord, Order, SymbolSpec
from app.database.base import Base
from app.database.models import DBExperiment, DBLLMUsage, DBOrder, DBSymbol

Model = TypeVar("Model", bound=Base)


class DatabaseRepository(Generic[Model]):
    """Repository for performing database queries against one model."""

    def __init__(self, model: type[Model], session: AsyncSession) -> None:
        self.model = model
        self.session = session

    async def create(self, data: dict[str, Any]) -> Model:
        instance = self.model(**data)
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def get(self, pk: Any) -> Model | None:
        return await self.session.get(self.model, pk)

    async def filter(self, *expressions: BinaryExpression) -> list[Model]:
        query = select(self.model)
        if expressions:
            query = query.where(*expressions)
        return list(await self.session.scalars(query))

    async def one(self, *expressions: BinaryExpression) -> Model | None:
        rows = await self.filter(*expressions)
        return rows[0] if rows else None


class OrderRepository(DatabaseRepository[DBOrder]):
    """Orders vertical slice: persistence of filled orders + reads."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(DBOrder, session)

    async def save_order(self, order: Order) -> DBOrder:
        return await self.create(
            {
                "id": order.id,
                "symbol": order.symbol,
                "side": order.side.value,
                "order_type": order.order_type.value,
                "price": order.price,
                "size": order.size,
                "status": order.status.value,
                "created_at": order.created_at,
                "filled_at": order.filled_at,
                "avg_fill_price": order.avg_fill_price,
                "stop_loss": order.stop_loss,
                "take_profit": order.take_profit,
                "commission": order.commission,
                "strategy_name": order.strategy_name,
            }
        )

    async def get_orders(self, limit: int = 50) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(DBOrder).order_by(DBOrder.created_at.desc()).limit(limit)
        )
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
            for r in result.scalars().all()
        ]


class ExperimentRepository(DatabaseRepository[DBExperiment]):
    """AI research vertical slice: hypothesis/experiment registry."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(DBExperiment, session)

    async def save_experiment(self, exp: ExperimentRecord) -> DBExperiment:
        return await self.create(
            {
                "experiment_id": exp.experiment_id,
                "created_at": exp.created_at,
                "hypothesis": exp.hypothesis,
                "strategy_name": exp.strategy_name,
                "dataset_range": exp.dataset_range,
                "parameters": exp.parameters,
                "metrics": exp.metrics,
                "promoted": exp.promoted,
                "notes": exp.notes,
            }
        )


class SymbolRepository(DatabaseRepository[DBSymbol]):
    """Symbol catalog vertical slice, including the auto-sync job."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(DBSymbol, session)

    async def get_active_symbols(self) -> list[str]:
        result = await self.session.execute(
            select(DBSymbol.symbol).where(DBSymbol.active.is_(True)).order_by(DBSymbol.symbol)
        )
        return [row[0] for row in result.fetchall()]

    async def get_symbol_catalog(self, limit: int = 200, active_only: bool = False) -> list[dict[str, Any]]:
        stmt = select(DBSymbol).order_by(DBSymbol.symbol).limit(limit)
        if active_only:
            stmt = stmt.where(DBSymbol.active.is_(True))
        result = await self.session.execute(stmt)
        return [
            {
                "symbol": r.symbol,
                "asset_class": r.asset_class,
                "category": r.category,
                "timeframe": r.timeframe,
                "active": r.active,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in result.scalars().all()
        ]

    async def get_symbol(self, symbol: str) -> SymbolSpec | None:
        row = await self.session.get(DBSymbol, symbol)
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
        for spec in specs:
            existing = await self.session.get(DBSymbol, spec.symbol)
            if existing:
                existing.active = True
                existing.asset_class = spec.asset_class
                existing.category = spec.category
                existing.timeframe = spec.timeframe
            else:
                self.session.add(
                    DBSymbol(
                        symbol=spec.symbol,
                        asset_class=spec.asset_class,
                        category=spec.category,
                        timeframe=spec.timeframe,
                    )
                )
            upserted += 1
        return upserted

    async def upsert_symbol(
        self,
        symbol: str,
        asset_class: str = "crypto",
        timeframe: str = "1h",
        category: str = "spot",
    ) -> None:
        existing = await self.session.get(DBSymbol, symbol)
        if existing:
            existing.active = True
            existing.asset_class = asset_class
            existing.category = category
            existing.timeframe = timeframe
        else:
            self.session.add(
                DBSymbol(
                    symbol=symbol,
                    asset_class=asset_class,
                    category=category,
                    timeframe=timeframe,
                )
            )

    async def deactivate_symbol(self, symbol: str) -> None:
        existing = await self.session.get(DBSymbol, symbol)
        if existing:
            existing.active = False


class LLMUsageRepository(DatabaseRepository[DBLLMUsage]):
    """LLM token usage & cost vertical slice."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(DBLLMUsage, session)

    async def save_llm_usage(self, *, data: dict[str, Any]) -> DBLLMUsage:
        return await self.create(data)

    async def get_llm_usage_summary(self, limit: int = 100) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(DBLLMUsage).order_by(DBLLMUsage.created_at.desc()).limit(limit)
        )
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
            for r in result.scalars().all()
        ]