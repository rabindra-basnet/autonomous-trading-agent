"""DefiLlama on-chain TVL and protocol metrics provider."""

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import ClassVar, Self

import httpx

from app.core.models import OnChainMetric
from app.ingestion.onchain.base import BaseOnChainProvider

logger = logging.getLogger("DefiLlamaProvider")


class DefiLlamaProvider(BaseOnChainProvider):
    TVL_API_URL = "https://api.llama.fi/charts"

    CHAIN_MAP: ClassVar[dict[str, str]] = {
        "BTC/USDT": "Bitcoin",
        "ETH/USDT": "Ethereum",
        "SOL/USDT": "Solana",
        "AVAX/USDT": "Avalanche",
        "MATIC/USDT": "Polygon",
        "BNB/USDT": "BSC",
        "ARB/USDT": "Arbitrum",
        "OP/USDT": "Optimism",
        "DOT/USDT": "Polkadot",
        "ADA/USDT": "Cardano",
        "TRX/USDT": "Tron",
    }

    def __init__(self):
        super().__init__(name="defillama")
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch_metrics(self, symbol: str) -> Sequence[OnChainMetric]:
        chain = self.CHAIN_MAP.get(symbol)
        if chain is None:
            return []
        url = f"{self.TVL_API_URL}/{chain}"

        metrics: list[OnChainMetric] = []
        try:
            resp = await self._get_client().get(url)
            if resp.status_code == 200:
                data = resp.json()
                for item in data[-10:]:  # Take last 10 snapshots
                    ts = datetime.fromtimestamp(int(item.get("date", 0)), tz=UTC)
                    tvl = float(item.get("totalLiquidityUSD", 0.0))
                    metrics.append(
                        OnChainMetric(
                            protocol=chain,
                            symbol=symbol,
                            timestamp=ts,
                            tvl_usd=tvl,
                        )
                    )
        except Exception as e:
            logger.warning(f"Error fetching DefiLlama metrics for {chain}: {e}")

        return metrics
