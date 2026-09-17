"""GDELT (Global Database of Events, Language, and Tone) News Provider."""

import asyncio
from datetime import datetime, timezone
import logging
from typing import AsyncIterator, List, Optional, Sequence
import httpx
from app.ingestion.news.base import BaseNewsProvider
from app.core.models import NewsItem

logger = logging.getLogger("GDELTNewsProvider")


class GDELTNewsProvider(BaseNewsProvider):
    GDELT_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

    def __init__(self, default_keywords: Optional[List[str]] = None):
        super().__init__(name="gdelt")
        self.default_keywords = default_keywords or ["bitcoin", "crypto", "fed", "inflation"]

    async def fetch_latest_news(
        self, keywords: Optional[List[str]] = None, limit: int = 25
    ) -> Sequence[NewsItem]:
        kw = keywords or self.default_keywords
        query = " OR ".join(kw)
        params = {
            "query": query,
            "mode": "artlist",
            "maxrecords": str(limit),
            "format": "json",
            "sort": "datedesc",
        }
        items: List[NewsItem] = []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(self.GDELT_API_URL, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    articles = data.get("articles", [])
                    for art in articles:
                        title = art.get("title", "")
                        # Simple rule-based sentiment heuristics for GDELT titles
                        sent = 0.0
                        lower_title = title.lower()
                        positive_words = ["surge", "bull", "rally", "jump", "record", "gain", "breakout", "adoption"]
                        negative_words = ["crash", "bear", "plunge", "ban", "hack", "dump", "fraud", "lawsuit"]
                        for w in positive_words:
                            if w in lower_title:
                                sent += 0.3
                        for w in negative_words:
                            if w in lower_title:
                                sent -= 0.3
                        sent = max(-1.0, min(1.0, sent))

                        symbols = []
                        if "bitcoin" in lower_title or "btc" in lower_title:
                            symbols.append("BTC/USDT")
                        if "ethereum" in lower_title or "eth" in lower_title:
                            symbols.append("ETH/USDT")
                        if "solana" in lower_title or "sol" in lower_title:
                            symbols.append("SOL/USDT")

                        pub_str = art.get("seendate")
                        try:
                            pub_dt = datetime.strptime(pub_str, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
                        except Exception:
                            pub_dt = datetime.now(timezone.utc)

                        items.append(
                            NewsItem(
                                id=art.get("url", str(hash(title))),
                                source=art.get("domain", "gdelt"),
                                headline=title,
                                url=art.get("url", ""),
                                published_at=pub_dt,
                                symbols_mentioned=symbols,
                                sentiment_score=sent,
                            )
                        )
        except Exception as e:
            logger.warning(f"Failed to fetch from GDELT API: {e}")

        return items

    async def stream_news(self, keywords: Optional[List[str]] = None) -> AsyncIterator[NewsItem]:
        seen_ids = set()
        while True:
            news_items = await self.fetch_latest_news(keywords, limit=10)
            for item in news_items:
                if item.id not in seen_ids:
                    seen_ids.add(item.id)
                    yield item
            await asyncio.sleep(60.0)
