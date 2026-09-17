"""Typed event schemas and event topic naming rules."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventTopic(str, Enum):
    # Market Data
    MARKET_CANDLE = "market.candle"
    MARKET_TRADE = "market.trade"
    MARKET_ORDERBOOK = "market.orderbook"

    # Information & Alt Data
    INFO_NEWS = "info.news"
    INFO_SOCIAL = "info.social"
    INFO_MACRO = "info.macro"
    INFO_ONCHAIN = "info.onchain"

    # Feature & Processing
    FEATURES_UPDATED = "features.updated"

    # Strategy & Execution
    SIGNAL_GENERATED = "signal.generated"
    ORDER_SUBMITTED = "order.submitted"
    ORDER_FILLED = "order.filled"
    ORDER_CANCELLED = "order.cancelled"
    PORTFOLIO_UPDATED = "portfolio.updated"
    RISK_BREACH = "risk.breach"

    # Research & Management
    RESEARCH_HYPOTHESIS = "research.hypothesis"
    EXPERIMENT_COMPLETED = "research.experiment_completed"
    SYMBOLS_UPDATED = "symbols.updated"


class Event(BaseModel):
    topic: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = Field(default_factory=dict)
    source: str = "system"
    event_id: str | None = None
