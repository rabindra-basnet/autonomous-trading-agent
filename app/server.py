"""Production FastAPI backend application and WebSocket server with DuckDB & PostgreSQL."""

import asyncio
import json
from collections.abc import Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import settings
from app.core.logging import get_logger
from app.core.models import Candle, MacroIndicator, NewsItem, SocialMetric
from app.core.redis_bus import RedisStreamEventBus
from app.execution.oms import OrderManagementSystem
from app.execution.paper_trader import PaperTradingEngine
from app.execution.risk_manager import RiskManager
from app.features.pipeline import FeaturePipeline
from app.ingestion.macro.fred_provider import FREDMacroProvider
from app.ingestion.market.global_provider import GlobalMarketDataProvider
from app.ingestion.news.gdelt_provider import GDELTNewsProvider
from app.ingestion.onchain.defillama_provider import DefiLlamaProvider
from app.ingestion.social.reddit_provider import RedditSocialProvider
from app.research.agent_graph import TradingState, TradingWorkflowGraph
from app.research.backtest import BacktestEngine
from app.research.multi_agent import MultiAgentConsensus, MultiAgentTradingDesk
from app.research.researcher import AutonomousResearcher
from app.storage.database import TimeSeriesDatabase
from app.storage.feature_store import PointInTimeFeatureStore
from app.storage.postgres import PostgresStorage
from app.strategies.momentum import MomentumTrendStrategy
from app.strategies.sentiment_momentum import SentimentMomentumStrategy
from app.symbol_service import symbol_catalog_sync_job

logger = get_logger("BackendServer")

# Core system state
postgres_storage = PostgresStorage()
duckdb_storage = TimeSeriesDatabase(db_path=settings.duckdb_path)
feature_store = PointInTimeFeatureStore()
feature_pipeline = FeaturePipeline()
risk_manager = RiskManager()
oms = OrderManagementSystem()
paper_trader = PaperTradingEngine(initial_cash=100000.0)
event_bus = RedisStreamEventBus()

# In-memory streaming state; trading symbols are loaded from the DB each cycle
symbols: list[str] = []
candle_buffers: dict[str, list[Candle]] = {}
active_strategies: list = []
active_websockets: list[WebSocket] = []
_ingestion_task: asyncio.Task | None = None


def _rebuild_strategies() -> None:
    """Rebuild strategy instances and candle buffers when the symbol set changes."""
    global active_strategies
    for s in symbols:
        candle_buffers.setdefault(s, [])
    for stale in [s for s in candle_buffers if s not in symbols]:
        del candle_buffers[stale]
    active_strategies = [
        MomentumTrendStrategy(symbols=symbols),
        SentimentMomentumStrategy(symbols=symbols),
    ]


async def broadcast_ws(message: dict[str, Any]):
    for ws in active_websockets:
        try:
            await ws.send_json(message)
        except Exception:
            logger.warning("Failed to broadcast to websocket; removing it", exc_info=True)
            active_websockets.remove(ws)


