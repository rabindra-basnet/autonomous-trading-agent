"""Sentiment feature calculations for news and social signals."""

from datetime import datetime, timezone, timedelta
from typing import Sequence, Dict
import numpy as np
from app.core.models import NewsItem, SocialMetric


class SentimentFeatures:
    @classmethod
    def compute_sentiment_features(
        cls,
        symbol: str,
        news: Sequence[NewsItem],
        social: Sequence[SocialMetric],
        lookback_hours: int = 24,
    ) -> Dict[str, float]:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=lookback_hours)

        # Filter relevant news
        relevant_news = [
            n for n in news
            if (symbol in n.symbols_mentioned or not n.symbols_mentioned)
            and (n.published_at >= cutoff)
        ]

        # Filter relevant social
        relevant_social = [
            s for s in social
            if s.symbol == symbol and s.timestamp >= cutoff
        ]

        # News sentiment metrics
        news_sentiment = float(np.mean([n.sentiment_score for n in relevant_news])) if relevant_news else 0.0
        news_count = float(len(relevant_news))

        # Social metrics
        social_sentiment = (
            float(np.mean([s.average_sentiment for s in relevant_social]))
            if relevant_social
            else 0.0
        )
        social_mentions = float(sum(s.mention_count for s in relevant_social))
        social_velocity = (
            float(np.mean([s.mention_velocity_pct for s in relevant_social]))
            if relevant_social
            else 0.0
        )

        # Composite sentiment (weighted blend)
        composite_sentiment = (news_sentiment * 0.5) + (social_sentiment * 0.5)

        return {
            "news_sentiment": news_sentiment,
            "news_count_24h": news_count,
            "social_sentiment": social_sentiment,
            "social_mentions_24h": social_mentions,
            "social_velocity_pct": social_velocity,
            "composite_sentiment": composite_sentiment,
        }
