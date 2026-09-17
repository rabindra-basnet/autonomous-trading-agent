"""CCXT-based universal cryptocurrency market data adapter."""

import asyncio
from datetime import datetime, timezone
from typing import AsyncIterator, Sequence, List, Optional, Any
import logging
from app.ingestion.market.base import BaseMarketDataProvider
from app.core.models import Candle, TradeEvent, OrderSide, AssetClass
from app.normalization.normalizer import DataNormalizer

logger = logging.getLogger("CCXTMarketDataProvider")


class CCXTMarketDataProvider(BaseMarketDataProvider):
    def __init__(self, exchange_id: str = "binance", sandbox: bool = False):
        super().__init__(name=f"ccxt_{exchange_id}")
        self.exchange_id = exchange_id
        self.sandbox = sandbox
        self._exchange: Any = None
        self._initialized = False

    def _get_exchange(self) -> Any:
        if not self._initialized:
            try:
                import ccxt.async_support as ccxt_async  # type: ignore
                exchange_class = getattr(ccxt_async, self.exchange_id, None)
                if not exchange_class:
                    logger.warning(f"Exchange {self.exchange_id} not found in ccxt, falling back to binance")
                    exchange_class = ccxt_async.binance

                self._exchange = exchange_class({
                    'enableRateLimit': True,
                    'timeout': 15000,
                })
                if self.sandbox:
                    self._exchange.set_sandbox_mode(True)
                self._initialized = True
            except ImportError:
                logger.error("CCXT library not installed or cannot import async_support.")
                raise
        return self._exchange

    async def fetch_historical_candles(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> Sequence[Candle]:
        exchange = self._get_exchange()
        since = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        all_candles: List[Candle] = []

        try:
            while since < end_ms:
                raw_ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=500)
                if not raw_ohlcv:
                    break
                for item in raw_ohlcv:
                    candle = DataNormalizer.from_ccxt_ohlcv(item, symbol, self.exchange_id)
                    if candle.timestamp <= end:
                        all_candles.append(candle)
                since = raw_ohlcv[-1][0] + 1
                if len(raw_ohlcv) < 500:
                    break
        except Exception as e:
            logger.error(f"Error fetching OHLCV from {self.exchange_id} for {symbol}: {e}")
            raise

        return all_candles

    async def fetch_ticker_price(self, symbol: str) -> float:
        exchange = self._get_exchange()
        ticker = await exchange.fetch_ticker(symbol)
        return float(ticker.get("last", 0.0))

    async def stream_trades(self, symbols: List[str]) -> AsyncIterator[TradeEvent]:
        exchange = self._get_exchange()
        while True:
            for symbol in symbols:
                try:
                    trades = await exchange.fetch_trades(symbol, limit=10)
                    for t in trades:
                        yield DataNormalizer.from_ccxt_trade(t, self.exchange_id)
                except Exception as e:
                    logger.warning(f"Failed to fetch trades for {symbol}: {e}")
            await asyncio.sleep(2.0)

    async def stream_candles(self, symbols: List[str], timeframe: str) -> AsyncIterator[Candle]:
        exchange = self._get_exchange()
        while True:
            for symbol in symbols:
                try:
                    ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=1)
                    if ohlcv:
                        yield DataNormalizer.from_ccxt_ohlcv(ohlcv[-1], symbol, self.exchange_id)
                except Exception as e:
                    logger.warning(f"Failed to stream candle for {symbol}: {e}")
            await asyncio.sleep(5.0)

    async def close(self) -> None:
        if self._exchange:
            await self._exchange.close()
