"""Macroeconomic regime and On-chain feature computation."""

from collections.abc import Sequence

from app.core.models import MacroIndicator, OnChainMetric


class MacroOnChainFeatures:
    @classmethod
    def compute_macro_features(cls, macro: Sequence[MacroIndicator]) -> dict[str, float]:
        features: dict[str, float] = {}
        for m in macro:
            if "FEDFUNDS" in m.series_id:
                features["fedfunds_rate"] = float(m.value)
            elif "T10Y2Y" in m.series_id:
                features["yield_spread_10y2y"] = float(m.value)
            elif "CPI" in m.series_id:
                features["cpi_yoy"] = float(m.value)

        # Risk-on/off only computed from actually-fetched rates; never fabricated.
        if "fedfunds_rate" in features and "yield_spread_10y2y" in features:
            inverted_yield = features["yield_spread_10y2y"] < 0
            features["macro_risk_on"] = 0.0 if inverted_yield or features["fedfunds_rate"] > 5.5 else 1.0

        return features

    @classmethod
    def compute_onchain_features(cls, symbol: str, onchain: Sequence[OnChainMetric]) -> dict[str, float]:
        rel = [o for o in onchain if o.symbol == symbol]
        if not rel:
            return {}

        latest = rel[-1]
        return {
            "onchain_tvl_usd": float(latest.tvl_usd),
            "onchain_active_addresses": float(latest.active_addresses),
            "onchain_net_inflows_usd": float(latest.exchange_net_inflow_usd),
            "onchain_whale_tx_count": float(latest.whale_transaction_count),
        }
