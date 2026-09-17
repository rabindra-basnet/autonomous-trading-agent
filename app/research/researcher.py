"""Autonomous AI Research Agent driving the self-improvement loop."""

import logging
from typing import List, Dict, Any, Sequence
from datetime import datetime, timezone
from app.core.models import (
    Candle,
    NewsItem,
    SocialMetric,
    MacroIndicator,
    OnChainMetric,
    ExperimentRecord,
    BacktestResult,
)
from app.storage.registry import StrategyRegistry
from app.strategies.momentum import MomentumTrendStrategy
from app.strategies.sentiment_momentum import SentimentMomentumStrategy
from app.research.optimizer import StrategyOptimizer
from app.research.backtest import BacktestEngine

logger = logging.getLogger("AIResearcher")


class AutonomousResearcher:
    def __init__(self, registry: StrategyRegistry | None = None):
        self.registry = registry or StrategyRegistry()
        self.backtester = BacktestEngine()
        self.optimizer = StrategyOptimizer(self.backtester)

    async def generate_hypotheses(self) -> List[Dict[str, Any]]:
        """AI Hypothesis generator proposing quantitative edge ideas."""
        return [
            {
                "hypothesis": "Fusing Reddit mention velocity with EMA momentum reduces false breakout whipsaws in crypto.",
                "strategy_cls": SentimentMomentumStrategy,
                "param_grid": {
                    "min_sentiment_threshold": [0.10, 0.20, 0.30],
                    "macro_risk_off_filter": [True, False],
                },
            },
            {
                "hypothesis": "Adaptive RSI bounds (30/70 vs 38/62) combined with MACD momentum improve risk-adjusted Sharpe.",
                "strategy_cls": MomentumTrendStrategy,
                "param_grid": {
                    "rsi_oversold": [30.0, 38.0],
                    "rsi_overbought": [62.0, 70.0],
                },
            },
        ]

    async def run_experiment_loop(
        self,
        symbol: str,
        candles: Sequence[Candle],
        news: Sequence[NewsItem] = (),
        social: Sequence[SocialMetric] = (),
        macro: Sequence[MacroIndicator] = (),
        onchain: Sequence[OnChainMetric] = (),
    ) -> List[ExperimentRecord]:
        """Execute autonomous research cycle: hypothesize -> optimize -> walk-forward validate -> promote."""
        logger.info("Starting Autonomous AI Research & Self-Improvement Loop...")
        hypotheses = await self.generate_hypotheses()
        records: List[ExperimentRecord] = []

        for h in hypotheses:
            desc = h["hypothesis"]
            strat_cls = h["strategy_cls"]
            grid = h["param_grid"]

            logger.info(f"Evaluating Hypothesis: {desc}")
            wf_res = self.optimizer.walk_forward_validation(
                strategy_cls=strat_cls,
                symbol=symbol,
                candles=candles,
                param_grid=grid,
                n_splits=3,
            )

            fold_results: List[BacktestResult] = wf_res.get("fold_results", [])
            if not fold_results:
                continue

            best_res = fold_results[-1]
            # Promotion Criteria: Positive Out-of-Sample Sharpe & controlled Max Drawdown
            promoted = (
                wf_res.get("avg_out_of_sample_sharpe", 0) > 1.0
                and best_res.max_drawdown_pct < 20.0
                and best_res.win_rate_pct >= 45.0
            )

            record = self.registry.log_experiment(
                hypothesis=desc,
                strategy_name=strat_cls(symbols=[symbol]).name,
                dataset_range=f"{candles[0].timestamp.date()} to {candles[-1].timestamp.date()}",
                parameters=best_res.parameters,
                backtest_result=best_res,
                promoted=promoted,
                notes=f"Walk-forward avg Sharpe: {wf_res.get('avg_out_of_sample_sharpe')}, Avg Return: {wf_res.get('avg_out_of_sample_return_pct')}%",
            )
            records.append(record)

            if promoted:
                logger.info(f"PROMOTED STRATEGY to Registry: {strat_cls(symbols=[symbol]).name} with params {best_res.parameters}")
            else:
                logger.info(f"Rejected Strategy hypothesis: {desc}")

        return records
