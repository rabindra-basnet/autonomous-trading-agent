"""Base Strategy Class."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any
from app.core.models import FeatureVector, PortfolioState, TradingSignal


class BaseStrategy(ABC):
    def __init__(self, name: str, symbols: List[str], parameters: Dict[str, Any] | None = None):
        self.name = name
        self.symbols = symbols
        self.parameters = parameters or {}

    @abstractmethod
    def generate_signals(
        self,
        feature_vector: FeatureVector,
        portfolio: PortfolioState,
    ) -> List[TradingSignal]:
        """Evaluate market state and emit signals."""
        pass
