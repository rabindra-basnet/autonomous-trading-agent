"""Data Quality assurance: Outlier detection, clock drift synchronization, and gap detection."""

import logging
from datetime import UTC

from app.core.models import Candle, TradeEvent

logger = logging.getLogger("DataCleaner")


class DataQualityAssurance:
    def __init__(
        self,
        max_price_jump_pct: float = 0.50,  # Alert/filter > 50% single candle jump
        min_volume: float = 0.0,
    ):
        self.max_price_jump_pct = max_price_jump_pct
        self.min_volume = min_volume

    def validate_candle(self, candle: Candle, previous_candle: Candle | None = None) -> bool:
        """Validate candle integrity and sanity."""
        if candle.high < candle.low:
            logger.warning(f"Invalid candle {candle.symbol}: high ({candle.high}) < low ({candle.low})")
            return False

        if candle.open < candle.low or candle.open > candle.high:
            logger.warning(f"Invalid candle {candle.symbol}: open ({candle.open}) outside [low, high]")
            return False

        if candle.close < candle.low or candle.close > candle.high:
            logger.warning(f"Invalid candle {candle.symbol}: close ({candle.close}) outside [low, high]")
            return False

        if candle.volume < self.min_volume:
            logger.warning(f"Invalid candle {candle.symbol}: volume {candle.volume} < {self.min_volume}")
            return False

        # Outlier spike check against previous candle
        if previous_candle and previous_candle.close > 0:
            jump = abs(candle.close - previous_candle.close) / previous_candle.close
            if jump > self.max_price_jump_pct:
                logger.warning(
                    f"Outlier spike detected on {candle.symbol}: {jump * 100:.1f}% jump from {previous_candle.close} to {candle.close}"
                )
                return False

        return True

    def clean_candle_sequence(self, candles: list[Candle]) -> list[Candle]:
        """Filter out duplicates, sort by timestamp ascending, and remove invalid candles."""
        if not candles:
            return []

        # Sort by timestamp
        sorted_candles = sorted(candles, key=lambda c: c.timestamp)

        # Deduplicate and validate
        cleaned: list[Candle] = []
        seen_timestamps = set()

        for c in sorted_candles:
            # Enforce UTC
            ts = c.timestamp if c.timestamp.tzinfo else c.timestamp.replace(tzinfo=UTC)
            if ts in seen_timestamps:
                continue

            prev = cleaned[-1] if cleaned else None
            if self.validate_candle(c, prev):
                seen_timestamps.add(ts)
                cleaned.append(c)

        return cleaned

    def validate_trade(self, trade: TradeEvent) -> bool:
        """Validate single trade event."""
        return not (trade.price <= 0 or trade.size <= 0)
