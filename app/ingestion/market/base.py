"""Base class for Market Data Providers."""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Sequence, List, Optional
from datetime import datetime
from app.core.models import Candle, TradeEvent, OrderBookSnapshot


class BaseMarketDataProvider(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def fetch_historical_candles(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> Sequence[Candle]:
        """Fetch historical candlestick data."""
        pass

    @abstractmethod
    async def fetch_ticker_price(self, symbol: str) -> float:
        """Fetch latest price."""
        pass

    @abstractmethod
    async def stream_trades(self, symbols: List[str]) -> AsyncIterator[TradeEvent]:
        """Stream real-time trade updates."""
        pass

    @abstractmethod
    async def stream_candles(self, symbols: List[str], timeframe: str) -> AsyncIterator[Candle]:
        """Stream real-time candle updates."""
        pass
