"""Reddit social data ingestion adapter using public subreddit feeds."""

import asyncio
from datetime import datetime, timezone
import logging
from typing import AsyncIterator, Dict, List, Sequence
import httpx
from app.ingestion.social.base import BaseSocialProvider
from app.core.models import SocialMetric

logger = logging.getLogger("RedditSocialProvider")


class RedditSocialProvider(BaseSocialProvider):
    def __init__(self, subreddits: List[str] | None = None):
        super().__init__(name="reddit")
        self.subreddits = subreddits or ["cryptocurrency", "bitcoin", "solana", "ethfinance"]
        self._history_counts: Dict[str, int] = {}

    async def fetch_metrics(self, symbols: List[str]) -> Sequence[SocialMetric]:
        headers = {"User-Agent": "TradingAgentBot/1.0"}
        mention_counts: Dict[str, int] = {s: 0 for s in symbols}
        sentiment_sums: Dict[str, float] = {s: 0.0 for s in symbols}

        async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
            for sub in self.subreddits:
                try:
                    url = f"https://www.reddit.com/r/{sub}/hot.json?limit=25"
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        posts = data.get("data", {}).get("children", [])
                        for p in posts:
                            post_data = p.get("data", {})
                            title = post_data.get("title", "").lower()
                            score = post_data.get("score", 1)
                            for sym in symbols:
                                ticker = sym.split("/")[0].lower()
                                if ticker in title:
                                    mention_counts[sym] += 1
                                    # Basic heuristic sentiment
                                    sent = 0.1
                                    if any(w in title for w in ["bull", "buy", "up", "pump", "moon"]):
                                        sent += 0.4
                                    if any(w in title for w in ["bear", "sell", "down", "dump", "crash"]):
                                        sent -= 0.4
                                    sentiment_sums[sym] += sent * min(score / 10.0, 5.0)
                except Exception as e:
                    logger.warning(f"Failed to fetch Reddit sub r/{sub}: {e}")

        metrics: List[SocialMetric] = []
        now = datetime.now(timezone.utc)
        for sym in symbols:
            count = mention_counts[sym]
            prev = self._history_counts.get(sym, count)
            velocity = ((count - prev) / max(1, prev)) * 100.0
            self._history_counts[sym] = count

            avg_sent = (sentiment_sums[sym] / count) if count > 0 else 0.0
            avg_sent = max(-1.0, min(1.0, avg_sent))

            metrics.append(
                SocialMetric(
                    platform="reddit",
                    symbol=sym,
                    timestamp=now,
                    mention_count=count,
                    mention_velocity_pct=velocity,
                    average_sentiment=avg_sent,
                    engagement_score=float(count * 10),
                )
            )
        return metrics

    async def stream_social_signals(self, symbols: List[str]) -> AsyncIterator[SocialMetric]:
        while True:
            metrics = await self.fetch_metrics(symbols)
            for m in metrics:
                yield m
            await asyncio.sleep(120.0)
