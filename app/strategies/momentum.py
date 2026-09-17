"""Technical Momentum and Trend Strategy."""

from typing import Any

from app.core.models import (
    FeatureVector,
    PortfolioState,
    SignalType,
    TradingSignal,
)
from app.strategies.base import BaseStrategy


class MomentumTrendStrategy(BaseStrategy):
    def __init__(
        self,
        symbols: list[str],
        parameters: dict[str, Any] | None = None,
    ):
        super().__init__(name="momentum_trend", symbols=symbols, parameters=parameters)
        self.rsi_oversold = float(self.parameters.get("rsi_oversold", 35.0))
        self.rsi_overbought = float(self.parameters.get("rsi_overbought", 65.0))

    def generate_signals(
        self,
        feature_vector: FeatureVector,
        portfolio: PortfolioState,
    ) -> list[TradingSignal]:
        signals: list[TradingSignal] = []
        sym = feature_vector.symbol
        if sym not in self.symbols:
            return signals

        feats = feature_vector.features
        close = feats.get("close", 0.0)
        ema_12 = feats.get("ema_12", 0.0)
        ema_26 = feats.get("ema_26", 0.0)
        rsi = feats.get("rsi_14", 50.0)
        macd_hist = feats.get("macd_hist", 0.0)

        current_position = portfolio.positions.get(sym)

        # Bullish condition: Fast EMA > Slow EMA, RSI not overbought, positive MACD momentum
        if ema_12 > ema_26 and rsi < self.rsi_overbought and macd_hist > 0:
            if not current_position:
                strength = min(1.0, max(0.2, (ema_12 - ema_26) / close * 100))
                signals.append(
                    TradingSignal(
                        symbol=sym,
                        timestamp=feature_vector.timestamp,
                        strategy_name=self.name,
                        signal_type=SignalType.LONG,
                        strength=strength,
                        suggested_size_pct=0.15,
                        stop_loss=close * 0.96,
                        target_price=close * 1.08,
                        metadata={"ema_12": ema_12, "ema_26": ema_26, "rsi": rsi},
                    )
                )

        # Bearish / Exit condition: Fast EMA < Slow EMA or RSI overbought
        elif (ema_12 < ema_26 or rsi > self.rsi_overbought) and current_position:
            signals.append(
                TradingSignal(
                    symbol=sym,
                    timestamp=feature_vector.timestamp,
                    strategy_name=self.name,
                    signal_type=SignalType.FLAT,
                    strength=1.0,
                    metadata={"reason": "trend_reversal_or_overbought"},
                )
            )

        return signals
