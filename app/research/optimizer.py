"""Strategy parameter optimization and Walk-Forward cross validation."""

import itertools
from collections.abc import Sequence
from typing import Any

from app.core.models import BacktestResult, Candle
from app.research.backtest import BacktestEngine
from app.strategies.base import BaseStrategy


class StrategyOptimizer:
    def __init__(self, backtest_engine: BacktestEngine | None = None):
        self.backtester = backtest_engine or BacktestEngine()

    def grid_search(
        self,
        strategy_cls: type[BaseStrategy],
        symbol: str,
        candles: Sequence[Candle],
        param_grid: dict[str, list[Any]],
    ) -> list[BacktestResult]:
        keys = list(param_grid.keys())
        combos = list(itertools.product(*param_grid.values()))
        results: list[BacktestResult] = []

        for combo in combos:
            params = dict(zip(keys, combo))
            strat_instance = strategy_cls(symbols=[symbol], parameters=params)
            res = self.backtester.run(strat_instance, symbol, candles)
            results.append(res)

        # Sort by Sharpe Ratio descending
        results.sort(key=lambda r: r.sharpe_ratio, reverse=True)
        return results

    def walk_forward_validation(
        self,
        strategy_cls: type[BaseStrategy],
        symbol: str,
        candles: Sequence[Candle],
        param_grid: dict[str, list[Any]],
        n_splits: int = 3,
        train_ratio: float = 0.7,
    ) -> dict[str, Any]:
        """Perform out-of-sample Walk-Forward Cross Validation."""
        total_len = len(candles)
        fold_size = total_len // n_splits
        oof_results: list[BacktestResult] = []

        for fold in range(n_splits):
            fold_candles = candles[fold * fold_size : (fold + 1) * fold_size]
            if len(fold_candles) < 50:
                continue

            split_idx = int(len(fold_candles) * train_ratio)
            train_data = fold_candles[:split_idx]
            test_data = fold_candles[split_idx:]

            # 1. Optimize on in-sample (train)
            train_results = self.grid_search(strategy_cls, symbol, train_data, param_grid)
            best_params = train_results[0].parameters if train_results else {}

            # 2. Test best params on out-of-sample (test)
            test_strat = strategy_cls(symbols=[symbol], parameters=best_params)
            test_res = self.backtester.run(test_strat, symbol, test_data)
            oof_results.append(test_res)

        avg_sharpe = sum(r.sharpe_ratio for r in oof_results) / len(oof_results) if oof_results else 0.0
        avg_return = sum(r.total_return_pct for r in oof_results) / len(oof_results) if oof_results else 0.0

        return {
            "folds": len(oof_results),
            "avg_out_of_sample_sharpe": round(avg_sharpe, 3),
            "avg_out_of_sample_return_pct": round(avg_return, 2),
            "fold_results": oof_results,
        }
