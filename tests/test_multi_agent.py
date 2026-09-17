"""Tests for Multi-Agent Trading Desk and consensus engine."""

import pytest

from app.research.multi_agent import MultiAgentConsensus, MultiAgentTradingDesk


@pytest.mark.asyncio
async def test_multi_agent_trading_desk_fallback():
    desk = MultiAgentTradingDesk()
    market_data = {
        "symbol": "BTC/USDT",
        "current_price": 68500.0,
        "features": {
            "rsi_14": 42.0,
            "ema_12": 68200.0,
            "ema_26": 67800.0,
            "composite_sentiment": 0.45,
            "social_velocity_pct": 25.0,
            "macro_risk_on": 1.0,
        },
    }

    consensus = await desk.evaluate_market(market_data)
    assert isinstance(consensus, MultiAgentConsensus)
    assert consensus.final_action in ["BUY", "SELL", "HOLD"]
    assert 0.0 <= consensus.conviction_score <= 1.0
    assert len(consensus.agent_opinions) >= 3
