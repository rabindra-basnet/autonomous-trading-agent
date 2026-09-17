"""Standalone Background Worker Daemon for Ingestion, Redis Streams, and AI Research Schedules."""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from app.config import settings
from app.core.logging import get_logger
from app.core.models import Candle, MacroIndicator, NewsItem, SocialMetric
from app.core.redis_bus import RedisStreamEventBus
from app.deps import check_provider_requirements
from app.execution.oms import OrderManagementSystem
from app.execution.paper_trader import PaperTradingEngine
from app.execution.risk_manager import RiskManager
from app.features.pipeline import FeaturePipeline
from app.ingestion.macro.fred_provider import FREDMacroProvider
from app.ingestion.market.global_provider import GlobalMarketDataProvider
from app.ingestion.news.gdelt_provider import GDELTNewsProvider
from app.ingestion.social.reddit_provider import RedditSocialProvider
from app.research.researcher import AutonomousResearcher
from app.storage.database import TimeSeriesDatabase
from app.storage.feature_store import PointInTimeFeatureStore
from app.storage.postgres import PostgresStorage
from app.strategies.momentum import MomentumTrendStrategy
from app.strategies.sentiment_momentum import SentimentMomentumStrategy
from app.symbol_service import symbol_catalog_sync_job, sync_symbol_catalog

logger = get_logger("BackgroundWorker")


