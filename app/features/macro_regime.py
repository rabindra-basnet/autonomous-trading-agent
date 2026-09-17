"""Macroeconomic regime and On-chain feature computation."""

from typing import Sequence, Dict
from app.core.models import MacroIndicator, OnChainMetric


class MacroOnChainFeatures:
    @classmethod
    def compute_macro_features(cls, macro: Sequence[MacroIndicator]) -> Dict[str, float]:
        features: Dict[str, float] = {
            "fedfunds_rate": 4.50,
            "yield_spread_10y2y": 0.20,
            "cpi_yoy": 2.80,
            "macro_risk_on": 1.0,  # 1.0 = Risk-on, 0.0 = Risk-off
        }
        for m in macro:
            if "FEDFUNDS" in m.series_id:
                features["fedfunds_rate"] = float(m.value)
            elif "T10Y2Y" in m.series_id:
                features["yield_spread_10y2y"] = float(m.value)
            elif "CPI" in m.series_id:
                features["cpi_yoy"] = float(m.value)

        # Inverted yield curve or high rates trigger risk-off
        if features["yield_spread_10y2y"] < 0 or features["fedfunds_rate"] > 5.5:
            features["macro_risk_on"] = 0.0

        return features

    @classmethod
    def compute_onchain_features(cls, symbol: str, onchain: Sequence[OnChainMetric]) -> Dict[str, float]:
        rel = [o for o in onchain if o.symbol == symbol]
        if not rel:
            return {
                "onchain_tvl_usd": 0.0,
                "onchain_active_addresses": 0.0,
                "onchain_net_inflows_usd": 0.0,
                "onchain_whale_tx_count": 0.0,
            }

        latest = rel[-1]
        return {
            "onchain_tvl_usd": float(latest.tvl_usd),
            "onchain_active_addresses": float(latest.active_addresses),
            "onchain_net_inflows_usd": float(latest.exchange_net_inflow_usd),
            "onchain_whale_tx_count": float(latest.whale_transaction_count),
        }
