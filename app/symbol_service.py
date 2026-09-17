"""Background symbol catalog synchronization.

Fetches the tradeable symbol set from the exchange on an interval and
upserts it into the PostgreSQL symbols table so ingestion can grow the
monitored universe automatically without config-file edits.
"""

import asyncio
from datetime import UTC, datetime

from app.core.logging import get_logger
from app.ingestion.market.global_provider import GlobalMarketDataProvider
from app.storage.postgres import PostgresStorage

logger = get_logger("SymbolService")

SYMBOL_REFRESH_INTERVAL_SECONDS = 600  # every 10 minutes


async def sync_symbol_catalog(
    postgres: PostgresStorage,
    provider: GlobalMarketDataProvider | None = None,
    quote: str = "USDT",
    limit: int = 30,
) -> list[str]:
    """Fetch the current symbol catalog from the global holder and upsert it into the DB."""
    provider = provider or GlobalMarketDataProvider()
    specs = await provider.fetch_available_symbols(quote=quote, limit=limit)
    if not specs:
        logger.warning("Symbol catalog fetch returned no symbols; keeping DB unchanged.")
        return []
    upserted = await postgres.bulk_upsert_symbols(specs)
    logger.info("Symbol catalog synced: %d symbols upserted at %s", upserted, datetime.now(UTC).isoformat())
    return [s.symbol for s in specs]


async def symbol_catalog_sync_job(
    postgres: PostgresStorage,
    interval_seconds: int = SYMBOL_REFRESH_INTERVAL_SECONDS,
    quote: str = "USDT",
    limit: int = 30,
) -> None:
    """Background loop: sync symbols from the global holder every interval (default 10m)."""
    logger.info("Symbol catalog sync job scheduled every %ds", interval_seconds)
    async with GlobalMarketDataProvider() as provider:
        while True:
            try:
                found = await sync_symbol_catalog(postgres, provider, quote=quote, limit=limit)
                if found:
                    logger.info("Symbols available after sync: %s", ", ".join(found))
            except Exception as e:  # resilience: keep the job alive across provider failures
                logger.error("Symbol catalog sync failed: %s", e)
            await asyncio.sleep(interval_seconds)
