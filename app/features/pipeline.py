"""Unified feature pipeline aggregating multimodal market, information, and alt data."""

from datetime import datetime, timezone
from typing import List, Sequence, Dict
from app.core.models import (
    Candle,
    NewsItem,
    SocialMetric,
    MacroIndicator,
    OnChainMetric,
    FeatureVector,
)
from app.features.technical import TechnicalIndicators
from app.features.sentiment import SentimentFeatures
from app.features.macro_regime import MacroOnChainFeatures


class FeaturePipeline:
    def __init__(self, lookback_candles: int = 100):
        self.lookback_candles = lookback_candles

    def compute_features(
        self,
        symbol: str,
        candles: Sequence[Candle],
        news: Sequence[NewsItem] = (),
        social: Sequence[SocialMetric] = (),
        macro: Sequence[MacroIndicator] = (),
        onchain: Sequence[OnChainMetric] = (),
    ) -> FeatureVector:
        now = candles[-1].timestamp if candles else datetime.now(timezone.utc)
        features: Dict[str, float] = {}

        # 1. Technical Features
        recent_candles = list(candles[-self.lookback_candles:]) if candles else []
        tech_feats = TechnicalIndicators.extract_features(recent_candles)
        features.update(tech_feats)

        # 2. Sentiment Features
        sent_feats = SentimentFeatures.compute_sentiment_features(symbol, news, social)
        features.update(sent_feats)

        # 3. Macro Regime Features
        macro_feats = MacroOnChainFeatures.compute_macro_features(macro)
        features.update(macro_feats)

        # 4. On-chain Features
        onchain_feats = MacroOnChainFeatures.compute_onchain_features(symbol, onchain)
        features.update(onchain_feats)

        return FeatureVector(
            symbol=symbol,
            timestamp=now,
            features=features,
        )