async def _process_symbol(
    market_prov: GlobalMarketDataProvider,
    sym: str,
    now: datetime,
    news: Sequence[NewsItem],
    social: Sequence[SocialMetric],
    macro: Sequence[MacroIndicator],
) -> None:
    """Process one symbol end-to-end. Failures inside are isolated to this symbol."""
    price = await market_prov.fetch_ticker_price(sym)
    candle = Candle(
        symbol=sym,
        timestamp=now,
        open=price * 0.999,
        high=price * 1.002,
        low=price * 0.998,
        close=price,
        volume=200.0,
        exchange="binance",
    )
    candle_buffers[sym].append(candle)
    if len(candle_buffers[sym]) > 300:
        candle_buffers[sym] = candle_buffers[sym][-300:]

    # 2. Store in DuckDB TimeSeries Lake
    duckdb_storage.insert_candles([candle])

    # 3. Compute point-in-time feature vector (on-chain metrics are fetched on demand only)
    feat_vec = feature_pipeline.compute_features(
        symbol=sym,
        candles=candle_buffers[sym],
        news=news,
        social=social,
        macro=macro,
    )
    feature_store.put_features(feat_vec)

    # 4. Evaluate Strategies
    current_prices = {s: candle_buffers[s][-1].close for s in symbols if candle_buffers[s]}
    portfolio = paper_trader.get_portfolio_state(current_prices)

    for strat in active_strategies:
        signals = strat.generate_signals(feat_vec, portfolio)
        for sig in signals:
            # 5. Pre-Trade Risk Gate
            risk_res = risk_manager.validate_signal(sig, portfolio, price)
            if risk_res.approved:
                order = oms.create_order_from_signal(sig, risk_res, price)
                if order:
                    filled = await paper_trader.execute_order(order, price)
                    await postgres_storage.save_order(filled)
                    await broadcast_ws(
                        {
                            "type": "order_filled",
                            "data": filled.model_dump(mode="json"),
                        }
                    )

    # Broadcast live tick to WebSockets
    await broadcast_ws(
        {
            "type": "market_tick",
            "symbol": sym,
            "price": price,
            "timestamp": now.isoformat(),
            "features": feat_vec.features,
        }
    )


async def background_ingestion_and_trading_loop():
    """Continuous async worker streaming real-time market data, computing features, running strategies & OMS."""
    global symbols
    news_prov = GDELTNewsProvider()
    social_prov = RedditSocialProvider()
    macro_prov = FREDMacroProvider()

    async with GlobalMarketDataProvider() as market_prov:
        while True:
            try:
                # Refresh symbols from DB each cycle so new symbols are picked up dynamically
                db_symbols = await postgres_storage.get_active_symbols()
                if db_symbols != symbols:
                    symbols = db_symbols
                    _rebuild_strategies()
                    logger.info("Symbols refreshed from DB: %s", ", ".join(symbols))
                if not symbols:
                    await asyncio.sleep(5.0)
                    continue

                # 1. Fetch & normalize multi-source feeds
                now = datetime.now(UTC)
                news = await news_prov.fetch_latest_news(limit=5)
                social = await social_prov.fetch_metrics(symbols)
                macro = await macro_prov.fetch_indicator("FEDFUNDS", now - timedelta(days=30))

                for sym in symbols:
                    try:
                        await _process_symbol(market_prov, sym, now, news, social, macro)
                    except Exception:
                        logger.exception("Skipping symbol %s after processing error", sym)

                await asyncio.sleep(2.0)
            except Exception:
                logger.exception("Unexpected error in ingestion & trading loop")
                await asyncio.sleep(2.0)


async def start_ingestion() -> bool:
    """Start the ingestion & trading loop if it is not already running.

    Returns True when a new task was started, False when it was already active.
    """
    global _ingestion_task
    if _ingestion_task is not None and not _ingestion_task.done():
        return False
    _ingestion_task = asyncio.create_task(background_ingestion_and_trading_loop())
    logger.info("Ingestion & trading loop started by trigger")
    return True


async def stop_ingestion() -> bool:
    """Cancel the ingestion & trading loop and release its provider sessions."""
    global _ingestion_task
    if _ingestion_task is None:
        return False
    _ingestion_task.cancel()
    try:
        await _ingestion_task
    except asyncio.CancelledError:
        pass
    _ingestion_task = None
    logger.info("Ingestion & trading loop stopped")
    return True


