"""Autonomous AI Research Agent driving the self-improvement loop."""

import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from app.core.models import (
    BacktestResult,
    Candle,
    ExperimentRecord,
    MacroIndicator,
    NewsItem,
    OnChainMetric,
    SocialMetric,
)
from app.research.backtest import BacktestEngine
from app.research.llm_client import OpenAICompatibleLLMClient
from app.research.optimizer import StrategyOptimizer
from app.strategies.momentum import MomentumTrendStrategy
from app.strategies.sentiment_momentum import SentimentMomentumStrategy

logger = logging.getLogger("AIResearcher")


class AutonomousResearcher:
    def __init__(self):
        self.backtester = BacktestEngine()
        self.optimizer = StrategyOptimizer(self.backtester)
        self.llm_client = OpenAICompatibleLLMClient()

    async def generate_hypotheses(self, market_context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """AI Hypothesis generator proposing quantitative edge ideas via Free LLMs (Gemini/Groq/Ollama)."""
        ctx = market_context or {
            "current_regime": "crypto_volatility_expansion",
            "active_assets": ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
            "macro_condition": "FED_rate_steady",
        }
        raw_hypotheses = await self.llm_client.generate_hypotheses(ctx)

        # Map strategy names to classes
        strat_map = {
            "sentiment_momentum": SentimentMomentumStrategy,
            "momentum_trend": MomentumTrendStrategy,
        }

        formatted = []
        for h in raw_hypotheses:
            s_name = h.get("strategy_name", "sentiment_momentum")
            s_cls = strat_map.get(s_name, SentimentMomentumStrategy)
            formatted.append(
                {
                    "hypothesis": h.get("hypothesis", ""),
                    "strategy_cls": s_cls,
                    "param_grid": h.get("param_grid", {}),
                }
            )

        return formatted

    async def run_experiment_loop(
        self,
        symbol: str,
        candles: Sequence[Candle],
        news: Sequence[NewsItem] = (),
        social: Sequence[SocialMetric] = (),
        macro: Sequence[MacroIndicator] = (),
        onchain: Sequence[OnChainMetric] = (),
    ) -> list[ExperimentRecord]:
        """Execute autonomous research cycle: hypothesize (LLM) -> optimize -> walk-forward validate -> promote."""
        logger.info("Starting Autonomous AI Research & Self-Improvement Loop with Free LLM Reasoning...")

        market_context = {
            "symbol": symbol,
            "candle_count": len(candles),
            "start_price": candles[0].close if candles else 0,
            "end_price": candles[-1].close if candles else 0,
            "news_count": len(news),
            "social_count": len(social),
        }

        hypotheses = await self.generate_hypotheses(market_context)
        records: list[ExperimentRecord] = []

        for h in hypotheses:
            desc = h["hypothesis"]
            strat_cls = h["strategy_cls"]
            grid = h["param_grid"]

            logger.info(f"Evaluating LLM Hypothesis: {desc}")
            wf_res = self.optimizer.walk_forward_validation(
                strategy_cls=strat_cls,
                symbol=symbol,
                candles=candles,
                param_grid=grid,
                n_splits=3,
            )

            fold_results: list[BacktestResult] = wf_res.get("fold_results", [])
            if not fold_results:
                continue

            best_res = fold_results[-1]
            # Promotion Criteria: Positive Out-of-Sample Sharpe & controlled Max Drawdown
            promoted = (
                wf_res.get("avg_out_of_sample_sharpe", 0) > 1.0
                and best_res.max_drawdown_pct < 20.0
                and best_res.win_rate_pct >= 45.0
            )

            record = ExperimentRecord(
                experiment_id=f"exp_{int(datetime.now(UTC).timestamp() * 1000)}_{uuid.uuid4().hex[:6]}",
                created_at=datetime.now(UTC),
                hypothesis=desc,
                strategy_name=strat_cls(symbols=[symbol]).name,
                dataset_range=f"{candles[0].timestamp.date()} to {candles[-1].timestamp.date()}",
                parameters=best_res.parameters,
                metrics={
                    "sharpe_ratio": round(best_res.sharpe_ratio, 3),
                    "total_return_pct": round(best_res.total_return_pct, 2),
                    "max_drawdown_pct": round(best_res.max_drawdown_pct, 2),
                    "win_rate_pct": round(best_res.win_rate_pct, 2),
                    "profit_factor": round(best_res.profit_factor, 2),
                },
                promoted=promoted,
                notes=f"Walk-forward avg Sharpe: {wf_res.get('avg_out_of_sample_sharpe')}, Avg Return: {wf_res.get('avg_out_of_sample_return_pct')}%",
            )
            records.append(record)

            if promoted:
                logger.info(f"PROMOTED STRATEGY: {strat_cls(symbols=[symbol]).name} with params {best_res.parameters}")
            else:
                logger.info(f"Rejected Strategy hypothesis: {desc}")

        return records