class BackgroundWorkerDaemon:
    def __init__(self, symbols: list[str] | None = None):
        self.symbols = symbols or []
        self.postgres_storage = PostgresStorage()
        self.duckdb_storage = TimeSeriesDatabase(db_path=settings.duckdb_path)
        self.feature_store = PointInTimeFeatureStore()
        self.feature_pipeline = FeaturePipeline()
        self.risk_manager = RiskManager()
        self.oms = OrderManagementSystem()
        self.paper_trader = PaperTradingEngine(initial_cash=100000.0)
        self.event_bus = RedisStreamEventBus()
        self.researcher = AutonomousResearcher()

        self.candle_buffers: dict[str, list[Candle]] = {s: [] for s in self.symbols}
        self.strategies = [
            MomentumTrendStrategy(symbols=self.symbols),
            SentimentMomentumStrategy(symbols=self.symbols),
        ]
        self.running = False

    def _rebuild_strategies(self) -> None:
        """Sync candle buffers and strategy instances with the current symbol set."""
        for s in self.symbols:
            self.candle_buffers.setdefault(s, [])
        for stale in [s for s in self.candle_buffers if s not in self.symbols]:
            del self.candle_buffers[stale]
        self.strategies = [
            MomentumTrendStrategy(symbols=self.symbols),
            SentimentMomentumStrategy(symbols=self.symbols),
        ]

    async def _process_symbol(
        self,
        market_prov: GlobalMarketDataProvider,
        news: Sequence[NewsItem],
        social: Sequence[SocialMetric],
        macro: Sequence[MacroIndicator],
        sym: str,
        now: datetime,
    ) -> None:
        """Process one symbol end-to-end. Failures inside are isolated to this symbol."""
        price = await market_prov.fetch_ticker_price(sym)
        candle = Candle(
            symbol=sym,
            timestamp=now,
            open=price * 0.999,
            high=price * 1.002,
            low=price * 0.998,
            close=price,
            volume=250.0,
            exchange="worker_sim",
        )
        self.candle_buffers[sym].append(candle)
        if len(self.candle_buffers[sym]) > 300:
            self.candle_buffers[sym] = self.candle_buffers[sym][-300:]

        # 1. Insert to DuckDB lake
        self.duckdb_storage.insert_candles([candle])

        # 2. Compute Point-In-Time Features (on-chain metrics are fetched on demand only)
        feat_vec = self.feature_pipeline.compute_features(
            symbol=sym,
            candles=self.candle_buffers[sym],
            news=news,
            social=social,
            macro=macro,
        )
        self.feature_store.put_features(feat_vec)

        # 3. Strategy Signal & Execution
        current_prices = {s: self.candle_buffers[s][-1].close for s in self.symbols if self.candle_buffers[s]}
        portfolio = self.paper_trader.get_portfolio_state(current_prices)

        for strat in self.strategies:
            signals = strat.generate_signals(feat_vec, portfolio)
            for sig in signals:
                risk_res = self.risk_manager.validate_signal(sig, portfolio, price)
                if risk_res.approved:
                    order = self.oms.create_order_from_signal(sig, risk_res, price)
                    if order:
                        filled = await self.paper_trader.execute_order(order, price)
                        await self.postgres_storage.save_order(filled)

    async def ingestion_stream_job(self):
        """Continuous ingestion & strategy execution job."""
        logger.info("Starting Ingestion Stream Job...")
        news_prov = GDELTNewsProvider()
        social_prov = RedditSocialProvider()
        macro_prov = FREDMacroProvider()

        async with GlobalMarketDataProvider() as market_prov:
            while self.running:
                try:
                    # Refresh trading symbols from DB each cycle; expand the engine
                    # when the monitored set grows (e.g. after every minute fetch).
                    db_symbols = await self.postgres_storage.get_active_symbols()
                    if db_symbols != self.symbols:
                        self.symbols = db_symbols
                        self._rebuild_strategies()
                        logger.info("Symbols refreshed from DB: %s", ", ".join(self.symbols))
                    if not self.symbols:
                        await asyncio.sleep(5.0)
                        continue

                    now = datetime.now(UTC)
                    news = await news_prov.fetch_latest_news(limit=5)
                    social = await social_prov.fetch_metrics(self.symbols)
                    macro = await macro_prov.fetch_indicator("FEDFUNDS", now - timedelta(days=30))

                    for sym in self.symbols:
                        try:
                            await self._process_symbol(market_prov, news, social, macro, sym, now)
                        except Exception:
                            logger.exception("Skipping symbol %s after processing error in worker", sym)

                    await asyncio.sleep(2.0)
                except Exception:
                    logger.exception("Error in Ingestion Stream Job")
                    await asyncio.sleep(2.0)

    async def ai_research_scheduler_job(self, interval_seconds: int = 300):
        """Periodic background job executing autonomous AI hypothesis generation & walk-forward validation."""
        logger.info(f"AI Research Scheduler Job scheduled every {interval_seconds}s...")
        while self.running:
            try:
                await asyncio.sleep(interval_seconds)
                for sym in self.symbols:
                    if self.candle_buffers[sym] and len(self.candle_buffers[sym]) >= 40:
                        logger.info(f"[Scheduled Job] Running Autonomous AI Research cycle for {sym}...")
                        records = await self.researcher.run_experiment_loop(sym, self.candle_buffers[sym])
                        for r in records:
                            await self.postgres_storage.save_experiment(r)
            except Exception:
                logger.exception("Error in AI Research Scheduler Job")

    async def start(self):
        check_provider_requirements()
        self.running = True
        await self.postgres_storage.init_db()
        # Initial symbol catalog sync from the exchange, then rely on the periodic job
        found = await sync_symbol_catalog(self.postgres_storage)
        if found:
            logger.info("Worker seeded %d symbols from exchange catalog.", len(found))
        self.symbols = await self.postgres_storage.get_active_symbols()
        self._rebuild_strategies()
        if self.symbols:
            logger.info("Worker loaded %d trading symbols from DB.", len(self.symbols))
        else:
            logger.warning("No active symbols in DB. Add rows to the 'symbols' table to start ingestion.")
        await self.event_bus.start()
        logger.info("Background Worker Daemon started successfully.")

        # Run ingestion job, research cron, and symbol catalog refresh concurrently
        await asyncio.gather(
            self.ingestion_stream_job(),
            self.ai_research_scheduler_job(interval_seconds=120),
            symbol_catalog_sync_job(self.postgres_storage),
        )

    async def stop(self):
        self.running = False
        await self.event_bus.stop()
        self.duckdb_storage.close()
        logger.info("Background Worker Daemon stopped.")


def main():
    daemon = BackgroundWorkerDaemon()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(daemon.start())
    except KeyboardInterrupt:
        loop.run_until_complete(daemon.stop())


if __name__ == "__main__":
    main()
