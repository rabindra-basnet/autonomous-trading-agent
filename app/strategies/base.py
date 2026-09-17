"""Base Strategy Class."""

from abc import ABC, abstractmethod
from typing import Any

from app.core.models import FeatureVector, PortfolioState, TradingSignal


class BaseStrategy(ABC):
    def __init__(self, name: str = "", symbols: list[str] | None = None, parameters: dict[str, Any] | None = None):
        self.name = name
        self.symbols = symbols or []
        self.parameters = parameters or {}

    @abstractmethod
    def generate_signals(
        self,
        feature_vector: FeatureVector,
        portfolio: PortfolioState,
    ) -> list[TradingSignal]:
        """Evaluate market state and emit signals."""
