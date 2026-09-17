"""Universal OpenAI-Compatible LLM Client supporting Groq, OpenRouter, Ollama, Gemini, DeepSeek, vLLM."""

import json
import logging
from typing import Any

from app.config import settings
from app.core.llm import chat_completion

logger = logging.getLogger("OpenAICompatibleLLMClient")


class OpenAICompatibleLLMClient:
    """Universal client for OpenAI-compatible LLM endpoints."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model

    async def generate_hypotheses(self, market_context: dict[str, Any]) -> list[dict[str, Any]]:
        """Query any OpenAI-compatible endpoint (/chat/completions) to generate quantitative trading hypotheses."""
        prompt = f"""You are an elite quantitative researcher designing self-improving trading strategies.
Market Context:
{json.dumps(market_context, indent=2)}

Task:
Formulate 2 distinct quantitative trading hypotheses with parameter search grids.
Return ONLY valid JSON array with this exact structure:
[
  {{
    "hypothesis": "Hypothesis description explaining the economic rationale and edge",
    "strategy_name": "sentiment_momentum",
    "param_grid": {{
      "min_sentiment_threshold": [0.10, 0.20, 0.30],
      "macro_risk_off_filter": [true, false]
    }}
  }},
  {{
    "hypothesis": "Hypothesis description for technical trend with adaptive thresholds",
    "strategy_name": "momentum_trend",
    "param_grid": {{
      "rsi_oversold": [30.0, 38.0],
      "rsi_overbought": [62.0, 70.0]
    }}
  }}
]
"""
        result = await chat_completion(
            "You are a quantitative finance AI. Respond only with JSON.", prompt, model=self.model
        )
        content = result.content

        try:
            cleaned_json = content.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(cleaned_json)
            if isinstance(parsed, list):
                return parsed
            elif isinstance(parsed, dict) and "hypotheses" in parsed:
                return parsed["hypotheses"]
            return [parsed]
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"LLM returned unparseable hypotheses ({e}). Using fallback.")

        # Deterministic fallback if API call fails or no API key is provided
        return [
            {
                "hypothesis": "Fusing social mention velocity with EMA trend reduces false breakout drawdowns in crypto.",
                "strategy_name": "sentiment_momentum",
                "param_grid": {
                    "min_sentiment_threshold": [0.10, 0.20, 0.30],
                    "macro_risk_off_filter": [True, False],
                },
            },
            {
                "hypothesis": "Adaptive RSI bounds (30/70 vs 38/62) combined with MACD momentum improve risk-adjusted Sharpe.",
                "strategy_name": "momentum_trend",
                "param_grid": {
                    "rsi_oversold": [30.0, 38.0],
                    "rsi_overbought": [62.0, 70.0],
                },
            },
        ]