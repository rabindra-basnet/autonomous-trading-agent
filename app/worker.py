"""Standalone Background Worker Daemon for Ingestion, Redis Streams, and AI Research Schedules."""

import asyncio
import logging
import signal
from datetime import datetime, timezone, timedelta
from typing import List

from app.config import settings
from app.core.models import Candle
from app.core.redis_bus import RedisStreamEventBus
from app.storage.database import TimeSeriesDatabase
from app.storage.postgres import PostgresStorage
from app.storage.feature_store import PointInTimeFeatureStore
from app.features.pipeline import FeaturePipeline
from app.execution.risk_manager import RiskManager
from app.execution.oms import OrderManagementSystem
from app.execution.paper_trader import PaperTradingEngine
from app.strategies.momentum import MomentumTrendStrategy
from app.strategies.sentiment_momentum import SentimentMomentumStrategy
from app.research.researcher import AutonomousResearcher
from app.ingestion.market.simulated import SimulatedMarketDataProvider
from app.ingestion.news.simulated import SimulatedNewsProvider
from app.ingestion.social.simulated import SimulatedSocialProvider
from app.ingestion.macro.simulated import SimulatedMacroProvider
from app.ingestion.onchain.simulated import SimulatedOnChainProvider

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("BackgroundWorker")


class BackgroundWorkerDaemon:
    def __init__(self):
        self.symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
        self.postgres_storage = PostgresStorage()
        self.duckdb_storage = TimeSeriesDatabase(db_path=settings.duckdb_path)
        self.feature_store = PointInTimeFeatureStore()
        self.feature_pipeline = FeaturePipeline()
        self.risk_manager = RiskManager()
        self.oms = OrderManagementSystem()
        self.paper_trader = PaperTradingEngine(initial_cash=100000.0)
        self.event_bus = RedisStreamEventBus()
        self.researcher = AutonomousResearcher()

        self.candle_buffers = {s: [] for s in self.symbols}
        self.strategies = [
            MomentumTrendStrategy(symbols=self.symbols),
            SentimentMomentumStrategy(symbols=self.symbols),
        ]
        self.running = False

    async def ingestion_stream_job(self):
        """Continuous ingestion & strategy execution job."""
        logger.info("Starting Ingestion Stream Job...")
        market_prov = SimulatedMarketDataProvider(seed=42)
        news_prov = SimulatedNewsProvider()
        social_prov = SimulatedSocialProvider()
        macro_prov = SimulatedMacroProvider()
        onchain_prov = SimulatedOnChainProvider()

        while self.running:
            try:
                now = datetime.now(timezone.utc)
                news = await news_prov.fetch_latest_news(limit=5)
                social = await social_prov.fetch_metrics(self.symbols)
                macro = await macro_prov.fetch_indicator("FEDFUNDS", now - timedelta(days=30))

                for sym in self.symbols:
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

                    # 2. Compute Point-In-Time Features
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

                await asyncio.sleep(2.0)
            except Exception as e:
                logger.error(f"Error in Ingestion Stream Job: {e}")
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
            except Exception as e:
                logger.error(f"Error in AI Research Scheduler Job: {e}")

    async def start(self):
        self.running = True
        await self.postgres_storage.init_db()
        await self.event_bus.start()
        logger.info("Background Worker Daemon started successfully.")

        # Run ingestion job and research cron concurrently
        await asyncio.gather(
            self.ingestion_stream_job(),
            self.ai_research_scheduler_job(interval_seconds=120),
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
