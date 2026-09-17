"""Time-series analytical storage engine using DuckDB with multi-process concurrency support."""

from datetime import datetime, timezone
import os
import logging
from typing import List, Optional, Sequence
import duckdb
import pandas as pd
from app.core.models import Candle, TradeEvent, NewsItem, FeatureVector

logger = logging.getLogger("TimeSeriesDatabase")


class TimeSeriesDatabase:
    def __init__(self, db_path: str = "data/trading_agent.duckdb", read_only: bool = False):
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self.db_path = db_path
        self.read_only = read_only
        self.conn = None
        self._connect()
        if not self.read_only:
            self._init_schema()

    def _connect(self) -> None:
        """Connect to DuckDB with graceful fallback if the database file is locked by another process."""
        try:
            self.conn = duckdb.connect(self.db_path, read_only=self.read_only)
        except Exception as e:
            logger.warning(f"Could not open DuckDB in {'read-only' if self.read_only else 'read-write'} mode: {e}. Attempting read-only shared access.")
            try:
                self.read_only = True
                self.conn = duckdb.connect(self.db_path, read_only=True)
            except Exception as e2:
                logger.warning(f"Shared access failed ({e2}). Using in-memory fallback database.")
                self.read_only = False
                self.conn = duckdb.connect(":memory:")

    def _init_schema(self) -> None:
        if not self.conn or self.read_only:
            return
        try:
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
        except Exception as e:
            logger.warning(f"Schema initialization note: {e}")

    def insert_candles(self, candles: Sequence[Candle]) -> None:
        if not candles or not self.conn:
            return
        if self.read_only:
            logger.debug("Database in read-only mode; skipping candle insert.")
            return

        try:
            df = pd.DataFrame([
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
            ])
            self.conn.register("df_candles", df)
            self.conn.execute("""
                INSERT OR REPLACE INTO candles 
                SELECT * FROM df_candles;
            """)
            self.conn.unregister("df_candles")
        except Exception as e:
            logger.warning(f"Failed to insert candles into DuckDB: {e}")

    def fetch_candles(
        self, symbol: str, start: datetime, end: datetime
    ) -> List[Candle]:
        if not self.conn:
            return []
        try:
            query = """
                SELECT symbol, asset_class, timestamp, open, high, low, close, volume, exchange
                FROM candles
                WHERE symbol = ? AND timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp ASC;
            """
            res = self.conn.execute(query, [symbol, start, end]).fetchall()
            from app.core.models import AssetClass
            return [
                Candle(
                    symbol=row[0],
                    asset_class=AssetClass(row[1]),
                    timestamp=row[2].replace(tzinfo=timezone.utc) if row[2].tzinfo is None else row[2],
                    open=row[3],
                    high=row[4],
                    low=row[5],
                    close=row[6],
                    volume=row[7],
                    exchange=row[8],
                )
                for row in res
            ]
        except Exception as e:
            logger.warning(f"Error fetching candles from DuckDB: {e}")
            return []

    def close(self) -> None:
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
