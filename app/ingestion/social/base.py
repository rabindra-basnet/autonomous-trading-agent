"""Base class for Social Signals Providers."""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Sequence, List
from app.core.models import SocialMetric


class BaseSocialProvider(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def fetch_metrics(self, symbols: List[str]) -> Sequence[SocialMetric]:
        """Fetch aggregated social metrics."""
        pass

    @abstractmethod
    def stream_social_signals(self, symbols: List[str]) -> AsyncIterator[SocialMetric]:
        """Stream real-time social metrics."""
        pass
