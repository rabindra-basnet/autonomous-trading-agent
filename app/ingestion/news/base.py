"""Base class for News Data Providers."""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Sequence, List, Optional
from app.core.models import NewsItem


class BaseNewsProvider(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def fetch_latest_news(
        self, keywords: Optional[List[str]] = None, limit: int = 50
    ) -> Sequence[NewsItem]:
        """Fetch latest news articles."""
        pass

    @abstractmethod
    def stream_news(self, keywords: Optional[List[str]] = None) -> AsyncIterator[NewsItem]:
        """Stream news items in real time."""
        pass
