"""Visual and structured Graph/Chart generation engine for quantitative analytics."""

import io
import base64
from typing import List, Dict, Any, Sequence, Optional
from datetime import datetime
import numpy as np

from app.core.models import Candle, BacktestResult


class ChartGenerator:
    """Generates visual and structured graphs for equity curves, technical indicators, and multi-modal signals."""

    @staticmethod
    def generate_equity_curve_data(equity_curve: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Format equity curve points for TradingView / Chart.js / Frontend graphs."""
        labels = [e["timestamp"] for e in equity_curve]
        equities = [e["equity"] for e in equity_curve]
        drawdowns = [e.get("drawdown_pct", 0.0) * 100.0 for e in equity_curve]

        return {
            "timestamps": labels,
            "equity": equities,
            "drawdown_pct": drawdowns,
            "peak_equity": max(equities) if equities else 0.0,
            "final_equity": equities[-1] if equities else 0.0,
        }

    @staticmethod
    def generate_candle_chart_data(candles: Sequence[Candle]) -> List[Dict[str, Any]]:
        """Format OHLCV candles with indicator overlays for charting libraries."""
        data = []
        for c in candles:
            data.append({
                "time": int(c.timestamp.timestamp()),
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            })
        return data

    @staticmethod
    def render_equity_chart_image(backtest_result: BacktestResult) -> str:
        """Render a base64 encoded PNG chart of the strategy equity curve and drawdown."""
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            equity_data = backtest_result.equity_curve
            if not equity_data:
                return ""

            times = [datetime.fromisoformat(e["timestamp"]) for e in equity_data]
            equities = [e["equity"] for e in equity_data]
            drawdowns = [e.get("drawdown_pct", 0.0) * -100.0 for e in equity_data]

            fig, (ax1, ax2) = plt.subplots(
                2, 1, figsize=(10, 6), sharex=True, gridspec_kw={"height_ratios": [3, 1]}
            )

            # Equity Curve
            ax1.plot(times, equities, label="Portfolio Equity ($)", color="#00ff88", linewidth=1.5)
            ax1.set_title(f"Strategy Equity Curve - {backtest_result.strategy_name} ({backtest_result.symbol})", fontsize=12, fontweight="bold")
            ax1.set_ylabel("Equity ($)")
            ax1.grid(True, linestyle="--", alpha=0.3)
            ax1.legend(loc="upper left")

            # Drawdown Area
            ax2.fill_between(times, drawdowns, 0, color="#ff4444", alpha=0.4, label="Drawdown %")
            ax2.set_ylabel("Drawdown %")
            ax2.set_xlabel("Date")
            ax2.grid(True, linestyle="--", alpha=0.3)
            ax2.legend(loc="lower left")

            plt.tight_layout()
            buf = io.BytesIO()
            plt.savefig(buf, format="png", dpi=120)
            plt.close(fig)
            buf.seek(0)
            return base64.b64encode(buf.read()).decode("utf-8")
        except Exception:
            return ""
