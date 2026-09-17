"""ClickHouse Cloud high-speed analytical storage engine."""

import logging
from datetime import datetime, timezone
from typing import List, Sequence, Dict, Any, Optional
import clickhouse_connect
from app.config import settings
from app.core.models import Candle, TradeEvent, FeatureVector

logger = logging.getLogger("ClickHouseStorage")


class ClickHouseStorage:
    def __init__(self):
        self.client = None
        self._connect()
        self._init_tables()

    def _connect(self):
        try:
            self.client = clickhouse_connect.get_client(
                host=settings.clickhouse_host,
                port=settings.clickhouse_port,
                username=settings.clickhouse_user,
                password=settings.clickhouse_password,
                database=settings.clickhouse_database,
                secure=settings.clickhouse_secure,
                connect_timeout=5,
                send_receive_timeout=5,
            )
            logger.info("Connected successfully to ClickHouse Cloud.")
        except Exception as e:
            logger.warning(f"Could not connect to ClickHouse Cloud ({e}). Local fallback will be used.")
            self.client = None

    def _init_tables(self):
        if not self.client:
            return

        # Candles table with ReplacingMergeTree for automatic deduplication by symbol & timestamp
        self.client.command("""
            CREATE TABLE IF NOT EXISTS market_candles (
                symbol LowCardinality(String),
                asset_class LowCardinality(String),
                timestamp DateTime64(3, 'UTC'),
                open Float64,
                high Float64,
                low Float64,
                close Float64,
                volume Float64,
                exchange LowCardinality(String)
            ) ENGINE = ReplacingMergeTree()
            ORDER BY (symbol, exchange, timestamp);
        """)

        # Trades tick table
        self.client.command("""
            CREATE TABLE IF NOT EXISTS market_trades (
                symbol LowCardinality(String),
                timestamp DateTime64(3, 'UTC'),
                price Float64,
                size Float64,
                side LowCardinality(String),
                exchange LowCardinality(String),
                trade_id String
            ) ENGINE = MergeTree()
            ORDER BY (symbol, timestamp);
        """)

        # Point-in-time Features table
        self.client.command("""
            CREATE TABLE IF NOT EXISTS point_in_time_features (
                symbol LowCardinality(String),
                timestamp DateTime64(3, 'UTC'),
                feature_name LowCardinality(String),
                feature_value Float64
            ) ENGINE = ReplacingMergeTree()
            ORDER BY (symbol, feature_name, timestamp);
        """)

    def insert_candles(self, candles: Sequence[Candle]):
        if not self.client or not candles:
            return
        data = [
            [
                c.symbol,
                c.asset_class.value,
                c.timestamp,
                c.open,
                c.high,
                c.low,
                c.close,
                c.volume,
                c.exchange,
            ]
            for c in candles
        ]
        self.client.insert(
            "market_candles",
            data,
            column_names=["symbol", "asset_class", "timestamp", "open", "high", "low", "close", "volume", "exchange"],
        )

    def fetch_candles(self, symbol: str, start: datetime, end: datetime) -> List[Candle]:
        if not self.client:
            return []
        query = """
            SELECT symbol, asset_class, timestamp, open, high, low, close, volume, exchange
            FROM market_candles
            WHERE symbol = %(symbol)s AND timestamp >= %(start)s AND timestamp <= %(end)s
            ORDER BY timestamp ASC;
        """
        result = self.client.query(query, parameters={"symbol": symbol, "start": start, "end": end})
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
            for row in result.result_rows
        ]
