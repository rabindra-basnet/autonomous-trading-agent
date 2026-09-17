"""Global multi-exchange market data holder.

Binary exchange routing on a single venue (e.g. Binance) limits the monitorable
universe because every exchange lists a different subset of symbols. This
provider holds several ccxt exchanges, builds a global symbol-to-exchange index,
and routes each symbol to the venue that best satisfies the routing criteria:

  1. liquidity  - highest recent quote volume (deepest venue wins)
  2. quote pair - USDT is preferred over USDC over USD
  3. priority   - deterministic exchange fallback order for equal scores

The index is built lazily once (across all configured exchanges in parallel) and
cached for the lifetime of the process so per-cycle routing is a dict lookup.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from typing import Any, Self

from app.core.models import Candle, SymbolSpec, TradeEvent
from app.ingestion.market.base import BaseMarketDataProvider
from app.normalization.normalizer import DataNormalizer

logger = logging.getLogger("GlobalMarketDataProvider")

# Deterministic routing order used as the tie-breaker criterion (#3).
DEFAULT_EXCHANGE_PRIORITY = ["binance", "bybit", "okx", "kraken", "bitget", "kucoin"]

# Quote-pair preference criterion (#2): higher is better.
QUOTE_PRIORITY = {"USDT": 2, "USDC": 1, "USD": 0}

# Only tradeable spot + derivatives pairs on the unified {BASE}/{QUOTE} key.
SPOT_TYPES = {"spot", "swap", "future"}

_DEFAULT_QUOTES = ("USDT", "USDC", "USD")


class GlobalMarketDataProvider(BaseMarketDataProvider):
    """Aggregated ccxt market-data provider with cross-exchange symbol routing."""

    def __init__(
        self,
        exchange_ids: list[str] | None = None,
        quotes: tuple[str, ...] | None = None,
    ):
        super().__init__(name="global_ccxt")
        self.exchange_ids = exchange_ids or DEFAULT_EXCHANGE_PRIORITY
        self.quotes = quotes or _DEFAULT_QUOTES
        self._exchanges: dict[str, Any] = {}
        self._symbol_index: dict[str, list[dict[str, Any]]] = {}
        self._initialized = False
        self._runtime_ms = 0.0

    async def _ensure_init(self) -> None:
        """Build the global symbol index once by loading markets from every exchange in parallel."""
        if self._initialized:
            return

        import ccxt.async_support as ccxt_async  # type: ignore

        started = asyncio.get_event_loop().time()
        exchanges: dict[str, Any] = {}
        for exchange_id in self.exchange_ids:
            exchange_class = getattr(ccxt_async, exchange_id, None)
            if exchange_class is None:
                logger.warning("Exchange %s not found in ccxt; skipping.", exchange_id)
                continue
            exchanges[exchange_id] = exchange_class(
                {
                    "enableRateLimit": True,
                    "timeout": 15000,
                }
            )

        async def _load(exchange_id: str) -> tuple[str, dict[str, Any] | Exception]:
            try:
                markets = await exchanges[exchange_id].load_markets()
                return exchange_id, markets
            except Exception as e:  # per-exchange isolation: one bad venue must not kill the index
                return exchange_id, e

        results = dict(await asyncio.gather(*[_load(exchange_id) for exchange_id in exchanges]))

        for exchange_id, markets in results.items():
            if isinstance(markets, Exception):
                logger.warning("Could not load markets from %s; skipping it: %s", exchange_id, markets)
                try:
                    await exchanges[exchange_id].close()
                except Exception:
                    pass
                continue

            self._exchanges[exchange_id] = exchanges[exchange_id]
            priority_idx = self.exchange_ids.index(exchange_id)
            added = 0
            for symbol, market in markets.items():
                if not market.get("active", True):
                    continue
                if market.get("type") not in SPOT_TYPES:
                    continue
                quote = market.get("quote", "")
                if quote not in self.quotes:
                    continue
                liquidity, quote_bonus = self._candidate_score(market)
                self._symbol_index.setdefault(symbol, []).append(
                    {
                        "exchange": exchange_id,
                        "liquidity": liquidity,
                        "quote_bonus": quote_bonus,
                        "priority_idx": priority_idx,
                    }
                )
                added += 1
            logger.debug("Loaded %d indexable %s-pairs from %s", added, "/".join(self.quotes), exchange_id)

        # Sort every symbol's candidates by criteria: liquidity, quote pair, priority.
        for candidates in self._symbol_index.values():
            candidates.sort(key=lambda c: (c["liquidity"], c["quote_bonus"], -c["priority_idx"]), reverse=True)

        self._runtime_ms = (asyncio.get_event_loop().time() - started) * 1000.0
        self._initialized = True
        logger.info(
            "Global market holder ready: %d symbols across %d exchanges (indexed in %.1f ms)",
            len(self._symbol_index),
            len(self._exchanges),
            self._runtime_ms,
        )

    @staticmethod
    def _candidate_score(market: dict[str, Any]) -> tuple[float, int]:
        """Score a market against the routing criteria.

        Returns (liquidity, quote_bonus). Liquidity uses the reported quote
        volume so deeper venues win, and quote_bonus prefers USDT > USDC > USD.
        """
        raw_qv = market.get("quoteVolume")
        try:
            liquidity = float(raw_qv) if raw_qv not in (None, "", "nan") else 0.0
        except (TypeError, ValueError):
            liquidity = 0.0
        quote_bonus = QUOTE_PRIORITY.get(market.get("quote", ""), 0)
        return max(0.0, liquidity), quote_bonus

    def get_symbol_routes(self, symbol: str) -> list[str]:
        """Exchanges that list the symbol, ordered best-first by routing criteria."""
        return [c["exchange"] for c in self._symbol_index.get(symbol, [])]

    def routes_for(self, symbol: str) -> list[dict[str, Any]]:
        """Return per-exchange routing candidates for a symbol (best first)."""
        return [
            {
                "exchange": c["exchange"],
                "liquidity": c["liquidity"],
                "quote_bonus": c["quote_bonus"],
                "priority_index": c["priority_idx"],
            }
            for c in self._symbol_index.get(symbol, [])
        ]

    def index_summary(self) -> dict[str, Any]:
        """Return a diagnostic snapshot of the built global routing index."""
        # Per-exchange symbol counts
        per_exchange: dict[str, int] = {eid: 0 for eid in self._exchanges}
        for candidates in self._symbol_index.values():
            for c in candidates:
                eid = c["exchange"]
                if eid in per_exchange:
                    per_exchange[eid] += 1

        # Symbols that route to each exchange as the primary (best) venue
        primary_by_exchange: dict[str, list[str]] = {eid: [] for eid in self._exchanges}
        for symbol, candidates in self._symbol_index.items():
            best = candidates[0]["exchange"]
            if best in primary_by_exchange:
                primary_by_exchange[best].append(symbol)

        return {
            "total_symbols_indexed": len(self._symbol_index),
            "total_exchanges_loaded": len(self._exchanges),
            "index_build_ms": round(self._runtime_ms, 1),
            "per_exchange_candidate_count": per_exchange,
            "per_exchange_primary_symbols": {k: len(v) for k, v in primary_by_exchange.items()},
        }

    def _route(self, symbol: str) -> Any:
        """Return the best exchange client for a symbol, raising KeyError when unlisted."""
        candidates = self._symbol_index.get(symbol)
        if not candidates:
            raise KeyError(
                f"Symbol {symbol} not found on any configured exchange {self.exchange_ids}. "
                "Check the symbol name or add the exchange that lists it."
            )
        exchange_id = candidates[0]["exchange"]
        return self._exchanges[exchange_id]

    async def fetch_ticker_price(self, symbol: str) -> float:
        await self._ensure_init()
        exchange = self._route(symbol)
        ticker = await exchange.fetch_ticker(symbol)
        return float(ticker.get("last", 0.0))

    async def fetch_historical_candles(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> Sequence[Candle]:
        await self._ensure_init()
        exchange = self._route(symbol)
        since = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        all_candles: list[Candle] = []

        while since < end_ms:
            raw_ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=500)
            if not raw_ohlcv:
                break
            for item in raw_ohlcv:
                candle = DataNormalizer.from_ccxt_ohlcv(item, symbol, exchange.id)
                if candle.timestamp <= end:
                    all_candles.append(candle)
            since = raw_ohlcv[-1][0] + 1
            if len(raw_ohlcv) < 500:
                break
        return all_candles

    async def fetch_available_symbols(self, quote: str = "USDT", limit: int = 30) -> list[SymbolSpec]:
        """
        Discover the global tradeable symbol catalog across all held exchanges.

        Symbols are ranked by the routing criteria (liquidity, quote pair,
        priority) so the returned set reflects the deepest, most reliable venue.
        """
        await self._ensure_init()
        preferred = QUOTE_PRIORITY.get(quote, 0)
        specs: list[SymbolSpec] = []
        for symbol, candidates in self._symbol_index.items():
            if symbol.split("/")[1] != quote:
                continue
            if candidates[0]["quote_bonus"] != preferred:
                continue
            specs.append(
                SymbolSpec(
                    symbol=symbol,
                    asset_class="crypto",
                    timeframe="1h",
                    category="global",
                )
            )
            if len(specs) >= limit:
                break
        logger.info("Discovered %d of %d global %s symbols", len(specs), len(self._symbol_index), quote)
        return specs

    async def stream_trades(self, symbols: list[str]) -> AsyncIterator[TradeEvent]:
        await self._ensure_init()
        while True:
            for symbol in symbols:
                try:
                    exchange = self._route(symbol)
                    trades = await exchange.fetch_trades(symbol, limit=10)
                    for t in trades:
                        yield DataNormalizer.from_ccxt_trade(t, exchange.id)
                except Exception as e:
                    logger.warning("Failed to fetch trades for %s: %s", symbol, e)
            await asyncio.sleep(2.0)

    async def stream_candles(self, symbols: list[str], timeframe: str) -> AsyncIterator[Candle]:
        await self._ensure_init()
        while True:
            for symbol in symbols:
                try:
                    exchange = self._route(symbol)
                    ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=1)
                    if ohlcv:
                        yield DataNormalizer.from_ccxt_ohlcv(ohlcv[-1], symbol, exchange.id)
                except Exception as e:
                    logger.warning("Failed to stream candle for %s: %s", symbol, e)
            await asyncio.sleep(5.0)

    async def close(self) -> None:
        for exchange in self._exchanges.values():
            try:
                await exchange.close()
            except Exception:
                logger.warning("Error closing exchange client", exc_info=True)
        self._exchanges.clear()
        self._initialized = False
        self._symbol_index.clear()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()
