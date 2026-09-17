"""StateGraph workflow engine orchestrating multi-agent analysis, debate, risk gating, and execution."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.core.models import RiskCheckResult, SignalType, TradingSignal
from app.execution.risk_manager import RiskManager
from app.research.multi_agent import AgentOpinion, MultiAgentConsensus, MultiAgentTradingDesk


class TradingState(BaseModel):
    """Shared state dictionary passed across the multi-agent graph nodes."""

    symbol: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    current_price: float = 0.0
    features: dict[str, float] = Field(default_factory=dict)

    # Node outputs
    analyst_opinions: list[AgentOpinion] = Field(default_factory=list)
    bull_case: str = ""
    bear_case: str = ""
    consensus: MultiAgentConsensus | None = None
    risk_result: RiskCheckResult | None = None
    trade_signal: TradingSignal | None = None
    execution_status: str = "PENDING"
    reflection_notes: str = ""
    graph_history: list[str] = Field(default_factory=list)


class TradingWorkflowGraph:
    """Cyclic Directed Graph for Autonomous Multi-Agent Trading & Decision Reflection."""

    def __init__(self, trading_desk: MultiAgentTradingDesk | None = None, risk_manager: RiskManager | None = None):
        self.desk = trading_desk or MultiAgentTradingDesk()
        self.risk_manager = risk_manager or RiskManager()

    async def _node_market_perception(self, state: TradingState) -> TradingState:
        """Node 1: Extract features and ingest state context, validating data availability."""
        state.graph_history.append("Node:MarketPerception")
        if state.current_price <= 0.0 or not state.features:
            state.execution_status = "HALTED_NO_MARKET_DATA"
            state.reflection_notes = (
                f"No market data for {state.symbol} (price={state.current_price}, "
                f"features={len(state.features)}). Start ingestion via POST /api/ingestion/start "
                "and wait for the first tick before requesting an AI decision."
            )
        return state

    async def _node_specialist_analysis(self, state: TradingState) -> TradingState:
        """Node 2: Multi-agent specialist analysts (Technical, Sentiment, Macro)."""
        state.graph_history.append("Node:SpecialistAnalysis")
        if state.execution_status == "HALTED_NO_MARKET_DATA":
            return state
        # Run consensus & debate through the multi-agent trading desk
        consensus = await self.desk.evaluate_market(
            {
                "symbol": state.symbol,
                "current_price": state.current_price,
                "features": state.features,
            }
        )
        state.consensus = consensus
        state.analyst_opinions = consensus.agent_opinions
        state.bull_case = consensus.bull_case_summary
        state.bear_case = consensus.bear_case_summary
        return state

    async def _node_risk_governor(self, state: TradingState) -> TradingState:
        """Node 3: Deterministic risk validation and sizing guardrails."""
        state.graph_history.append("Node:RiskGovernor")
        if state.execution_status == "HALTED_NO_MARKET_DATA":
            return state
        if not state.consensus or state.consensus.final_action == "HOLD":
            state.execution_status = "HOLD"
            return state

        sig_type = SignalType.LONG if state.consensus.final_action == "BUY" else SignalType.SHORT
        signal = TradingSignal(
            symbol=state.symbol,
            timestamp=state.timestamp,
            strategy_name="multi_agent_graph",
            signal_type=sig_type,
            strength=state.consensus.conviction_score,
            suggested_size_pct=0.15,
            stop_loss=state.current_price * (1 - state.consensus.suggested_stop_loss_pct / 100.0)
            if sig_type == SignalType.LONG
            else state.current_price * (1 + state.consensus.suggested_stop_loss_pct / 100.0),
            target_price=state.current_price * (1 + state.consensus.suggested_take_profit_pct / 100.0)
            if sig_type == SignalType.LONG
            else state.current_price * (1 - state.consensus.suggested_take_profit_pct / 100.0),
        )
        state.trade_signal = signal

        # Risk check
        from app.core.models import PortfolioState

        mock_portfolio = PortfolioState(
            timestamp=state.timestamp,
            cash_balance=100000.0,
            total_equity=100000.0,
        )
        risk_res = self.risk_manager.validate_signal(signal, mock_portfolio, state.current_price)
        state.risk_result = risk_res
        if not risk_res.approved:
            state.execution_status = f"REJECTED_BY_RISK: {risk_res.rejection_reason}"
        else:
            state.execution_status = "APPROVED_FOR_EXECUTION"

        return state

    async def _node_post_trade_reflection(self, state: TradingState) -> TradingState:
        """Node 4: Post-execution reflection and recursive state update."""
        state.graph_history.append("Node:PostTradeReflection")
        if state.execution_status == "HALTED_NO_MARKET_DATA":
            return state
        if state.execution_status == "APPROVED_FOR_EXECUTION" and state.consensus:
            state.reflection_notes = f"Consensus {state.consensus.final_action} with conviction {state.consensus.conviction_score:.2f} successfully sized and dispatched."
        else:
            state.reflection_notes = f"State halted: {state.execution_status}"
        return state

    async def execute_graph(
        self,
        symbol: str,
        current_price: float,
        features: dict[str, float],
    ) -> TradingState:
        """Execute state machine transitions across graph nodes."""
        state = TradingState(
            symbol=symbol,
            current_price=current_price,
            features=features,
        )

        # Graph execution sequence:
        # MarketPerception -> SpecialistAnalysis -> RiskGovernor -> PostTradeReflection
        state = await self._node_market_perception(state)
        state = await self._node_specialist_analysis(state)
        state = await self._node_risk_governor(state)
        state = await self._node_post_trade_reflection(state)

        return state
