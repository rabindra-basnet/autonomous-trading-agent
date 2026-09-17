"""Base class for News Data Providers."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence

from app.core.models import NewsItem


class BaseNewsProvider(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def fetch_latest_news(self, keywords: list[str] | None = None, limit: int = 50) -> Sequence[NewsItem]:
        """Fetch latest news articles."""

    @abstractmethod
    def stream_news(self, keywords: list[str] | None = None) -> AsyncIterator[NewsItem]:
        """Stream news items in real time."""
