"""Time-series analytical storage engine using DuckDB."""

from datetime import datetime, timezone
import os
from typing import List, Optional, Sequence
import duckdb
import pandas as pd
from app.core.models import Candle, TradeEvent, NewsItem, FeatureVector


class TimeSeriesDatabase:
    def __init__(self, db_path: str = "data/trading_agent.duckdb"):
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self.db_path = db_path
        self.conn = duckdb.connect(db_path)
        self._init_schema()

    def _init_schema(self) -> None:
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

    def insert_candles(self, candles: Sequence[Candle]) -> None:
        if not candles:
            return
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

    def fetch_candles(
        self, symbol: str, start: datetime, end: datetime
    ) -> List[Candle]:
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

    def close(self) -> None:
        self.conn.close()
