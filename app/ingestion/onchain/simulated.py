"""Simulated on-chain metrics provider."""

from datetime import datetime, timezone, timedelta
import random
from typing import Sequence, List
from app.ingestion.onchain.base import BaseOnChainProvider
from app.core.models import OnChainMetric


class SimulatedOnChainProvider(BaseOnChainProvider):
    def __init__(self):
        super().__init__(name="simulated_onchain")
        self.base_tvls = {
            "BTC/USDT": 25_000_000_000.0,
            "ETH/USDT": 55_000_000_000.0,
            "SOL/USDT": 8_000_000_000.0,
        }

    async def fetch_metrics(self, symbol: str) -> Sequence[OnChainMetric]:
        base = self.base_tvls.get(symbol, 10_000_000_000.0)
        metrics: List[OnChainMetric] = []
        now = datetime.now(timezone.utc)
        for i in range(5, 0, -1):
            ts = now - timedelta(hours=i * 4)
            tvl = base * (1 + random.uniform(-0.03, 0.05))
            metrics.append(
                OnChainMetric(
                    protocol=symbol.split("/")[0],
                    symbol=symbol,
                    timestamp=ts,
                    tvl_usd=tvl,
                    active_addresses=random.randint(50000, 250000),
                    exchange_net_inflow_usd=random.uniform(-50_000_000, 50_000_000),
                    whale_transaction_count=random.randint(10, 80),
                )
            )
        return metrics
