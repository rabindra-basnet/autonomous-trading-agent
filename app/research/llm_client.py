"""Free LLM Client supporting Google Gemini, Groq (Llama 3.3), and Local Ollama."""

import os
import json
import logging
from typing import Dict, Any, List, Optional
import httpx

logger = logging.getLogger("FreeLLMClient")


class FreeLLMClient:
    """Client for generating trading hypotheses and reasoning using free LLM tiers."""

    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        groq_api_key: Optional[str] = None,
        ollama_base_url: str = "http://localhost:11434",
    ):
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY", "")
        self.groq_api_key = groq_api_key or os.getenv("GROQ_API_KEY", "")
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", ollama_base_url)

    async def generate_hypotheses(self, market_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Query free LLM (Gemini -> Groq -> Ollama -> Algorithmic fallback) to synthesize strategy hypotheses."""
        prompt = f"""You are an elite quantitative researcher designing self-improving trading strategies.
Market Context:
{json.dumps(market_context, indent=2)}

Task:
Formulate 2 distinct quantitative trading hypotheses with parameter search grids.
Return ONLY valid JSON in this exact structure:
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
        # 1. Try Google Gemini Free Tier
        if self.gemini_api_key:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.gemini_api_key}"
                payload = {"contents": [{"parts": [{"text": prompt}]}]}
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        raw_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                        cleaned_json = raw_text.replace("```json", "").replace("```", "").strip()
                        return json.loads(cleaned_json)
            except Exception as e:
                logger.warning(f"Gemini API call failed, trying next provider: {e}")

        # 2. Try Groq Free Tier (Llama-3.3-70B)
        if self.groq_api_key:
            try:
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {"Authorization": f"Bearer {self.groq_api_key}"}
                payload = {
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                }
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    if resp.status_code == 200:
                        res = resp.json()["choices"][0]["message"]["content"]
                        parsed = json.loads(res)
                        return parsed if isinstance(parsed, list) else parsed.get("hypotheses", [parsed])
            except Exception as e:
                logger.warning(f"Groq API call failed: {e}")

        # 3. Try Local Ollama (100% Free, offline)
        try:
            url = f"{self.ollama_base_url}/api/generate"
            payload = {"model": "llama3.2", "prompt": prompt, "stream": False, "format": "json"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    res_text = resp.json().get("response", "")
                    return json.loads(res_text)
        except Exception:
            pass

        # 4. Deterministic algorithmic fallback
        return [
            {
                "hypothesis": "Fusing social mention velocity with EMA trend reduces false breakout drawdowns.",
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