def ingestion_is_running() -> bool:
    return _ingestion_task is not None and not _ingestion_task.done()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: load state and sync the symbol catalog, but do NOT start the
    # ingestion/trading loop. External feeds and trading are trigger-driven;
    # the frontend or a websocket client must call /api/ingestion/start.
    global symbols
    await postgres_storage.init_db()
    await event_bus.start()
    symbols = await postgres_storage.get_active_symbols()
    _rebuild_strategies()
    if symbols:
        logger.info("Loaded %d trading symbols from DB: %s", len(symbols), ", ".join(symbols))
    else:
        logger.warning("No active symbols in DB. Add rows to the 'symbols' table to start ingestion.")
    logger.info("Ingestion idle. Call POST /api/ingestion/start or send {'action':'start'} over /ws/live.")
    sync_task = asyncio.create_task(symbol_catalog_sync_job(postgres_storage))
    yield
    # Shutdown
    await stop_ingestion()
    sync_task.cancel()
    try:
        await sync_task
    except asyncio.CancelledError:
        pass
    await event_bus.stop()
    duckdb_storage.close()


app = FastAPI(
    title="AutoQuant-AI Backend",
    description="Multi-Source Quantitative Trading & AI Research Server with DuckDB & PostgreSQL",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now(UTC).isoformat(),
        "postgres": "connected" if postgres_storage.engine else "disconnected",
        "duckdb": "connected" if duckdb_storage.conn else "disconnected",
        "redis_bus": "connected" if event_bus._redis else "disconnected",
    }


@app.get("/api/portfolio")
async def get_portfolio():
    prices = {s: candle_buffers[s][-1].close for s in symbols if candle_buffers[s]}
    return paper_trader.get_portfolio_state(prices).model_dump(mode="json")


@app.get("/api/orders")
async def get_orders(limit: int = 50):
    return await postgres_storage.get_orders(limit=limit)


@app.get("/api/llm/usage")
async def get_llm_usage(limit: int = 100):
    """Return recent LLM token usage & cost rows from the llm_usage table."""
    return {"usage": await postgres_storage.get_llm_usage_summary(limit=limit)}


class BacktestRequest(BaseModel):
    symbol: str = "BTC/USDT"
    days: int = 30
    strategy: str = "sentiment_momentum"


@app.post("/api/backtest")
async def run_backtest(req: BacktestRequest):
    end = datetime.now(UTC)
    start = end - timedelta(days=req.days)
    async with GlobalMarketDataProvider() as market_prov:
        candles = await market_prov.fetch_historical_candles(req.symbol, "1h", start, end)

    strat = (
        SentimentMomentumStrategy(symbols=[req.symbol])
        if req.strategy == "sentiment_momentum"
        else MomentumTrendStrategy(symbols=[req.symbol])
    )
    engine = BacktestEngine(initial_capital=100000.0)
    result = engine.run(strat, req.symbol, candles)
    return result.model_dump(mode="json")


@app.post("/api/research/run")
async def run_research_loop(symbol: str = "BTC/USDT"):
    async def _research_task():
        end = datetime.now(UTC)
        start = end - timedelta(days=60)
        async with GlobalMarketDataProvider() as market_prov:
            candles = await market_prov.fetch_historical_candles(symbol, "1h", start, end)

        researcher = AutonomousResearcher()
        records = await researcher.run_experiment_loop(symbol, candles)
        for r in records:
            await postgres_storage.save_experiment(r)

    asyncio.create_task(_research_task())

    return {"message": "AI Research & Strategy Evolution cycle started in background."}


@app.get("/api/symbols")
async def list_symbols():
    rows = await postgres_storage.get_active_symbols()
    return {"symbols": rows}


@app.get("/api/market/index")
async def get_market_index(symbol: str | None = None, quote: str = "USDT", limit: int = 100):
    """Inspect the global market holder: per-exchange counts, or full routing details.

    Query params: symbol (single symbol lookup), quote (USDT/USDC/USD), limit.
    """
    async with GlobalMarketDataProvider() as prov:
        await prov._ensure_init()

        if symbol:
            routes = prov.routes_for(symbol)
            return {"symbol": symbol, "routes": routes}

        details = [
            {
                "symbol": s,
                "best_exchange": candidates[0]["exchange"],
                "exchanges": [c["exchange"] for c in candidates],
            }
            for s, candidates in prov._symbol_index.items()
            if s.split("/")[1] == quote
        ][:limit]

        return {
            **prov.index_summary(),
            "quote": quote,
            "sample_symbols": details,
            "sample_size": len(details),
        }


