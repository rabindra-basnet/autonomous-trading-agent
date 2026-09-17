"""Multi-modal Sentiment Momentum Strategy fusing price, sentiment, and macro regime."""

from typing import List, Dict, Any
from app.strategies.base import BaseStrategy
from app.core.models import (
    FeatureVector,
    PortfolioState,
    TradingSignal,
    SignalType,
)


class SentimentMomentumStrategy(BaseStrategy):
    def __init__(
        self,
        symbols: List[str],
        parameters: Dict[str, Any] | None = None,
    ):
        super().__init__(name="sentiment_momentum", symbols=symbols, parameters=parameters)
        self.min_sentiment = float(self.parameters.get("min_sentiment_threshold", 0.15))
        self.macro_filter = bool(self.parameters.get("macro_risk_off_filter", True))

    def generate_signals(
        self,
        feature_vector: FeatureVector,
        portfolio: PortfolioState,
    ) -> List[TradingSignal]:
        signals: List[TradingSignal] = []
        sym = feature_vector.symbol
        if sym not in self.symbols:
            return signals

        feats = feature_vector.features
        close = feats.get("close", 0.0)
        ema_12 = feats.get("ema_12", 0.0)
        ema_26 = feats.get("ema_26", 0.0)
        composite_sentiment = feats.get("composite_sentiment", 0.0)
        social_velocity = feats.get("social_velocity_pct", 0.0)
        macro_risk_on = feats.get("macro_risk_on", 1.0)

        # Macro gate check: If macro is risk-off and filter is active, avoid opening new longs
        if self.macro_filter and macro_risk_on < 0.5:
            return signals

        current_position = portfolio.positions.get(sym)

        # Multi-modal Long Trigger:
        # Technical momentum positive + Sentiment bullish + Social buzz accelerating
        if (
            ema_12 > ema_26
            and composite_sentiment >= self.min_sentiment
            and social_velocity >= 0.0
        ):
            if not current_position:
                # Signal strength is scaled by sentiment magnitude and velocity
                strength = min(1.0, max(0.3, composite_sentiment + (social_velocity / 200.0)))
                signals.append(
                    TradingSignal(
                        symbol=sym,
                        timestamp=feature_vector.timestamp,
                        strategy_name=self.name,
                        signal_type=SignalType.LONG,
                        strength=strength,
                        suggested_size_pct=0.20,
                        stop_loss=close * 0.95,
                        target_price=close * 1.10,
                        metadata={
                            "sentiment": composite_sentiment,
                            "social_velocity": social_velocity,
                            "macro_risk_on": macro_risk_on,
                        },
                    )
                )

        # Exit if sentiment drops severely or technicals break
        elif (composite_sentiment < -0.20 or ema_12 < ema_26) and current_position:
            signals.append(
                TradingSignal(
                    symbol=sym,
                    timestamp=feature_vector.timestamp,
                    strategy_name=self.name,
                    signal_type=SignalType.FLAT,
                    strength=1.0,
                    metadata={"reason": "sentiment_or_trend_decay"},
                )
            )

        return signals
