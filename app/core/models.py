"""Canonical domain models for the quantitative trading agent platform."""

from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class AssetClass(str, Enum):
    CRYPTO = "crypto"
    EQUITY = "equity"
    FOREX = "forex"
    COMMODITY = "commodity"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"


class OrderStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class SignalType(str, Enum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


# ==========================================
# Market Data Models
# ==========================================

class Candle(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    asset_class: AssetClass = AssetClass.CRYPTO
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: Optional[float] = None
    exchange: str = "default"

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def return_pct(self) -> float:
        if self.open == 0:
            return 0.0
        return (self.close - self.open) / self.open


class TradeEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    timestamp: datetime
    price: float
    size: float
    side: OrderSide
    exchange: str = "default"
    trade_id: Optional[str] = None


class OrderBookLevel(BaseModel):
    price: float
    size: float


class OrderBookSnapshot(BaseModel):
    symbol: str
    timestamp: datetime
    bids: List[OrderBookLevel] = Field(default_factory=list)
    asks: List[OrderBookLevel] = Field(default_factory=list)
    exchange: str = "default"

    @property
    def best_bid(self) -> Optional[float]:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        return self.asks[0].price if self.asks else None

    @property
    def spread(self) -> float:
        if self.best_bid and self.best_ask:
            return self.best_ask - self.best_bid
        return 0.0

    @property
    def imbalance(self) -> float:
        total_bid_vol = sum(b.size for b in self.bids[:5])
        total_ask_vol = sum(a.size for a in self.asks[:5])
        tot = total_bid_vol + total_ask_vol
        if tot == 0:
            return 0.0
        return (total_bid_vol - total_ask_vol) / tot


# ==========================================
# Information & Alternative Data Models
# ==========================================

class NewsItem(BaseModel):
    id: str
    source: str
    headline: str
    content: Optional[str] = None
    url: str = ""
    published_at: datetime
    symbols_mentioned: List[str] = Field(default_factory=list)
    sentiment_score: float = 0.0  # Range: -1.0 (very negative) to +1.0 (very positive)
    relevance_score: float = 1.0


class SocialMetric(BaseModel):
    platform: str
    symbol: str
    timestamp: datetime
    mention_count: int = 0
    mention_velocity_pct: float = 0.0  # % change over rolling window
    average_sentiment: float = 0.0      # Range: -1.0 to +1.0
    engagement_score: float = 0.0


class MacroIndicator(BaseModel):
    series_id: str
    name: str
    timestamp: datetime
    value: float
    unit: str = ""
    previous_value: Optional[float] = None
    change_pct: Optional[float] = None


class OnChainMetric(BaseModel):
    protocol: str
    symbol: str
    timestamp: datetime
    tvl_usd: float = 0.0
    active_addresses: int = 0
    exchange_net_inflow_usd: float = 0.0
    whale_transaction_count: int = 0


# ==========================================
# Feature Vectors
# ==========================================

class FeatureVector(BaseModel):
    symbol: str
    timestamp: datetime
    features: Dict[str, float] = Field(default_factory=dict)

    def get(self, key: str, default: float = 0.0) -> float:
        return self.features.get(key, default)


# ==========================================
# Strategy & Trading Models
# ==========================================

class TradingSignal(BaseModel):
    symbol: str
    timestamp: datetime
    strategy_name: str
    signal_type: SignalType
    strength: float = 1.0  # 0.0 to 1.0 confidence/scale
    suggested_size_pct: float = 0.10
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Order(BaseModel):
    id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    price: Optional[float] = None
    size: float
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime
    filled_at: Optional[datetime] = None
    avg_fill_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    commission: float = 0.0
    strategy_name: str = ""


class Position(BaseModel):
    symbol: str
    side: OrderSide
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    opened_at: datetime
    last_updated: datetime


class PortfolioState(BaseModel):
    timestamp: datetime
    cash_balance: float
    total_equity: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    peak_equity: float = 100000.0
    drawdown_pct: float = 0.0
    positions: Dict[str, Position] = Field(default_factory=dict)
    open_orders: List[Order] = Field(default_factory=list)


class RiskCheckResult(BaseModel):
    approved: bool
    adjusted_size: float
    rejection_reason: Optional[str] = None
    adjusted_stop_loss: Optional[float] = None
    adjusted_take_profit: Optional[float] = None


# ==========================================
# Research & Evaluation Models
# ==========================================

class BacktestResult(BaseModel):
    strategy_name: str
    symbol: str
    start_date: datetime
    end_date: datetime
    total_return_pct: float
    cagr_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    calmar_ratio: float
    win_rate_pct: float
    profit_factor: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    trades_log: List[Dict[str, Any]] = Field(default_factory=list)
    equity_curve: List[Dict[str, Any]] = Field(default_factory=list)
    parameters: Dict[str, Any] = Field(default_factory=dict)


class ExperimentRecord(BaseModel):
    experiment_id: str
    created_at: datetime
    hypothesis: str
    strategy_name: str
    dataset_range: str
    parameters: Dict[str, Any]
    metrics: Dict[str, float]
    promoted: bool = False
    notes: str = ""
