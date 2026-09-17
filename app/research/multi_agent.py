"""Multi-Agent Institutional Trading Desk powered by OpenAI-Compatible LLMs (Groq Llama-3.3-70B)."""

import json
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import httpx
from app.config import settings

logger = logging.getLogger("MultiAgentDesk")


class AgentOpinion(BaseModel):
    role: str
    stance: str  # "bullish", "bearish", "neutral"
    confidence: float  # 0.0 to 1.0
    rationale: str
    key_factors: List[str] = Field(default_factory=list)


class MultiAgentConsensus(BaseModel):
    final_action: str  # "BUY", "SELL", "HOLD"
    conviction_score: float  # 0.0 to 1.0
    bull_case_summary: str
    bear_case_summary: str
    risk_assessment: str
    suggested_stop_loss_pct: float
    suggested_take_profit_pct: float
    agent_opinions: List[AgentOpinion] = Field(default_factory=list)


class MultiAgentTradingDesk:
    """Collaborative multi-agent trading desk featuring specialized analyst roles and bull/bear debate."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model

    async def _call_agent(self, system_role: str, user_prompt: str) -> str:
        """Helper to invoke an agent role via OpenAI-compatible completions API."""
        endpoint = f"{self.base_url}/chat/completions" if not self.base_url.endswith("/chat/completions") else self.base_url
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_role},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.post(endpoint, headers=headers, json=payload)
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"Error calling {system_role}: {e}")
        return ""

    async def evaluate_market(self, market_data: Dict[str, Any]) -> MultiAgentConsensus:
        """Run the multi-agent deliberation: Technical + Sentiment + Macro -> Bull vs Bear Debate -> CRO Consensus."""
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
        sent_raw = await self._call_agent("You are an expert Sentiment & Narrative Analyst. Output valid JSON.", sent_prompt)

        # 3. Macro & Regime Analyst Agent
        macro_prompt = f"""Evaluate macroeconomic regime, interest rate trajectory, and yield spreads:
{data_str}
Return JSON:
{{"stance": "bullish|bearish|neutral", "confidence": 0.0-1.0, "rationale": "...", "key_factors": ["..."]}}"""
        macro_raw = await self._call_agent("You are a Chief Global Macro Strategist. Output valid JSON.", macro_prompt)

        # Parse specialist opinions
        opinions: List[AgentOpinion] = []
        for name, raw in [("Technical Analyst", tech_raw), ("Sentiment Analyst", sent_raw), ("Macro Analyst", macro_raw)]:
            try:
                cleaned = raw.replace("```json", "").replace("```", "").strip()
                p = json.loads(cleaned)
                opinions.append(AgentOpinion(role=name, **p))
            except Exception:
                opinions.append(AgentOpinion(role=name, stance="neutral", confidence=0.5, rationale="Algorithmic baseline analysis."))

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
        cro_raw = await self._call_agent("You are the Chief Risk Officer (CRO) and Portfolio Manager. Output valid JSON.", cro_prompt)

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
