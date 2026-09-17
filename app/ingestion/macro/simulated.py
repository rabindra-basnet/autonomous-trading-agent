"""Simulated macro indicator provider."""

from datetime import datetime, timezone, timedelta
import random
from typing import Sequence, List
from app.ingestion.macro.base import BaseMacroProvider
from app.core.models import MacroIndicator


class SimulatedMacroProvider(BaseMacroProvider):
    def __init__(self):
        super().__init__(name="simulated_macro")

    async def fetch_indicator(
        self, series_id: str, start_date: datetime
    ) -> Sequence[MacroIndicator]:
        indicators: List[MacroIndicator] = []
        curr_dt = start_date if start_date.tzinfo else start_date.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        val = 4.5 if "FED" in series_id else 0.35

        while curr_dt <= now:
            val += random.uniform(-0.1, 0.1)
            indicators.append(
                MacroIndicator(
                    series_id=series_id,
                    name=f"Simulated {series_id}",
                    timestamp=curr_dt,
                    value=round(val, 3),
                    unit="percent",
                )
            )
            curr_dt += timedelta(days=30)

        return indicators
