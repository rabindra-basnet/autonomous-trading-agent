"""DuckDB-backed time-series analytical store.

DuckDB allows exactly one read-write process per database file; additional
processes must open the same file read-only. This module makes those rules
explicit and safe:

* one shared connection per database path inside a process, so two subsystems
  (e.g. the API and a background job) cannot deadlock each other on the file
  lock;
* bounded retry with backoff while another process briefly holds the lock;
* a deliberate read-only fallback for readers instead of a silent in-memory
  swap that would quietly split the dataset and lose writes;
* an explicit error when a *writable* store is required but unavailable.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Self, cast

import duckdb
import pandas as pd

from app.core.models import AssetClass, Candle

logger = logging.getLogger("TimeSeriesDatabase")


class TimeSeriesDatabaseError(RuntimeError):
    """Raised when the DuckDB store cannot be opened in the required mode."""


_INSTANCES: dict[str, TimeSeriesDatabase] = {}
_REGISTRY_LOCK = threading.Lock()


class TimeSeriesDatabase:
    """Single-process, connection-shared DuckDB time-series store.

    Construction is idempotent per absolute database path: repeated calls return
    the same instance so the file is only ever opened once per process.
    """

    db_path: str
    read_only: bool
    conn: duckdb.DuckDBPyConnection | None

    def __new__(
        cls,
        db_path: str = "data/trading_agent.duckdb",
        read_only: bool = False,
        *,
        max_retries: int = 5,
        retry_delay: float = 0.5,
    ) -> Self:
        key = cls._instance_key(db_path)
        with _REGISTRY_LOCK:
            instance = _INSTANCES.get(key)
            if instance is None:
                instance = super().__new__(cls)
                _INSTANCES[key] = instance
            return cast(Self, instance)

    def __init__(
        self,
        db_path: str = "data/trading_agent.duckdb",
        read_only: bool = False,
        *,
        max_retries: int = 5,
        retry_delay: float = 0.5,
    ) -> None:
        if getattr(self, "_initialized", False):
            if read_only != self.read_only:
                logger.warning(
                    "DuckDB for %s is already open (read_only=%s); ignoring requested read_only=%s.",
                    self.db_path,
                    self.read_only,
                    read_only,
                )
            return

        self.db_path = db_path
        self.read_only = read_only or db_path == ":memory:"
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._query_lock = threading.Lock()
        self.conn: duckdb.DuckDBPyConnection | None = None

        if db_path != ":memory:":
            parent = os.path.dirname(os.path.abspath(db_path))
            os.makedirs(parent, exist_ok=True)

        self.conn = self._connect()
        self._initialized = True

        if not self.read_only:
            self._init_schema()

    @staticmethod
    def _instance_key(db_path: str) -> str:
        return db_path if db_path == ":memory:" else os.path.abspath(db_path)

    def _connect(self) -> duckdb.DuckDBPyConnection:
        """Open the database, retrying lock contention and degrading to read-only.

        Raises ``TimeSeriesDatabaseError`` rather than silently falling back to
        an in-memory database, which would hide the failure and split the data.
        """
        if self.db_path == ":memory:":
            return duckdb.connect(":memory:")

        if not self.read_only:
            conn = self._open_with_retry(read_only=False)
            if conn is not None:
                return conn
            logger.warning(
                "Could not obtain the DuckDB write lock on %s (held by another process); "
                "opening read-only. Writes will be skipped until this process owns the lock.",
                self.db_path,
            )
            self.read_only = True

        if not os.path.exists(self.db_path):
            raise TimeSeriesDatabaseError(
                f"DuckDB file {self.db_path} does not exist and cannot be created in read-only mode."
            )

        conn = self._open_with_retry(read_only=True)
        if conn is None:
            raise TimeSeriesDatabaseError(f"Unable to open DuckDB database {self.db_path} in read-only mode.")
        return conn

    def _open_with_retry(self, read_only: bool) -> duckdb.DuckDBPyConnection | None:
        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                conn = duckdb.connect(self.db_path, read_only=read_only)
                conn.execute("SET TimeZone='UTC'")
                return conn
            except Exception as e:  # duckdb raises plain IOError on lock contention
                last_error = e
                logger.warning(
                    "DuckDB open attempt %d/%d (%s) on %s failed: %s",
                    attempt,
                    self._max_retries,
                    "read-only" if read_only else "read-write",
                    self.db_path,
                    e,
                )
                if attempt < self._max_retries:
                    time.sleep(self._retry_delay * attempt)
        logger.error("Giving up opening %s after %d attempts: %s", self.db_path, self._max_retries, last_error)
        return None

    def _init_schema(self) -> None:
        if not self.conn or self.read_only:
            return
        try:
            with self._query_lock:
                self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS candles (
                        symbol VARCHAR,
                        asset_class VARCHAR,
                        timestamp TIMESTAMP WITH TIME ZONE,
                        open DOUBLE,
                        high DOUBLE,
                        low DOUBLE,
                        close DOUBLE,
                        volume DOUBLE,
                        exchange VARCHAR,
                        PRIMARY KEY (symbol, timestamp, exchange)
                    );
                """)

                self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS trades (
                        symbol VARCHAR,
                        timestamp TIMESTAMP WITH TIME ZONE,
                        price DOUBLE,
                        size DOUBLE,
                        side VARCHAR,
                        exchange VARCHAR,
                        trade_id VARCHAR
                    );
                """)

                self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS news (
                        id VARCHAR PRIMARY KEY,
                        source VARCHAR,
                        headline VARCHAR,
                        url VARCHAR,
                        published_at TIMESTAMP WITH TIME ZONE,
                        sentiment_score DOUBLE
                    );
                """)

                self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS feature_store (
                        symbol VARCHAR,
                        timestamp TIMESTAMP WITH TIME ZONE,
                        feature_name VARCHAR,
                        feature_value DOUBLE,
                        PRIMARY KEY (symbol, timestamp, feature_name)
                    );
                """)
        except Exception:
            logger.exception("Schema initialization failed on %s", self.db_path)

    def insert_candles(self, candles: Sequence[Candle]) -> int:
        """Persist candles, returning the number of rows written (0 if read-only)."""
        if not candles or not self.conn:
            return 0
        if self.read_only:
            logger.debug("DuckDB is read-only; skipping candle insert for %d candles.", len(candles))
            return 0

        try:
            df = pd.DataFrame(
                [
                    {
                        "symbol": c.symbol,
                        "asset_class": c.asset_class.value,
                        "timestamp": c.timestamp,
                        "open": c.open,
                        "high": c.high,
                        "low": c.low,
                        "close": c.close,
                        "volume": c.volume,
                        "exchange": c.exchange,
                    }
                    for c in candles
                ]
            )
            with self._query_lock:
                self.conn.register("df_candles", df)
                try:
                    self.conn.execute("INSERT OR REPLACE INTO candles SELECT * FROM df_candles;")
                finally:
                    self.conn.unregister("df_candles")
            return len(df)
        except Exception:
            logger.exception("Failed to insert candles into DuckDB")
            return 0

    def fetch_candles(self, symbol: str, start: datetime, end: datetime) -> list[Candle]:
        if not self.conn:
            return []
        try:
            query = """
                SELECT symbol, asset_class, timestamp, open, high, low, close, volume, exchange
                FROM candles
                WHERE symbol = ? AND timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp ASC;
            """
            with self._query_lock:
                res = self.conn.execute(query, [symbol, start, end]).fetchall()
            return [
                Candle(
                    symbol=row[0],
                    asset_class=AssetClass(row[1]),
                    timestamp=row[2].replace(tzinfo=UTC) if row[2].tzinfo is None else row[2],
                    open=row[3],
                    high=row[4],
                    low=row[5],
                    close=row[6],
                    volume=row[7],
                    exchange=row[8],
                )
                for row in res
            ]
        except Exception:
            logger.exception("Error fetching candles from DuckDB")
            return []

    def close(self) -> None:
        with _REGISTRY_LOCK:
            if self.conn:
                try:
                    with self._query_lock:
                        self.conn.close()
                except Exception:
                    logger.exception("Error closing DuckDB connection")
                finally:
                    self.conn = None
            _INSTANCES.pop(self._instance_key(self.db_path), None)
            self._initialized = False
