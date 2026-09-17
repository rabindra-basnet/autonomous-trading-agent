"""Simulated social provider for testing and deterministic backtesting."""

import asyncio
from datetime import datetime, timezone
import random
from typing import AsyncIterator, Sequence, List
from app.ingestion.social.base import BaseSocialProvider
from app.core.models import SocialMetric


class SimulatedSocialProvider(BaseSocialProvider):
    def __init__(self):
        super().__init__(name="simulated_social")
        self.counts = {"BTC/USDT": 1500, "ETH/USDT": 900, "SOL/USDT": 1200}

    async def fetch_metrics(self, symbols: List[str]) -> Sequence[SocialMetric]:
        metrics: List[SocialMetric] = []
        now = datetime.now(timezone.utc)
        for sym in symbols:
            prev = self.counts.get(sym, 500)
            change = random.randint(-150, 300)
            curr = max(50, prev + change)
            self.counts[sym] = curr
            velocity = ((curr - prev) / prev) * 100.0
            sentiment = random.uniform(-0.4, 0.8)

            metrics.append(
                SocialMetric(
                    platform="simulated_social",
                    symbol=sym,
                    timestamp=now,
                    mention_count=curr,
                    mention_velocity_pct=velocity,
                    average_sentiment=round(sentiment, 3),
                    engagement_score=float(curr * 2.5),
                )
            )
        return metrics

    async def stream_social_signals(self, symbols: List[str]) -> AsyncIterator[SocialMetric]:
        while True:
            metrics = await self.fetch_metrics(symbols)
            for m in metrics:
                yield m
            await asyncio.sleep(5.0)
