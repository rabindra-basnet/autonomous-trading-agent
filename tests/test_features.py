"""Tests for technical, sentiment, and macro feature pipelines."""

import pytest
import numpy as np
from datetime import datetime, timezone, timedelta
from app.core.models import Candle, NewsItem, SocialMetric
from app.features.technical import TechnicalIndicators
from app.features.sentiment import SentimentFeatures
from app.features.pipeline import FeaturePipeline


def test_technical_indicators():
    prices = np.array([10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 14.0, 13.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0])
    
    # EMA
    ema = TechnicalIndicators.ema(prices, 5)
    assert len(ema) == len(prices)
    assert ema[-1] > 14.0

    # RSI
    rsi = TechnicalIndicators.rsi(prices, 5)
    assert len(rsi) == len(prices)
    assert 0 <= rsi[-1] <= 100


def test_sentiment_features():
    now = datetime.now(timezone.utc)
    news = [
        NewsItem(
            id="1",
            source="test",
            headline="Bitcoin hits new high",
            published_at=now,
            symbols_mentioned=["BTC/USDT"],
            sentiment_score=0.8,
        )
    ]
    social = [
        SocialMetric(
            platform="reddit",
            symbol="BTC/USDT",
            timestamp=now,
            mention_count=500,
            mention_velocity_pct=50.0,
            average_sentiment=0.6,
        )
    ]

    res = SentimentFeatures.compute_sentiment_features("BTC/USDT", news, social)
    assert res["news_sentiment"] == 0.8
    assert res["social_sentiment"] == 0.6
    assert res["composite_sentiment"] == 0.7
    assert res["social_velocity_pct"] == 50.0


def test_feature_pipeline():
    pipeline = FeaturePipeline()
    now = datetime.now(timezone.utc)
    candles = [
        Candle(
            symbol="BTC/USDT",
            timestamp=now - timedelta(hours=i),
            open=50000.0 + i * 10,
            high=50100.0 + i * 10,
            low=49900.0 + i * 10,
            close=50050.0 + i * 10,
            volume=100.0,
        )
        for i in range(50, 0, -1)
    ]

    feat_vec = pipeline.compute_features(
        symbol="BTC/USDT",
        candles=candles,
    )

    assert feat_vec.symbol == "BTC/USDT"
    assert "close" in feat_vec.features
    assert "rsi_14" in feat_vec.features
    assert "ema_12" in feat_vec.features
