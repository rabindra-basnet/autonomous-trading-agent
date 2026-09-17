"""Universal OpenAI-Compatible LLM Client supporting Groq, OpenRouter, Ollama, Gemini, DeepSeek, vLLM."""

import os
import json
import logging
from typing import Dict, Any, List, Optional
import httpx
from app.config import settings

logger = logging.getLogger("OpenAICompatibleLLMClient")


class OpenAICompatibleLLMClient:
    """Universal client for OpenAI-compatible LLM endpoints."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model

    async def generate_hypotheses(self, market_context: Dict[str, Any]) -> List[Dict[str, Any]]:
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
        # Ensure endpoint url is correct
        endpoint = f"{self.base_url}/chat/completions" if not self.base_url.endswith("/chat/completions") else self.base_url

        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a quantitative finance AI. Respond only with JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(endpoint, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    cleaned_json = content.replace("```json", "").replace("```", "").strip()
                    parsed = json.loads(cleaned_json)
                    if isinstance(parsed, list):
                        return parsed
                    elif isinstance(parsed, dict) and "hypotheses" in parsed:
                        return parsed["hypotheses"]
                    return [parsed]
                else:
                    logger.warning(
                        f"OpenAI-compatible API request failed ({resp.status_code}): {resp.text}. Using fallback."
                    )
        except Exception as e:
            logger.warning(f"Error communicating with LLM API at {endpoint}: {e}. Using deterministic fallback.")

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
