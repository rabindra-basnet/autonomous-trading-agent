"""Simulated news data provider for offline testing and backtesting."""

import asyncio
from datetime import datetime, timezone
import random
from typing import AsyncIterator, Sequence, List, Optional
from app.ingestion.news.base import BaseNewsProvider
from app.core.models import NewsItem


class SimulatedNewsProvider(BaseNewsProvider):
    HEADLINES = [
        ("Federal Reserve signals dovish rate trajectory for upcoming quarter", 0.65, ["BTC/USDT", "ETH/USDT"]),
        ("Crypto ETF inflows reach new all-time high amidst institutional demand", 0.85, ["BTC/USDT", "SOL/USDT"]),
        ("Major exchange undergoes regulatory scrutiny over derivatives listing", -0.55, ["BTC/USDT", "ETH/USDT", "SOL/USDT"]),
        ("Solana network throughput increases following major validator upgrade", 0.70, ["SOL/USDT"]),
        ("Inflation prints higher than expected, sparking risk-off sentiment", -0.60, ["BTC/USDT", "ETH/USDT"]),
        ("Leading venture fund raises $2B dedicated to decentralized infrastructure", 0.45, ["ETH/USDT", "SOL/USDT"]),
        ("Macro liquidity indicators show expansion across G10 economies", 0.50, ["BTC/USDT"]),
    ]

    def __init__(self):
        super().__init__(name="simulated_news")

    async def fetch_latest_news(
        self, keywords: Optional[List[str]] = None, limit: int = 10
    ) -> Sequence[NewsItem]:
        items: List[NewsItem] = []
        sampled = random.sample(self.HEADLINES, min(limit, len(self.HEADLINES)))
        for i, (headline, score, symbols) in enumerate(sampled):
            items.append(
                NewsItem(
                    id=f"sim_news_{i}_{int(datetime.now(timezone.utc).timestamp())}",
                    source="simulated_wire",
                    headline=headline,
                    url=f"https://simulated.news/{i}",
                    published_at=datetime.now(timezone.utc),
                    symbols_mentioned=symbols,
                    sentiment_score=score,
                )
            )
        return items

    async def stream_news(self, keywords: Optional[List[str]] = None) -> AsyncIterator[NewsItem]:
        while True:
            headline, score, symbols = random.choice(self.HEADLINES)
            yield NewsItem(
                id=f"sim_stream_{int(datetime.now(timezone.utc).timestamp()*1000)}",
                source="simulated_stream",
                headline=headline,
                url="https://simulated.news/stream",
                published_at=datetime.now(timezone.utc),
                symbols_mentioned=symbols,
                sentiment_score=score,
            )
            await asyncio.sleep(10.0)
