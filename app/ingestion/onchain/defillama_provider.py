"""DefiLlama on-chain TVL and protocol metrics provider."""

from datetime import datetime, timezone
import logging
from typing import Sequence, List
import httpx
from app.ingestion.onchain.base import BaseOnChainProvider
from app.core.models import OnChainMetric

logger = logging.getLogger("DefiLlamaProvider")


class DefiLlamaProvider(BaseOnChainProvider):
    TVL_API_URL = "https://api.llama.fi/charts"

    def __init__(self):
        super().__init__(name="defillama")

    async def fetch_metrics(self, symbol: str) -> Sequence[OnChainMetric]:
        chain_map = {
            "ETH/USDT": "Ethereum",
            "SOL/USDT": "Solana",
            "BTC/USDT": "Bitcoin",
        }
        chain = chain_map.get(symbol, "Ethereum")
        url = f"{self.TVL_API_URL}/{chain}"

        metrics: List[OnChainMetric] = []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data[-10:]:  # Take last 10 snapshots
                        ts = datetime.fromtimestamp(int(item.get("date", 0)), tz=timezone.utc)
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
