"""Federal Reserve Economic Data (FRED) macroeconomic data provider."""

import logging
import os
from collections.abc import Sequence
from datetime import UTC, datetime

import httpx

from app.core.models import MacroIndicator
from app.ingestion.macro.base import BaseMacroProvider

logger = logging.getLogger("FREDMacroProvider")


class FREDMacroProvider(BaseMacroProvider):
    FRED_URL = "https://api.stlouisfed.org/fred/series/observations"

    def __init__(self, api_key: str | None = None):
        super().__init__(name="fred")
        self.api_key = api_key or os.getenv("FRED_API_KEY", "")

    async def fetch_indicator(self, series_id: str, start_date: datetime) -> Sequence[MacroIndicator]:
        if not self.api_key:
            logger.warning(
                "FRED_API_KEY not set; returning no data for %s. "
                "Macro features will be unavailable until the key is configured.",
                series_id,
            )
            return []

        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "observation_start": start_date.strftime("%Y-%m-%d"),
        }

        indicators: list[MacroIndicator] = []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(self.FRED_URL, params=params)
                if resp.status_code == 200:
                    obs = resp.json().get("observations", [])
                    prev_val = None
                    for o in obs:
                        val_str = o.get("value")
                        if val_str and val_str != ".":
                            val = float(val_str)
                            dt = datetime.strptime(o.get("date"), "%Y-%m-%d").replace(tzinfo=UTC)
                            chg = ((val - prev_val) / prev_val) * 100.0 if prev_val else 0.0
                            indicators.append(
                                MacroIndicator(
                                    series_id=series_id,
                                    name=series_id,
                                    timestamp=dt,
                                    value=val,
                                    previous_value=prev_val,
                                    change_pct=chg,
                                )
                            )
                            prev_val = val
        except Exception:
            logger.exception("Error fetching FRED series %s", series_id)

        return indicators
