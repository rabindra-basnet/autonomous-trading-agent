"""Structural Protocol interfaces decoupling providers, features, risk, execution, and research."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from typing import Protocol

from app.core.models import (
    BacktestResult,
    Candle,
    ExperimentRecord,
    FeatureVector,
    MacroIndicator,
    NewsItem,
    OnChainMetric,
    Order,
    PortfolioState,
    RiskCheckResult,
    SocialMetric,
    TradeEvent,
    TradingSignal,
)


class MarketDataProvider(Protocol):
    name: str

    async def fetch_historical_candles(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> Sequence[Candle]:
        """Fetch historical OHLCV candles."""
        ...

    async def fetch_ticker_price(self, symbol: str) -> float:
        """Fetch current price for symbol."""
        ...

    def stream_trades(self, symbols: list[str]) -> AsyncIterator[TradeEvent]:
        """Stream real-time trade events."""
        ...

    def stream_candles(self, symbols: list[str], timeframe: str) -> AsyncIterator[Candle]:
        """Stream real-time candle updates."""
        ...


class NewsProvider(Protocol):
    name: str

    async def fetch_latest_news(self, keywords: list[str] | None = None, limit: int = 50) -> Sequence[NewsItem]:
        """Fetch recent news articles."""
        ...

    def stream_news(self, keywords: list[str] | None = None) -> AsyncIterator[NewsItem]:
        """Stream live news events."""
        ...


class SocialProvider(Protocol):
    name: str

    async def fetch_metrics(self, symbols: list[str]) -> Sequence[SocialMetric]:
        """Fetch aggregated social metrics (mentions, sentiment, velocity)."""
        ...

    def stream_social_signals(self, symbols: list[str]) -> AsyncIterator[SocialMetric]:
        """Stream live social signal updates."""
        ...


class MacroProvider(Protocol):
    name: str

    async def fetch_indicator(self, series_id: str, start_date: datetime) -> Sequence[MacroIndicator]:
        """Fetch macroeconomic time series."""
        ...


class OnChainProvider(Protocol):
    name: str

    async def fetch_metrics(self, symbol: str) -> Sequence[OnChainMetric]:
        """Fetch on-chain metrics (TVL, net inflows, whale movements)."""
        ...


class FeaturePipelineProtocol(Protocol):
    def compute_features(
        self,
        candles: Sequence[Candle],
        news: Sequence[NewsItem],
        social: Sequence[SocialMetric],
        macro: Sequence[MacroIndicator],
        onchain: Sequence[OnChainMetric],
    ) -> FeatureVector:
        """Compute unified feature vector from multimodal inputs."""
        ...


class StrategyProtocol(Protocol):
    name: str
    symbols: list[str]

    def generate_signals(
        self,
        feature_vector: FeatureVector,
        portfolio: PortfolioState,
    ) -> list[TradingSignal]:
        """Generate actionable trade signals from features & state."""
        ...


class RiskManagerProtocol(Protocol):
    def validate_signal(
        self,
        signal: TradingSignal,
        portfolio: PortfolioState,
        current_price: float,
    ) -> RiskCheckResult:
        """Validate, size, and guardrail an incoming trading signal."""
        ...

    def check_portfolio_health(self, portfolio: PortfolioState) -> bool:
        """Evaluate circuit breakers and maximum drawdown limits."""
        ...


class ExecutionEngineProtocol(Protocol):
    async def submit_order(self, order: Order) -> Order:
        """Submit an order for execution."""
        ...

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        ...

    def get_portfolio_state(self) -> PortfolioState:
        """Return current real-time portfolio state."""
        ...


class ResearchAgentProtocol(Protocol):
    async def generate_hypotheses(self) -> list[str]:
        """Generate market / feature / strategy hypotheses."""
        ...

    async def evaluate_strategy(self, strategy: StrategyProtocol, dataset_name: str) -> BacktestResult:
        """Run walk-forward backtest evaluation on historical data."""
        ...

    async def run_experiment_loop(self) -> list[ExperimentRecord]:
        """Run self-improvement cycle and promote winning strategies."""
        ...
