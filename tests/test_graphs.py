"""Tests for the multi-agent workflow graph."""

import pytest

from app.research.agent_graph import TradingState, TradingWorkflowGraph


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
