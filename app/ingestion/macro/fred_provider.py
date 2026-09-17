"""Federal Reserve Economic Data (FRED) macroeconomic data provider."""

from datetime import datetime, timezone
import os
import logging
from typing import List, Sequence
import httpx
from app.ingestion.macro.base import BaseMacroProvider
from app.core.models import MacroIndicator

logger = logging.getLogger("FREDMacroProvider")


class FREDMacroProvider(BaseMacroProvider):
    FRED_URL = "https://api.stlouisfed.org/fred/series/observations"

    def __init__(self, api_key: str | None = None):
        super().__init__(name="fred")
        self.api_key = api_key or os.getenv("FRED_API_KEY", "")

    async def fetch_indicator(
        self, series_id: str, start_date: datetime
    ) -> Sequence[MacroIndicator]:
        if not self.api_key:
            logger.warning("No FRED API key provided. Using fallback baseline data.")
            return [
                MacroIndicator(
                    series_id=series_id,
                    name=f"Series {series_id}",
                    timestamp=datetime.now(timezone.utc),
                    value=4.75 if "FEDFUNDS" in series_id else 0.45,
                    unit="percent",
                )
            ]

        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "observation_start": start_date.strftime("%Y-%m-%d"),
        }

        indicators: List[MacroIndicator] = []
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
                            dt = datetime.strptime(o.get("date"), "%Y-%m-%d").replace(tzinfo=timezone.utc)
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
        except Exception as e:
            logger.error(f"Error fetching FRED series {series_id}: {e}")

        return indicators
