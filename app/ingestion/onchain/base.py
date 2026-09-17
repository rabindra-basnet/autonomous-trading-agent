"""Base class for On-Chain Data Providers."""

from abc import ABC, abstractmethod
from typing import Sequence
from app.core.models import OnChainMetric


class BaseOnChainProvider(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def fetch_metrics(self, symbol: str) -> Sequence[OnChainMetric]:
        """Fetch on-chain metrics for symbol/protocol."""
        pass
