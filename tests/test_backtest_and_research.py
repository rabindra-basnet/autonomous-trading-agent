"""Tests for backtester and autonomous AI research loop."""

import pytest
from datetime import datetime, timezone, timedelta
from app.ingestion.market.simulated import SimulatedMarketDataProvider
from app.strategies.momentum import MomentumTrendStrategy
from app.strategies.sentiment_momentum import SentimentMomentumStrategy
from app.research.backtest import BacktestEngine
from app.research.researcher import AutonomousResearcher


@pytest.mark.asyncio
async def test_backtest_engine():
    market_prov = SimulatedMarketDataProvider(seed=42)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)
    candles = await market_prov.fetch_historical_candles("BTC/USDT", "1h", start, end)

    strat = MomentumTrendStrategy(symbols=["BTC/USDT"])
    engine = BacktestEngine(initial_capital=100000.0)
    res = engine.run(strat, "BTC/USDT", candles)

    assert res.strategy_name == "momentum_trend"
    assert res.symbol == "BTC/USDT"
    assert len(res.equity_curve) > 0


@pytest.mark.asyncio
async def test_autonomous_research_loop(tmp_path):
    market_prov = SimulatedMarketDataProvider(seed=99)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=40)
    candles = await market_prov.fetch_historical_candles("BTC/USDT", "1h", start, end)

    from app.storage.registry import StrategyRegistry
    reg_file = str(tmp_path / "test_reg.json")
    registry = StrategyRegistry(registry_file=reg_file)

    researcher = AutonomousResearcher(registry=registry)
    records = await researcher.run_experiment_loop("BTC/USDT", candles)

    assert len(records) > 0
    assert len(registry.records) == len(records)
