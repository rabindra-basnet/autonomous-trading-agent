"""Tests for backtester and autonomous AI research loop."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.core.models import AssetClass, Candle
from app.research.backtest import BacktestEngine
from app.research.researcher import AutonomousResearcher
from app.strategies.momentum import MomentumTrendStrategy


def _synthetic_candles(
    symbol: str = "BTC/USDT",
    hours: int = 720,
    start_price: float = 50000.0,
    seed: int = 42,
) -> list[Candle]:
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0001, 0.02, hours)
    closes = start_price * np.cumprod(1 + rets)
    now = datetime.now(UTC)
    candles = []
    for i in range(hours):
        ts = now - timedelta(hours=hours - i)
        close = float(closes[i])
        high = close * (1 + abs(rng.normal(0, 0.005)))
        low = close * (1 - abs(rng.normal(0, 0.005)))
        candles.append(
            Candle(
                symbol=symbol,
                asset_class=AssetClass.CRYPTO,
                timestamp=ts,
                open=float(closes[max(0, i - 1)]),
                high=max(high, close),
                low=min(low, close),
                close=close,
                volume=float(rng.uniform(100, 5000)),
                exchange="synthetic",
            )
        )
    return candles


@pytest.mark.asyncio
async def test_backtest_engine():
    candles = _synthetic_candles()

    strat = MomentumTrendStrategy(symbols=["BTC/USDT"])
    engine = BacktestEngine(initial_capital=100000.0)
    res = engine.run(strat, "BTC/USDT", candles)

    assert res.strategy_name == "momentum_trend"
    assert res.symbol == "BTC/USDT"
    assert len(res.equity_curve) > 0


@pytest.mark.asyncio
async def test_autonomous_research_loop(tmp_path):
    candles = _synthetic_candles(hours=960, seed=99)

    researcher = AutonomousResearcher()
    records = await researcher.run_experiment_loop("BTC/USDT", candles)

    assert len(records) > 0
    assert all(r.experiment_id and r.hypothesis and r.metrics for r in records)
