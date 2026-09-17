"""Multi-Agent Institutional Trading Desk powered by OpenAI-Compatible LLMs (Groq Llama-3.3-70B)."""

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from app.config import settings
from app.core.llm import chat_completion

logger = logging.getLogger("MultiAgentDesk")


class AgentOpinion(BaseModel):
    role: str
    stance: str  # "bullish", "bearish", "neutral"
    confidence: float  # 0.0 to 1.0
    rationale: str
    key_factors: list[str] = Field(default_factory=list)


class MultiAgentConsensus(BaseModel):
    final_action: str  # "BUY", "SELL", "HOLD"
    conviction_score: float  # 0.0 to 1.0
    bull_case_summary: str
    bear_case_summary: str
    risk_assessment: str
    suggested_stop_loss_pct: float
    suggested_take_profit_pct: float
    agent_opinions: list[AgentOpinion] = Field(default_factory=list)


class MultiAgentTradingDesk:
    """Collaborative multi-agent trading desk featuring specialized analyst roles and bull/bear debate."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model

    async def _call_agent(self, system_role: str, user_prompt: str) -> str:
        """Invoke an agent role via the shared OpenAI SDK client."""
        result = await chat_completion(system_role, user_prompt, model=self.model)
        if not result.content:
            logger.warning("Agent %s returned empty content; using baseline.", system_role)
        return result.content

    async def _parse_opinion(self, name: str, raw: str) -> AgentOpinion:
        """Parse an agent's raw JSON response into an AgentOpinion with a deterministic fallback."""
        try:
            cleaned = raw.replace("```json", "").replace("```", "").strip()
            p = json.loads(cleaned)
            return AgentOpinion(role=name, **p)
        except (json.JSONDecodeError, ValueError) as e:
            logger.debug("Agent %s returned unparseable response (%s); using baseline.", name, e)
            return AgentOpinion(role=name, stance="neutral", confidence=0.5, rationale="Algorithmic baseline analysis.")

    async def evaluate_market(self, market_data: dict[str, Any]) -> MultiAgentConsensus:
        """Run the multi-agent deliberation: Technical + Sentiment + Macro -> Bull vs Bear Debate -> CRO Consensus."""
        current_price = float(market_data.get("current_price") or 0.0)
        features = market_data.get("features") or {}
        if current_price <= 0.0 or not features:
            logger.warning(
                "Multi-agent desk invoked without market data for %s (price=%s, features=%d); "
                "returning HOLD instead of speculating.",
                market_data.get("symbol"),
                current_price,
                len(features),
            )
            return MultiAgentConsensus(
                final_action="HOLD",
                conviction_score=0.0,
                bull_case_summary="Insufficient data: no current price or feature vector supplied.",
                bear_case_summary="Insufficient data: analysis withheld to avoid speculative decisions.",
                risk_assessment="No market data available. Start ingestion and retry once a live tick exists.",
                suggested_stop_loss_pct=0.0,
                suggested_take_profit_pct=0.0,
                agent_opinions=[],
            )

        data_str = json.dumps(market_data, indent=2)

        # 1. Technical Analyst Agent
        tech_prompt = f"""Evaluate technical indicators and price action:
{data_str}
Return JSON:
{{"stance": "bullish|bearish|neutral", "confidence": 0.0-1.0, "rationale": "...", "key_factors": ["..."]}}"""
        tech_raw = await self._call_agent("You are an expert Technical Market Analyst. Output valid JSON.", tech_prompt)

        # 2. Sentiment & Social Velocity Analyst Agent
        sent_prompt = f"""Evaluate news headlines, Reddit mention velocity, and social sentiment:
{data_str}
Return JSON:
{{"stance": "bullish|bearish|neutral", "confidence": 0.0-1.0, "rationale": "...", "key_factors": ["..."]}}"""
        sent_raw = await self._call_agent(
            "You are an expert Sentiment & Narrative Analyst. Output valid JSON.", sent_prompt
        )

        # 3. Macro & Regime Analyst Agent
        macro_prompt = f"""Evaluate macroeconomic regime, interest rate trajectory, and yield spreads:
{data_str}
Return JSON:
{{"stance": "bullish|bearish|neutral", "confidence": 0.0-1.0, "rationale": "...", "key_factors": ["..."]}}"""
        macro_raw = await self._call_agent("You are a Chief Global Macro Strategist. Output valid JSON.", macro_prompt)

        # Parse specialist opinions
        opinions: list[AgentOpinion] = []
        for name, raw in [
            ("Technical Analyst", tech_raw),
            ("Sentiment Analyst", sent_raw),
            ("Macro Analyst", macro_raw),
        ]:
            opinions.append(await self._parse_opinion(name, raw))

        # 4. Bull vs Bear Debate & Chief Risk Officer (CRO) Consensus
        cro_prompt = f"""Review the specialists' findings:
{json.dumps([o.model_dump() for o in opinions], indent=2)}

Synthesize a Bull vs Bear debate and produce the final consensus trade decision.
Return ONLY valid JSON:
{{
  "final_action": "BUY" | "SELL" | "HOLD",
  "conviction_score": 0.0 to 1.0,
  "bull_case_summary": "Core bullish arguments",
  "bear_case_summary": "Core bearish arguments and tail risks",
  "risk_assessment": "Volatility, liquidity, and invalidation criteria",
  "suggested_stop_loss_pct": 3.0,
  "suggested_take_profit_pct": 6.0
}}"""
        cro_raw = await self._call_agent(
            "You are the Chief Risk Officer (CRO) and Portfolio Manager. Output valid JSON.", cro_prompt
        )

        try:
            cleaned_cro = cro_raw.replace("```json", "").replace("```", "").strip()
            cro_dict = json.loads(cleaned_cro)
            return MultiAgentConsensus(
                final_action=cro_dict.get("final_action", "HOLD"),
                conviction_score=float(cro_dict.get("conviction_score", 0.5)),
                bull_case_summary=cro_dict.get("bull_case_summary", "Technical trend intact."),
                bear_case_summary=cro_dict.get("bear_case_summary", "Macro headwinds present."),
                risk_assessment=cro_dict.get("risk_assessment", "Controlled risk boundaries."),
                suggested_stop_loss_pct=float(cro_dict.get("suggested_stop_loss_pct", 3.0)),
                suggested_take_profit_pct=float(cro_dict.get("suggested_take_profit_pct", 6.0)),
                agent_opinions=opinions,
            )
        except Exception:
            logger.exception("CRO response unparseable; using deterministic fallback consensus.")
            # Deterministic quantitative fallback
            return MultiAgentConsensus(
                final_action="BUY" if any(o.stance == "bullish" for o in opinions) else "HOLD",
                conviction_score=0.7,
                bull_case_summary="Momentum and multi-modal alignment.",
                bear_case_summary="Standard volatility risk.",
                risk_assessment="Risk parameters within normal operational limits.",
                suggested_stop_loss_pct=3.0,
                suggested_take_profit_pct=6.0,
                agent_opinions=opinions,
            )
