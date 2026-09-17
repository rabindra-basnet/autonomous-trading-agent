"""Tests for risk management, OMS, and paper trading."""

from datetime import UTC, datetime

import pytest

from app.core.models import OrderSide, SignalType, TradingSignal
from app.execution.oms import OrderManagementSystem
from app.execution.paper_trader import PaperTradingEngine
from app.execution.risk_manager import RiskManager


@pytest.mark.asyncio
async def test_risk_manager_and_paper_trader():
    risk_mgr = RiskManager(
        max_position_size_pct=0.20,
        max_drawdown_limit_pct=0.10,
    )
    paper_trader = PaperTradingEngine(initial_cash=100000.0)
    oms = OrderManagementSystem()

    state = paper_trader.get_portfolio_state({"BTC/USDT": 50000.0})
    signal = TradingSignal(
        symbol="BTC/USDT",
        timestamp=datetime.now(UTC),
        strategy_name="test_strat",
        signal_type=SignalType.LONG,
        strength=1.0,
        suggested_size_pct=0.10,
    )

    risk_res = risk_mgr.validate_signal(signal, state, 50000.0)
    assert risk_res.approved is True
    assert risk_res.adjusted_size > 0

    order = oms.create_order_from_signal(signal, risk_res, 50000.0)
    assert order is not None
    assert order.side == OrderSide.BUY

    filled_order = await paper_trader.execute_order(order, 50000.0)
    assert filled_order.status.value == "filled"

    new_state = paper_trader.get_portfolio_state({"BTC/USDT": 55000.0})
    assert "BTC/USDT" in new_state.positions
    assert new_state.unrealized_pnl > 0
