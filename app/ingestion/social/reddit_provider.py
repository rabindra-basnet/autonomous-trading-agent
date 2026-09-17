"""Reddit social data ingestion adapter using the public Atom RSS feeds.

Reddit's public JSON endpoints (``hot.json`` / ``search.json``) are WAF-blocked
with ``HTTP 403 Blocked`` for unauthenticated clients. The public Atom RSS
feeds (``/r/{sub}/hot.rss``) serve reliably to identified User-Agents, so this
provider reads RSS only — the same approach used by the TradingAgents framework.

Best-effort by design:
  * a descriptive, identified ``User-Agent`` (Reddit blocks generic/anonymous
    tokens like a bare "curl" or "Mozilla/5.0");
  * pacing between subreddit requests plus a single ``429`` back-off that
    honours ``Retry-After``;
  * a failed subreddit fetch degrades to zero mentions for that sub, and a
    fully-failed fetch returns empty metrics instead of fabricating data.
"""

import asyncio
import logging
import random
import xml.etree.ElementTree as ET
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime

import httpx

from app.core.models import SocialMetric
from app.ingestion.social.base import BaseSocialProvider

logger = logging.getLogger("RedditSocialProvider")

# Identified client per Reddit's API etiquette; required to avoid 403s.
USER_AGENT = "autonomous-trading-agent/0.1 (+https://github.com/autonomous-trading-agent)"
ATOM_NS = "http://www.w3.org/2005/Atom"

DEFAULT_SUBREDDITS = ["cryptocurrency", "bitcoin", "solana", "ethfinance"]

# Pacing between subreddit requests to stay under Reddit's public per-IP limit.
INTER_REQUEST_DELAY = 1.0
_RETRY_FALLBACK_SECONDS = 30.0


def _jitter(seconds: float, frac: float = 0.2) -> float:
    """Return ``seconds`` with +/- ``frac`` jitter to desynchronize concurrent runs."""
    return seconds * (1.0 + random.uniform(-frac, frac))


class RedditSocialProvider(BaseSocialProvider):
    def __init__(self, subreddits: list[str] | None = None):
        super().__init__(name="reddit")
        self.subreddits = subreddits or DEFAULT_SUBREDDITS
        self._history_counts: dict[str, int] = {}

    @staticmethod
    def _tickerize(symbol: str) -> str:
        """Map a unified pair (BTC/USDT) to the Reddit mention keyword (btc)."""
        return symbol.split("/")[0].lower()

    @staticmethod
    def _heuristic_sentiment(title: str) -> float:
        """Rule-based sentiment from a post title; clamp to [-1.0, 1.0]."""
        positive = ["bull", "buy", "up", "pump", "moon", "surge", "rally", "gain", "record", "breakout"]
        negative = ["bear", "sell", "down", "dump", "crash", "plunge", "ban", "hack", "fraud", "lawsuit"]
        sent = 0.0
        if any(w in title for w in positive):
            sent += 0.4
        if any(w in title for w in negative):
            sent -= 0.4
        return max(-1.0, min(1.0, sent))

    async def _fetch_subreddit_feed(
        self,
        client: httpx.AsyncClient,
        sub: str,
        limit: int = 25,
        timeout: float = 10.0,
        _retry: bool = True,
    ) -> list[tuple[str, str]] | None:
        """Fetch hot (title, published_at) pairs for a subreddit via the public RSS feed.

        Returns ``None`` when the fetch failed so the caller can distinguish a
        failure from an empty result set.
        """
        url = f"https://www.reddit.com/r/{sub}/hot.rss?limit={limit}"
        try:
            resp = await client.get(url)
        except httpx.HTTPError as e:
            logger.warning("Reddit RSS fetch failed for r/%s: %s", sub, e)
            return None

        if resp.status_code == 429 and _retry:
            retry_after = float(resp.headers.get("Retry-After", 0) or 0)
            wait = retry_after if retry_after > 0 else _jitter(_RETRY_FALLBACK_SECONDS)
            logger.warning("Reddit RSS 429 for r/%s — backing off %.1fs then retrying once", sub, wait)
            await asyncio.sleep(wait)
            return await self._fetch_subreddit_feed(client, sub, limit, timeout, _retry=False)

        if resp.status_code != 200:
            logger.warning("Reddit RSS request for r/%s returned status %s", sub, resp.status_code)
            return None

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as e:
            logger.warning("Reddit RSS parse failed for r/%s: %s", sub, e)
            return None

        posts: list[tuple[str, str]] = []
        for entry in root.findall(f"{{{ATOM_NS}}}entry")[:limit]:
            title_el = entry.find(f"{{{ATOM_NS}}}title")
            published_el = entry.find(f"{{{ATOM_NS}}}published")
            title = (title_el.text if title_el is not None else "") or ""
            published = (published_el.text if published_el is not None else "") or ""
            posts.append((title, published))
        return posts

    async def fetch_metrics(self, symbols: list[str]) -> Sequence[SocialMetric]:
        mention_counts: dict[str, int] = {s: 0 for s in symbols}
        sentiment_sums: dict[str, float] = {s: 0.0 for s in symbols}

        headers = {"User-Agent": USER_AGENT}
        async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
            for i, sub in enumerate(self.subreddits):
                if i > 0 and INTER_REQUEST_DELAY:
                    await asyncio.sleep(_jitter(INTER_REQUEST_DELAY))
                posts = await self._fetch_subreddit_feed(client, sub)
                if posts is None:
                    logger.warning("Reddit feed for r/%s unavailable; counting as zero mentions", sub)
                    continue
                for title, _published in posts:
                    lower_title = title.lower()
                    for sym in symbols:
                        ticker = self._tickerize(sym)
                        if ticker not in lower_title:
                            continue
                        mention_counts[sym] += 1
                        sentiment_sums[sym] += self._heuristic_sentiment(lower_title)

        metrics: list[SocialMetric] = []
        now = datetime.now(UTC)
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

    async def stream_social_signals(self, symbols: list[str]) -> AsyncIterator[SocialMetric]:
        while True:
            metrics = await self.fetch_metrics(symbols)
            for m in metrics:
                yield m
            await asyncio.sleep(120.0)
