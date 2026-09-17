"""Production FastAPI backend application and WebSocket server with DuckDB & PostgreSQL."""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import settings
from app.core.events import Event, EventTopic
from app.core.models import Candle, TradingSignal
from app.core.redis_bus import RedisStreamEventBus
from app.storage.postgres import PostgresStorage
from app.storage.database import TimeSeriesDatabase
from app.storage.feature_store import PointInTimeFeatureStore
from app.features.pipeline import FeaturePipeline
from app.execution.risk_manager import RiskManager
from app.execution.oms import OrderManagementSystem
from app.execution.paper_trader import PaperTradingEngine
from app.strategies.momentum import MomentumTrendStrategy
from app.strategies.sentiment_momentum import SentimentMomentumStrategy
from app.research.researcher import AutonomousResearcher
from app.research.backtest import BacktestEngine
from app.research.multi_agent import MultiAgentTradingDesk, MultiAgentConsensus
from app.ingestion.market.simulated import SimulatedMarketDataProvider
from app.ingestion.news.simulated import SimulatedNewsProvider
from app.ingestion.social.simulated import SimulatedSocialProvider
from app.ingestion.macro.simulated import SimulatedMacroProvider
from app.ingestion.onchain.simulated import SimulatedOnChainProvider

# Core system state
postgres_storage = PostgresStorage()
duckdb_storage = TimeSeriesDatabase(db_path=settings.duckdb_path)
feature_store = PointInTimeFeatureStore()
feature_pipeline = FeaturePipeline()
risk_manager = RiskManager()
oms = OrderManagementSystem()
paper_trader = PaperTradingEngine(initial_cash=100000.0)
event_bus = RedisStreamEventBus()

# In-memory streaming state
symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
candle_buffers: Dict[str, List[Candle]] = {s: [] for s in symbols}
active_strategies = [
    MomentumTrendStrategy(symbols=symbols),
    SentimentMomentumStrategy(symbols=symbols),
]

active_websockets: List[WebSocket] = []


async def broadcast_ws(message: Dict[str, Any]):
    for ws in active_websockets:
        try:
            await ws.send_json(message)
        except Exception:
            pass


async def background_ingestion_and_trading_loop():
    """Continuous async worker streaming real-time market data, computing features, running strategies & OMS."""
    market_prov = SimulatedMarketDataProvider(seed=42)
    news_prov = SimulatedNewsProvider()
    social_prov = SimulatedSocialProvider()
    macro_prov = SimulatedMacroProvider()
    onchain_prov = SimulatedOnChainProvider()

    while True:
        try:
            # 1. Fetch & normalize multi-source feeds
            now = datetime.now(timezone.utc)
            news = await news_prov.fetch_latest_news(limit=5)
            social = await social_prov.fetch_metrics(symbols)
            macro = await macro_prov.fetch_indicator("FEDFUNDS", now - timedelta(days=30))
            
            for sym in symbols:
                price = await market_prov.fetch_ticker_price(sym)
                candle = Candle(
                    symbol=sym,
                    timestamp=now,
                    open=price * 0.999,
                    high=price * 1.002,
                    low=price * 0.998,
                    close=price,
                    volume=200.0,
                    exchange="backend_sim",
                )
                candle_buffers[sym].append(candle)
                if len(candle_buffers[sym]) > 300:
                    candle_buffers[sym] = candle_buffers[sym][-300:]

                # 2. Store in DuckDB TimeSeries Lake
                duckdb_storage.insert_candles([candle])

                # 3. Compute point-in-time feature vector
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
                                await broadcast_ws({
                                    "type": "order_filled",
                                    "data": filled.model_dump(mode="json"),
                                })

                # Broadcast live tick to WebSockets
                await broadcast_ws({
                    "type": "market_tick",
                    "symbol": sym,
                    "price": price,
                    "timestamp": now.isoformat(),
                    "features": feat_vec.features,
                })

            await asyncio.sleep(2.0)
        except Exception as e:
            await asyncio.sleep(2.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await postgres_storage.init_db()
    await event_bus.start()
    task = asyncio.create_task(background_ingestion_and_trading_loop())
    yield
    # Shutdown
    task.cancel()
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
        "timestamp": datetime.now(timezone.utc).isoformat(),
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


class BacktestRequest(BaseModel):
    symbol: str = "BTC/USDT"
    days: int = 30
    strategy: str = "sentiment_momentum"


@app.post("/api/backtest")
async def run_backtest(req: BacktestRequest):
    market_prov = SimulatedMarketDataProvider(seed=42)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=req.days)
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
async def run_research_loop(symbol: str = "BTC/USDT", background_tasks: BackgroundTasks = None):
    async def _research_task():
        market_prov = SimulatedMarketDataProvider(seed=101)
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=60)
        candles = await market_prov.fetch_historical_candles(symbol, "1h", start, end)

        researcher = AutonomousResearcher()
        records = await researcher.run_experiment_loop(symbol, candles)
        for r in records:
            await postgres_storage.save_experiment(r)

    if background_tasks:
        background_tasks.add_task(_research_task)
    else:
        asyncio.create_task(_research_task())

    return {"message": "AI Research & Strategy Evolution cycle started in background."}


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


@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_websockets.remove(websocket)
