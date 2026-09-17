"""High-fidelity Event-Driven Point-in-Time Backtesting Engine."""

from collections.abc import Sequence
from typing import Any

from app.core.models import (
    BacktestResult,
    Candle,
    MacroIndicator,
    NewsItem,
    OnChainMetric,
    OrderSide,
    PortfolioState,
    Position,
    SignalType,
    SocialMetric,
)
from app.core.protocols import StrategyProtocol
from app.execution.risk_manager import RiskManager
from app.features.pipeline import FeaturePipeline
from app.research.evaluator import StrategyEvaluator


class BacktestEngine:
    def __init__(
        self,
        initial_capital: float = 100000.0,
        commission_rate: float = 0.001,
        slippage_rate: float = 0.0005,
    ):
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage_rate = slippage_rate
        self.feature_pipeline = FeaturePipeline()
        self.risk_manager = RiskManager()

    def run(
        self,
        strategy: StrategyProtocol,
        symbol: str,
        candles: Sequence[Candle],
        news: Sequence[NewsItem] = (),
        social: Sequence[SocialMetric] = (),
        macro: Sequence[MacroIndicator] = (),
        onchain: Sequence[OnChainMetric] = (),
    ) -> BacktestResult:
        if not candles:
            raise ValueError("Candles dataset cannot be empty for backtest.")

        candles_list = sorted(candles, key=lambda c: c.timestamp)
        start_date = candles_list[0].timestamp
        end_date = candles_list[-1].timestamp

        cash = self.initial_capital
        peak_equity = self.initial_capital
        positions: dict[str, Position] = {}
        trades_log: list[dict[str, Any]] = []
        equity_curve: list[dict[str, Any]] = []

        # Warm-up period for indicators
        warmup = 30
        for i in range(warmup, len(candles_list)):
            current_candle = candles_list[i]
            history_slice = candles_list[: i + 1]
            ts = current_candle.timestamp
            price = current_candle.close

            # Update position prices & bracket stop loss / take profits
            if symbol in positions:
                pos = positions[symbol]
                pos.current_price = price
                pos.last_updated = ts
                pos.unrealized_pnl = (price - pos.entry_price) * pos.size

                # Check Stop Loss / Take Profit triggers
                hit_stop = pos.stop_loss and price <= pos.stop_loss
                hit_target = pos.take_profit and price >= pos.take_profit

                if hit_stop or hit_target:
                    raw_exit = pos.stop_loss if hit_stop else pos.take_profit
                    assert raw_exit is not None
                    exit_price = raw_exit * (1.0 - self.slippage_rate)
                    trade_val = exit_price * pos.size
                    comm = trade_val * self.commission_rate
                    pnl = (exit_price - pos.entry_price) * pos.size - comm
                    cash += trade_val - comm

                    trades_log.append(
                        {
                            "timestamp": ts.isoformat(),
                            "symbol": symbol,
                            "side": "sell",
                            "size": pos.size,
                            "entry_price": pos.entry_price,
                            "exit_price": exit_price,
                            "pnl": pnl,
                            "reason": "stop_loss" if hit_stop else "take_profit",
                        }
                    )
                    del positions[symbol]

            # Current Equity
            pos_val = sum(p.size * p.current_price for p in positions.values())
            total_equity = cash + pos_val
            peak_equity = max(peak_equity, total_equity)
            drawdown = (peak_equity - total_equity) / peak_equity if peak_equity > 0 else 0.0

            portfolio_state = PortfolioState(
                timestamp=ts,
                cash_balance=cash,
                total_equity=total_equity,
                unrealized_pnl=sum(p.unrealized_pnl for p in positions.values()),
                realized_pnl=sum(t.get("pnl", 0) for t in trades_log),
                peak_equity=peak_equity,
                drawdown_pct=drawdown,
                positions={k: v.model_copy() for k, v in positions.items()},
            )

            equity_curve.append(
                {
                    "timestamp": ts.isoformat(),
                    "equity": total_equity,
                    "cash": cash,
                    "drawdown_pct": drawdown,
                }
            )

            # 1. Point-in-time feature vector computation
            # Filter news/social/macro available strictly up to current timestamp
            avail_news = [n for n in news if n.published_at <= ts]
            avail_social = [s for s in social if s.timestamp <= ts]
            avail_macro = [m for m in macro if m.timestamp <= ts]
            avail_onchain = [o for o in onchain if o.timestamp <= ts]

            feat_vec = self.feature_pipeline.compute_features(
                symbol=symbol,
                candles=history_slice,
                news=avail_news,
                social=avail_social,
                macro=avail_macro,
                onchain=avail_onchain,
            )

            # 2. Strategy Signal Generation
            signals = strategy.generate_signals(feat_vec, portfolio_state)

            # 3. Risk & Execution
            for sig in signals:
                risk_res = self.risk_manager.validate_signal(sig, portfolio_state, price)
                if not risk_res.approved:
                    continue

                if sig.signal_type == SignalType.LONG:
                    fill_price = price * (1.0 + self.slippage_rate)
                    cost = fill_price * risk_res.adjusted_size
                    comm = cost * self.commission_rate
                    if cash >= (cost + comm):
                        cash -= cost + comm
                        positions[symbol] = Position(
                            symbol=symbol,
                            side=OrderSide.BUY,
                            size=risk_res.adjusted_size,
                            entry_price=fill_price,
                            current_price=fill_price,
                            stop_loss=risk_res.adjusted_stop_loss,
                            take_profit=risk_res.adjusted_take_profit,
                            opened_at=ts,
                            last_updated=ts,
                        )

                elif sig.signal_type == SignalType.FLAT and symbol in positions:
                    pos = positions[symbol]
                    exit_price = price * (1.0 - self.slippage_rate)
                    trade_val = exit_price * pos.size
                    comm = trade_val * self.commission_rate
                    pnl = (exit_price - pos.entry_price) * pos.size - comm
                    cash += trade_val - comm

                    trades_log.append(
                        {
                            "timestamp": ts.isoformat(),
                            "symbol": symbol,
                            "side": "sell",
                            "size": pos.size,
                            "entry_price": pos.entry_price,
                            "exit_price": exit_price,
                            "pnl": pnl,
                            "reason": sig.metadata.get("reason", "signal_flat"),
                        }
                    )
                    del positions[symbol]

        return StrategyEvaluator.calculate_metrics(
            strategy_name=strategy.name,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.initial_capital,
            equity_curve=equity_curve,
            trades_log=trades_log,
            parameters=getattr(strategy, "parameters", {}),
        )
