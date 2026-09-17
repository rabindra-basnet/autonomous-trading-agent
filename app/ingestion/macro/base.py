"""Base class for Macroeconomic Data Providers."""

from abc import ABC, abstractmethod
from typing import Sequence
from datetime import datetime
from app.core.models import MacroIndicator


class BaseMacroProvider(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def fetch_indicator(
        self, series_id: str, start_date: datetime
    ) -> Sequence[MacroIndicator]:
        """Fetch macroeconomic time series."""
        pass