@app.get("/api/market/routes")
async def get_market_routes(symbol: str = "BTC/USDT"):
    """Show which exchanges list a symbol, best-first by routing criteria."""
    async with GlobalMarketDataProvider() as prov:
        await prov._ensure_init()
        routes = prov.routes_for(symbol)
        if not routes:
            raise HTTPException(
                status_code=404,
                detail=f"Symbol {symbol} is not listed on any configured exchange {prov.exchange_ids}.",
            )
        return {"symbol": symbol, "routes": routes}


class SymbolRequest(BaseModel):
    symbol: str
    asset_class: str = "crypto"
    category: str = "spot"
    timeframe: str = "1h"


@app.get("/api/symbols/catalog")
async def get_symbol_catalog(limit: int = 200):
    """Return the full symbol catalog from the DB, including asset category."""
    rows = await postgres_storage.get_symbol_catalog(limit=limit)
    return {"symbols": rows}


@app.post("/api/symbols")
async def add_symbol(req: SymbolRequest):
    await postgres_storage.upsert_symbol(req.symbol, asset_class=req.asset_class, timeframe=req.timeframe)
    return {"symbol": req.symbol, "status": "active", "category": req.category}


@app.delete("/api/symbols")
async def remove_symbol(symbol: str):
    await postgres_storage.deactivate_symbol(symbol)
    return {"symbol": symbol, "status": "inactive"}


@app.get("/api/onchain/{symbol}")
async def get_onchain_metrics(symbol: str):
    """Fetch on-chain TVL metrics on demand. Only symbols with a mapped chain return data."""
    async with DefiLlamaProvider() as prov:
        metrics = await prov.fetch_metrics(symbol)
    return {"symbol": symbol, "metrics": [m.model_dump(mode="json") for m in metrics]}


@app.get("/api/ingestion/status")
async def ingestion_status():
    return {"running": ingestion_is_running()}


@app.post("/api/ingestion/start")
async def ingestion_start():
    started = await start_ingestion()
    return {"running": True, "already_running": not started}


@app.post("/api/ingestion/stop")
async def ingestion_stop():
    stopped = await stop_ingestion()
    return {"running": False, "was_running": stopped}


@app.get("/api/agents/consensus", response_model=MultiAgentConsensus)
async def get_multi_agent_consensus(symbol: str = "BTC/USDT"):
    desk = MultiAgentTradingDesk()
    latest_feat = feature_store.get_latest_features(symbol)
    market_context = {
        "symbol": symbol,
        "features": latest_feat.features if latest_feat else {},
        "current_price": candle_buffers[symbol][-1].close if candle_buffers[symbol] else 0.0,
    }
    return await desk.evaluate_market(market_context)


@app.get("/api/graphs/workflow", response_model=TradingState)
async def execute_multi_agent_graph(symbol: str = "BTC/USDT"):
    """Execute the multi-agent StateGraph workflow and return state trace."""
    workflow = TradingWorkflowGraph()
    latest_feat = feature_store.get_latest_features(symbol)
    price = candle_buffers[symbol][-1].close if candle_buffers[symbol] else 0.0
    return await workflow.execute_graph(symbol, price, latest_feat.features if latest_feat else {})


@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            action = msg.get("action") if isinstance(msg, dict) else None
            if action == "start":
                started = await start_ingestion()
                await websocket.send_json({"type": "ingestion", "running": True, "started": started})
            elif action == "stop":
                stopped = await stop_ingestion()
                await websocket.send_json({"type": "ingestion", "running": False, "stopped": stopped})
            elif action == "status":
                await websocket.send_json({"type": "ingestion", "running": ingestion_is_running()})
    except WebSocketDisconnect:
        active_websockets.remove(websocket)
