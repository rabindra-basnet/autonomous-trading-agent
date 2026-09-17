"""Tests for data normalization, cleaning, and quality assurance."""

from datetime import UTC, datetime

from app.core.models import AssetClass, Candle
from app.normalization.cleaner import DataQualityAssurance
from app.normalization.normalizer import DataNormalizer


def test_data_normalizer_ccxt_ohlcv():
    raw_ohlcv = [1700000000000, 60000.0, 61000.0, 59000.0, 60500.0, 1500.0]
    candle = DataNormalizer.from_ccxt_ohlcv(raw_ohlcv, "BTC/USDT", "binance")

    assert candle.symbol == "BTC/USDT"
    assert candle.open == 60000.0
    assert candle.high == 61000.0
    assert candle.low == 59000.0
    assert candle.close == 60500.0
    assert candle.volume == 1500.0
    assert candle.exchange == "binance"
    assert candle.asset_class == AssetClass.CRYPTO


def test_data_cleaner_validation():
    cleaner = DataQualityAssurance(max_price_jump_pct=0.5)

    now = datetime.now(UTC)
    valid_candle = Candle(
        symbol="BTC/USDT",
        timestamp=now,
        open=100.0,
        high=105.0,
        low=95.0,
        close=102.0,
        volume=50.0,
    )
    assert cleaner.validate_candle(valid_candle) is True

    # Invalid candle: High < Low
    invalid_high_low = Candle(
        symbol="BTC/USDT",
        timestamp=now,
        open=100.0,
        high=90.0,
        low=95.0,
        close=92.0,
        volume=50.0,
    )
    assert cleaner.validate_candle(invalid_high_low) is False

    # Outlier spike check
    spike_candle = Candle(
        symbol="BTC/USDT",
        timestamp=now,
        open=100.0,
        high=250.0,
        low=100.0,
        close=220.0,
        volume=50.0,
    )
    assert cleaner.validate_candle(spike_candle, previous_candle=valid_candle) is False
