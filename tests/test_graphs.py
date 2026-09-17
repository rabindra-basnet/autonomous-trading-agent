"""Tests for StateGraph workflow and visual chart/graph generation."""

import pytest
from app.research.agent_graph import TradingWorkflowGraph, TradingState
from app.features.charting import ChartGenerator
from app.core.models import Candle, AssetClass, BacktestResult
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_multi_agent_workflow_graph():
    graph = TradingWorkflowGraph()
    features = {
        "rsi_14": 52.0,
        "ema_12": 65000.0,
        "ema_26": 64000.0,
        "composite_sentiment": 0.40,
        "social_velocity_pct": 15.0,
        "macro_risk_on": 1.0,
    }

    state = await graph.execute_graph("BTC/USDT", 65000.0, features)

    assert isinstance(state, TradingState)
    assert len(state.graph_history) == 4
    assert "Node:MarketPerception" in state.graph_history
    assert "Node:SpecialistAnalysis" in state.graph_history
    assert "Node:RiskGovernor" in state.graph_history
    assert "Node:PostTradeReflection" in state.graph_history


def test_chart_generator_data_formatting():
    equity_curve = [
        {"timestamp": "2026-09-01T00:00:00Z", "equity": 100000.0, "drawdown_pct": 0.0},
        {"timestamp": "2026-09-02T00:00:00Z", "equity": 105000.0, "drawdown_pct": 0.0},
        {"timestamp": "2026-09-03T00:00:00Z", "equity": 103000.0, "drawdown_pct": 0.019},
    ]

    data = ChartGenerator.generate_equity_curve_data(equity_curve)
    assert len(data["timestamps"]) == 3
    assert data["peak_equity"] == 105000.0
    assert data["final_equity"] == 103000.0
