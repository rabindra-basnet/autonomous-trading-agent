"""Base class for Market Data Providers."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from datetime import datetime

from app.core.models import Candle, TradeEvent


class BaseMarketDataProvider(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def fetch_historical_candles(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> Sequence[Candle]:
        """Fetch historical candlestick data."""

    @abstractmethod
    async def fetch_ticker_price(self, symbol: str) -> float:
        """Fetch latest price."""

    @abstractmethod
    def stream_trades(self, symbols: list[str]) -> AsyncIterator[TradeEvent]:
        """Stream real-time trade updates."""

    @abstractmethod
    def stream_candles(self, symbols: list[str], timeframe: str) -> AsyncIterator[Candle]:
        """Stream real-time candle updates."""
