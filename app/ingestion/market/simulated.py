"""High-fidelity simulated market data provider (GBM + jump diffusion)."""

import asyncio
from datetime import datetime, timezone, timedelta
import random
from typing import AsyncIterator, Sequence, List
import numpy as np
from app.ingestion.market.base import BaseMarketDataProvider
from app.core.models import Candle, TradeEvent, OrderSide, AssetClass


class SimulatedMarketDataProvider(BaseMarketDataProvider):
    def __init__(
        self,
        base_prices: dict[str, float] | None = None,
        volatility: float = 0.02,
        drift: float = 0.0001,
        seed: int = 42,
    ):
        super().__init__(name="simulated_market")
        self.prices = base_prices or {
            "BTC/USDT": 65000.0,
            "ETH/USDT": 3500.0,
            "SOL/USDT": 150.0,
        }
        self.volatility = volatility
        self.drift = drift
        self.rng = np.random.default_rng(seed)

    async def fetch_historical_candles(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> Sequence[Candle]:
        candles: List[Candle] = []
        current_ts = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
        end_ts = end if end.tzinfo else end.replace(tzinfo=timezone.utc)

        # Map timeframe to timedelta
        delta = timedelta(hours=1)
        if timeframe == "1m":
            delta = timedelta(minutes=1)
        elif timeframe == "5m":
            delta = timedelta(minutes=5)
        elif timeframe == "15m":
            delta = timedelta(minutes=15)
        elif timeframe == "1d":
            delta = timedelta(days=1)

        current_price = self.prices.get(symbol, 100.0)

        while current_ts <= end_ts:
            ret = self.rng.normal(self.drift, self.volatility)
            # Add occasional jump
            if self.rng.random() < 0.03:
                ret += self.rng.normal(0, self.volatility * 3)

            close_p = max(0.01, current_price * (1 + ret))
            intra_noise = abs(self.rng.normal(0, self.volatility * 0.5))
            high_p = max(current_price, close_p) * (1 + intra_noise)
            low_p = min(current_price, close_p) * (1 - intra_noise)
            volume = float(self.rng.uniform(100, 5000) * (current_price / 1000.0))

            candle = Candle(
                symbol=symbol,
                asset_class=AssetClass.CRYPTO,
                timestamp=current_ts,
                open=round(current_price, 2),
                high=round(high_p, 2),
                low=round(low_p, 2),
                close=round(close_p, 2),
                volume=round(volume, 2),
                exchange="simulated",
            )
            candles.append(candle)
            current_price = close_p
            current_ts += delta

        self.prices[symbol] = current_price
        return candles

    async def fetch_ticker_price(self, symbol: str) -> float:
        curr = self.prices.get(symbol, 100.0)
        ret = self.rng.normal(self.drift, self.volatility * 0.2)
        new_p = max(0.01, curr * (1 + ret))
        self.prices[symbol] = new_p
        return round(new_p, 2)

    async def stream_trades(self, symbols: List[str]) -> AsyncIterator[TradeEvent]:
        while True:
            for symbol in symbols:
                price = await self.fetch_ticker_price(symbol)
                side = OrderSide.BUY if self.rng.random() > 0.5 else OrderSide.SELL
                size = float(round(self.rng.uniform(0.1, 2.5), 4))
                yield TradeEvent(
                    symbol=symbol,
                    timestamp=datetime.now(timezone.utc),
                    price=price,
                    size=size,
                    side=side,
                    exchange="simulated",
                )
            await asyncio.sleep(1.0)

    async def stream_candles(self, symbols: List[str], timeframe: str) -> AsyncIterator[Candle]:
        while True:
            for symbol in symbols:
                price = await self.fetch_ticker_price(symbol)
                spread = price * 0.002
                yield Candle(
                    symbol=symbol,
                    asset_class=AssetClass.CRYPTO,
                    timestamp=datetime.now(timezone.utc),
                    open=price - spread,
                    high=price + spread * 1.5,
                    low=price - spread * 1.5,
                    close=price,
                    volume=float(round(self.rng.uniform(500, 2000), 2)),
                    exchange="simulated",
                )
            await asyncio.sleep(2.0)
