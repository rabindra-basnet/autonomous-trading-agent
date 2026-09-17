"""Point-in-time correct Feature Store."""

from datetime import UTC, datetime

import pandas as pd

from app.core.models import FeatureVector


class PointInTimeFeatureStore:
    def __init__(self):
        self._cache: dict[str, list[FeatureVector]] = {}

    def put_features(self, feature_vector: FeatureVector) -> None:
        sym = feature_vector.symbol
        if sym not in self._cache:
            self._cache[sym] = []
        self._cache[sym].append(feature_vector)
        # Sort to maintain strict temporal ordering
        self._cache[sym].sort(key=lambda x: x.timestamp)

    def get_latest_features(self, symbol: str) -> FeatureVector | None:
        vectors = self._cache.get(symbol, [])
        return vectors[-1] if vectors else None

    def get_features_as_of(self, symbol: str, as_of: datetime) -> FeatureVector | None:
        """Strict point-in-time lookup without lookahead bias: return latest features <= as_of."""
        as_of_tz = as_of if as_of.tzinfo else as_of.replace(tzinfo=UTC)
        vectors = self._cache.get(symbol, [])
        valid = [
            v for v in vectors if (v.timestamp if v.timestamp.tzinfo else v.timestamp.replace(tzinfo=UTC)) <= as_of_tz
        ]
        return valid[-1] if valid else None

    def to_dataframe(self, symbol: str) -> pd.DataFrame:
        vectors = self._cache.get(symbol, [])
        if not vectors:
            return pd.DataFrame()
        records = []
        for v in vectors:
            rec = {"timestamp": v.timestamp, "symbol": v.symbol}
            rec.update(v.features)
            records.append(rec)
        df = pd.DataFrame(records)
        df.set_index("timestamp", inplace=True)
        return df
