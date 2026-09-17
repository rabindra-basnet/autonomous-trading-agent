"""Raw payload to canonical model normalizer."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.core.models import (
    Candle,
    TradeEvent,
    OrderSide,
    NewsItem,
    SocialMetric,
    MacroIndicator,
    OnChainMetric,
    AssetClass,
)


class DataNormalizer:
    @staticmethod
    def parse_timestamp(val: Any) -> datetime:
        """Parse int timestamp (ms/sec), ISO string, or datetime to UTC datetime."""
        if isinstance(val, datetime):
            return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
        if isinstance(val, (int, float)):
            # If timestamp in milliseconds (> 1e11)
            if val > 1e11:
                return datetime.fromtimestamp(val / 1000.0, tz=timezone.utc)
            return datetime.fromtimestamp(val, tz=timezone.utc)
        if isinstance(val, str):
            try:
                # Handle ISO formats
                return datetime.fromisoformat(val.replace("Z", "+00:00"))
            except Exception:
                return datetime.now(timezone.utc)
        return datetime.now(timezone.utc)

    @classmethod
    def from_ccxt_ohlcv(
        cls, raw_ohlcv: List[Any], symbol: str, exchange: str = "binance"
    ) -> Candle:
        """
        Normalize CCXT standard format: [timestamp, open, high, low, close, volume]
        """
        ts = cls.parse_timestamp(raw_ohlcv[0])
        return Candle(
            symbol=symbol,
            asset_class=AssetClass.CRYPTO,
            timestamp=ts,
            open=float(raw_ohlcv[1]),
            high=float(raw_ohlcv[2]),
            low=float(raw_ohlcv[3]),
            close=float(raw_ohlcv[4]),
            volume=float(raw_ohlcv[5]),
            exchange=exchange,
        )

    @classmethod
    def from_ccxt_trade(cls, raw_trade: Dict[str, Any], exchange: str = "binance") -> TradeEvent:
        """Normalize CCXT standard trade dict."""
        return TradeEvent(
            symbol=raw_trade.get("symbol", "UNKNOWN"),
            timestamp=cls.parse_timestamp(raw_trade.get("timestamp")),
            price=float(raw_trade.get("price", 0.0)),
            size=float(raw_trade.get("amount", 0.0)),
            side=OrderSide.BUY if raw_trade.get("side") == "buy" else OrderSide.SELL,
            exchange=exchange,
            trade_id=str(raw_trade.get("id", "")),
        )

    @classmethod
    def from_news_dict(cls, data: Dict[str, Any]) -> NewsItem:
        return NewsItem(
            id=str(data.get("id", "")),
            source=data.get("source", "generic"),
            headline=data.get("headline", ""),
            content=data.get("content", ""),
            url=data.get("url", ""),
            published_at=cls.parse_timestamp(data.get("published_at")),
            symbols_mentioned=data.get("symbols_mentioned", []),
            sentiment_score=float(data.get("sentiment_score", 0.0)),
        )

    @classmethod
    def from_social_dict(cls, data: Dict[str, Any]) -> SocialMetric:
        return SocialMetric(
            platform=data.get("platform", "generic"),
            symbol=data.get("symbol", ""),
            timestamp=cls.parse_timestamp(data.get("timestamp")),
            mention_count=int(data.get("mention_count", 0)),
            mention_velocity_pct=float(data.get("mention_velocity_pct", 0.0)),
            average_sentiment=float(data.get("average_sentiment", 0.0)),
            engagement_score=float(data.get("engagement_score", 0.0)),
        )

    @classmethod
    def from_macro_dict(cls, data: Dict[str, Any]) -> MacroIndicator:
        return MacroIndicator(
            series_id=data.get("series_id", ""),
            name=data.get("name", ""),
            timestamp=cls.parse_timestamp(data.get("timestamp")),
            value=float(data.get("value", 0.0)),
            unit=data.get("unit", ""),
            previous_value=float(data.get("previous_value", 0.0)) if data.get("previous_value") is not None else None,
            change_pct=float(data.get("change_pct", 0.0)) if data.get("change_pct") is not None else None,
        )
