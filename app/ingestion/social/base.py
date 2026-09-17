"""Base class for Social Signals Providers."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence

from app.core.models import SocialMetric


class BaseSocialProvider(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def fetch_metrics(self, symbols: list[str]) -> Sequence[SocialMetric]:
        """Fetch aggregated social metrics."""

    @abstractmethod
    def stream_social_signals(self, symbols: list[str]) -> AsyncIterator[SocialMetric]:
        """Stream real-time social metrics."""
