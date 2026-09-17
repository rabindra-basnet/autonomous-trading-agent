"""Dynamic Symbol Management & Registry for active trading pairs."""

import asyncio
from typing import List, Set, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from app.config import settings
from app.core.logging import get_logger

logger = get_logger("SymbolManager")


class SymbolInfo(BaseModel):
    symbol: str
    base_asset: str
    quote_asset: str
    active: bool = True
    added_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SymbolManager:
    """Thread-safe dynamic manager for actively tracked and traded asset pairs."""

    def __init__(self, initial_symbols: Optional[List[str]] = None):
        self._symbols: Set[str] = set()
        raw_list = initial_symbols or settings.symbols
        for s in raw_list:
            norm = self._normalize(s)
            if norm:
                self._symbols.add(norm)
        logger.info(f"SymbolManager initialized with {len(self._symbols)} active pairs: {sorted(list(self._symbols))}")

    @staticmethod
    def _normalize(symbol: str) -> str:
        s = symbol.strip().upper()
        if "/" not in s and len(s) >= 6:
            # e.g. BTCUSDT -> BTC/USDT
            if s.endswith("USDT"):
                return f"{s[:-4]}/USDT"
            elif s.endswith("USD"):
                return f"{s[:-3]}/USD"
        return s

    def get_active_symbols(self) -> List[str]:
        """Return list of currently active symbols sorted alphabetically."""
        return sorted(list(self._symbols))

    def get_symbol_details(self) -> List[SymbolInfo]:
        """Return detailed info for all active symbols."""
        details = []
        for s in self.get_active_symbols():
            parts = s.split("/")
            base = parts[0] if len(parts) > 0 else s
            quote = parts[1] if len(parts) > 1 else "USDT"
            details.append(
                SymbolInfo(
                    symbol=s,
                    base_asset=base,
                    quote_asset=quote,
                    active=True,
                )
            )
        return details

    def add_symbol(self, symbol: str) -> str:
        """Dynamically add a new symbol to the active tracking registry."""
        norm = self._normalize(symbol)
        if not norm:
            raise ValueError(f"Invalid symbol format: {symbol}")
        if norm not in self._symbols:
            self._symbols.add(norm)
            logger.info(f"Dynamically added symbol to active registry: {norm}")
        return norm

    def add_symbols(self, symbols: List[str]) -> List[str]:
        """Add multiple symbols at once."""
        added = []
        for s in symbols:
            added.append(self.add_symbol(s))
        return added

    def remove_symbol(self, symbol: str) -> bool:
        """Remove a symbol from active tracking."""
        norm = self._normalize(symbol)
        if norm in self._symbols:
            self._symbols.remove(norm)
            logger.info(f"Removed symbol from active registry: {norm}")
            return True
        return False
