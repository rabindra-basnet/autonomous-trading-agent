"""Master Trading System Orchestrator and Pipeline."""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from app.core.bus import EventBus
from app.core.events import Event, EventTopic
from app.core.models import (
    Candle,
    NewsItem,
    SocialMetric,
    MacroIndicator,
    OnChainMetric,
    TradingSignal,
    Order,
    PortfolioState,
)
from app.ingestion.market.base import BaseMarketDataProvider
from app.ingestion.news.base import BaseNewsProvider
from app.ingestion.social.base import BaseSocialProvider
from app.ingestion.macro.base import BaseMacroProvider
from app.ingestion.onchain.base import BaseOnChainProvider
from app.normalization.cleaner import DataQualityAssurance
from app.storage.database import TimeSeriesDatabase
from app.storage.feature_store import PointInTimeFeatureStore
from app.features.pipeline import FeaturePipeline
from app.execution.risk_manager import RiskManager
from app.execution.oms import OrderManagementSystem
from app.config import settings
from app.core.logging import get_logger

logger = get_logger("TradingPipeline")


class TradingSystemPipeline:
    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        market_provider: Optional[BaseMarketDataProvider] = None,
        news_provider: Optional[BaseNewsProvider] = None,
        social_provider: Optional[BaseSocialProvider] = None,
        macro_provider: Optional[BaseMacroProvider] = None,
        onchain_provider: Optional[BaseOnChainProvider] = None,
        strategies: Optional[List[BaseStrategy]] = None,
        db_path: str = "data/trading_agent.duckdb",
        initial_capital: float = 100000.0,
    ):
        self.symbols = symbols or settings.symbols
        self.market_provider = market_provider
        self.news_provider = news_provider
        self.social_provider = social_provider
        self.macro_provider = macro_provider
        self.onchain_provider = onchain_provider
        self.strategies = strategies

        # Subsystems
        self.bus = EventBus()
        self.db = TimeSeriesDatabase(db_path)
        self.feature_store = PointInTimeFeatureStore()
        self.feature_pipeline = FeaturePipeline()
        self.cleaner = DataQualityAssurance()
        self.risk_manager = RiskManager()
        self.oms = OrderManagementSystem()
        self.paper_trader = PaperTradingEngine(initial_cash=initial_capital)

        # In-memory streaming buffers
        self._candle_buffers: Dict[str, List[Candle]] = {s: [] for s in symbols}
        self._latest_news: List[NewsItem] = []
        self._latest_social: List[SocialMetric] = []
        self._latest_macro: List[MacroIndicator] = []
        self._latest_onchain: List[OnChainMetric] = []
        self._running = False

    async def _handle_market_candle(self, event: Event) -> None:
        candle = Candle(**event.payload)
        sym = candle.symbol

        # Validate
        prev = self._candle_buffers[sym][-1] if self._candle_buffers[sym] else None
        if not self.cleaner.validate_candle(candle, prev):
            return

        self._candle_buffers[sym].append(candle)
        if len(self._candle_buffers[sym]) > 500:
            self._candle_buffers[sym] = self._candle_buffers[sym][-500:]

        # Insert to DB
        self.db.insert_candles([candle])

        # Compute point-in-time feature vector
        feat_vec = self.feature_pipeline.compute_features(
            symbol=sym,
            candles=self._candle_buffers[sym],
            news=self._latest_news,
            social=self._latest_social,
            macro=self._latest_macro,
            onchain=self._latest_onchain,
        )
        self.feature_store.put_features(feat_vec)

        # Evaluate strategies
        prices = {s: self._candle_buffers[s][-1].close for s in self.symbols if self._candle_buffers[s]}
        portfolio = self.paper_trader.get_portfolio_state(prices)

        for strat in self.strategies:
            signals = strat.generate_signals(feat_vec, portfolio)
            for sig in signals:
                await self.bus.publish(
                    Event(
                        topic=EventTopic.SIGNAL_GENERATED.value,
                        payload=sig.model_dump(mode="json"),
                        source=strat.name,
                    )
                )

    async def _handle_signal(self, event: Event) -> None:
        signal = TradingSignal(**event.payload)
        sym = signal.symbol
        price = self._candle_buffers[sym][-1].close if self._candle_buffers[sym] else 0.0
        if price <= 0:
            return

        prices = {s: self._candle_buffers[s][-1].close for s in self.symbols if self._candle_buffers[s]}
        portfolio = self.paper_trader.get_portfolio_state(prices)

        risk_res = self.risk_manager.validate_signal(signal, portfolio, price)
        if not risk_res.approved:
            logger.info(f"Signal rejected by RiskManager: {risk_res.rejection_reason}")
            return

        order = self.oms.create_order_from_signal(signal, risk_res, price)
        if order:
            await self.paper_trader.execute_order(order, price)

    async def start(self) -> None:
        """Start the real-time event-driven trading loop."""
        self._running = True
        await self.bus.start()

        # Subscribe handlers
        self.bus.subscribe(EventTopic.MARKET_CANDLE.value, self._handle_market_candle)
        self.bus.subscribe(EventTopic.SIGNAL_GENERATED.value, self._handle_signal)

        logger.info("Trading System Pipeline initialized and running.")

    async def stop(self) -> None:
        self._running = False
        await self.bus.stop()
        self.db.close()
        logger.info("Trading System Pipeline stopped.")
