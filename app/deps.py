"""Startup data-provider requirements: what live-data API keys are needed to run the system with real data.

Every enabled data source must be backed by a real provider (no simulations).
This module verifies at startup that each source has the credentials it needs
and tells the operator exactly which env var to set when one is missing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from app.core.logging import get_logger

logger = get_logger("DataProviderDeps")


@dataclass(frozen=True)
class ProviderRequirement:
    domain: str
    provider: str
    key_env: str | None
    required: bool
    hint: str


REQUIREMENTS: list[ProviderRequirement] = [
    ProviderRequirement(
        domain="market_data",
        provider="CCXT multi-exchange (binance, bybit, okx, kraken, ...)",
        key_env=None,
        required=True,
        hint="Global market data holder routes each symbol to a listing exchange; no API key required.",
    ),
    ProviderRequirement(
        domain="news",
        provider="GDELT 2.0",
        key_env=None,
        required=True,
        hint="Public keyless API; no API key required.",
    ),
    ProviderRequirement(
        domain="social",
        provider="Reddit public JSON",
        key_env=None,
        required=True,
        hint="Public subreddit feeds; no API key required.",
    ),
    ProviderRequirement(
        domain="macro",
        provider="FRED (St. Louis Fed)",
        key_env="FRED_API_KEY",
        required=False,
        hint="Macro regime features are only computed when this key is set. "
        "Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html",
    ),
    ProviderRequirement(
        domain="onchain",
        provider="DefiLlama",
        key_env=None,
        required=True,
        hint="Public keyless API; no API key required.",
    ),
]


def check_provider_requirements() -> bool:
    """Validate all live data-source requirements.

    Logs one status line per provider. Missing hard-required keys raise a
    RuntimeError with a clear message so the operator cannot run a silently
    incomplete ingestion stack. Optional keys (e.g. FRED) only warn.
    Returns True when everything required is satisfied.
    """
    missing_required = False
    for req in REQUIREMENTS:
        if req.key_env is None:
            logger.info("[OK] %-12s %-32s keyless", req.domain, req.provider)
            continue

        if os.getenv(req.key_env):
            logger.info("[OK] %-12s %-32s using %s", req.domain, req.provider, req.key_env)
            continue

        if req.required:
            logger.error("[MISSING] %-12s %-32s needs %s env var. %s", req.domain, req.provider, req.key_env, req.hint)
            missing_required = True
        else:
            logger.warning("[WARN] %-12s %-32s %s not set -> %s", req.domain, req.provider, req.key_env, req.hint)

    if missing_required:
        raise RuntimeError("Missing required data-provider API keys. Set the env vars above to run with live data.")
    return True


def main() -> int:
    """Doctor-style CLI: `python -m app.deps` prints provider status."""
    try:
        check_provider_requirements()
    except RuntimeError as e:
        print(f"DATA PROVIDER CHECK FAILED: {e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
