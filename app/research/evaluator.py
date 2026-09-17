"""Quantitative strategy evaluation and risk-adjusted metrics."""

from datetime import datetime
from typing import Any

import numpy as np

from app.core.models import BacktestResult


class StrategyEvaluator:
    @staticmethod
    def calculate_metrics(
        strategy_name: str,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float,
        equity_curve: list[dict[str, Any]],
        trades_log: list[dict[str, Any]],
        parameters: dict[str, Any] | None = None,
    ) -> BacktestResult:
        if not equity_curve:
            return BacktestResult(
                strategy_name=strategy_name,
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                total_return_pct=0.0,
                cagr_pct=0.0,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                max_drawdown_pct=0.0,
                calmar_ratio=0.0,
                win_rate_pct=0.0,
                profit_factor=0.0,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                parameters=parameters or {},
            )

        equities = np.array([e["equity"] for e in equity_curve], dtype=float)
        final_equity = equities[-1]
        total_return_pct = ((final_equity - initial_capital) / initial_capital) * 100.0

        # Returns series
        returns = np.diff(equities) / np.maximum(1e-6, equities[:-1])
        if len(returns) == 0:
            returns = np.array([0.0])

        # Sharpe ratio (annualized, assuming hourly candles: 24 * 365 = 8760 periods)
        periods_per_year = 8760
        mean_ret = np.mean(returns)
        std_ret = np.std(returns)
        sharpe = float((mean_ret / std_ret) * np.sqrt(periods_per_year)) if std_ret > 1e-8 else 0.0

        # Sortino ratio (downside deviation)
        downside_returns = returns[returns < 0]
        downside_std = np.std(downside_returns) if len(downside_returns) > 0 else 1e-8
        sortino = float((mean_ret / downside_std) * np.sqrt(periods_per_year)) if downside_std > 1e-8 else 0.0

        # Max Drawdown
        running_max = np.maximum.accumulate(equities)
        drawdowns = (running_max - equities) / np.maximum(1e-6, running_max)
        max_drawdown_pct = float(np.max(drawdowns)) * 100.0 if len(drawdowns) > 0 else 0.0

        # Calmar Ratio
        calmar = (total_return_pct / max_drawdown_pct) if max_drawdown_pct > 0 else 0.0

        # Trade metrics
        total_trades = len(trades_log)
        pnls = [t.get("pnl", 0.0) for t in trades_log]
        winning_trades = len([p for p in pnls if p > 0])
        losing_trades = len([p for p in pnls if p <= 0])
        win_rate_pct = (winning_trades / total_trades * 100.0) if total_trades > 0 else 0.0

        gross_profits = sum([p for p in pnls if p > 0])
        gross_losses = abs(sum([p for p in pnls if p < 0]))
        profit_factor = (
            (gross_profits / gross_losses) if gross_losses > 0 else (gross_profits if gross_profits > 0 else 1.0)
        )

        # CAGR
        days = max(1, (end_date - start_date).days)
        years = days / 365.25
        cagr_pct = (((final_equity / initial_capital) ** (1.0 / max(0.01, years))) - 1.0) * 100.0

        return BacktestResult(
            strategy_name=strategy_name,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            total_return_pct=round(total_return_pct, 2),
            cagr_pct=round(cagr_pct, 2),
            sharpe_ratio=round(sharpe, 3),
            sortino_ratio=round(sortino, 3),
            max_drawdown_pct=round(max_drawdown_pct, 2),
            calmar_ratio=round(calmar, 3),
            win_rate_pct=round(win_rate_pct, 2),
            profit_factor=round(profit_factor, 2),
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            trades_log=trades_log,
            equity_curve=equity_curve,
            parameters=parameters or {},
        )
