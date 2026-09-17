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
from app.research.agent_graph import TradingWorkflowGraph, TradingState
from app.features.charting import ChartGenerator
from app.ingestion.market.simulated import SimulatedMarketDataProvider
from app.core.symbol_manager import SymbolManager, SymbolInfo
from app.core.logging import get_logger

logger = get_logger("BackendServer")

# Core system state
symbol_manager = SymbolManager()
postgres_storage = PostgresStorage()
duckdb_storage = TimeSeriesDatabase(db_path=settings.duckdb_path)
feature_store = PointInTimeFeatureStore()
feature_pipeline = FeaturePipeline()
risk_manager = RiskManager()
oms = OrderManagementSystem()
paper_trader = PaperTradingEngine(initial_cash=100000.0)
event_bus = RedisStreamEventBus()

# In-memory streaming state driven by dynamic SymbolManager
candle_buffers: Dict[str, List[Candle]] = {s: [] for s in symbol_manager.get_active_symbols()}
active_strategies = [
    MomentumTrendStrategy(symbols=symbol_manager.get_active_symbols()),
    SentimentMomentumStrategy(symbols=symbol_manager.get_active_symbols()),
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
            current_symbols = symbol_manager.get_active_symbols()
            now = datetime.now(timezone.utc)
            news = await news_prov.fetch_latest_news(limit=5)
            social = await social_prov.fetch_metrics(current_symbols)
            macro = await macro_prov.fetch_indicator("FEDFUNDS", now - timedelta(days=30))

            for sym in current_symbols:
                if sym not in candle_buffers:
                    candle_buffers[sym] = []

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
                current_prices = {s: candle_buffers[s][-1].close for s in current_symbols if candle_buffers.get(s)}
                portfolio = paper_trader.get_portfolio_state(current_prices)

                for strat in active_strategies:
                    strat.symbols = current_symbols
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


class AddSymbolsRequest(BaseModel):
    symbols: List[str]


@app.get("/api/symbols", response_model=List[SymbolInfo])
async def get_active_symbols():
    """Retrieve all actively tracked and traded asset pairs."""
    return symbol_manager.get_symbol_details()


@app.post("/api/symbols")
async def add_trading_symbols(req: AddSymbolsRequest):
    """Dynamically register new trading pairs to the multi-agent system."""
    added = symbol_manager.add_symbols(req.symbols)
    # Broadcast dynamic symbol update to all connected WebSocket clients & event bus
    await broadcast_ws({
        "type": "symbols_updated",
        "action": "added",
        "active_symbols": symbol_manager.get_active_symbols(),
    })
    return {
        "message": f"Successfully registered {len(added)} symbol(s).",
        "added_symbols": added,
        "active_symbols": symbol_manager.get_active_symbols(),
    }


@app.delete("/api/symbols/{symbol:path}")
async def remove_trading_symbol(symbol: str):
    """Deactivate and remove a trading pair from active ingestion and trading."""
    removed = symbol_manager.remove_symbol(symbol)
    if not removed:
        return {"message": f"Symbol '{symbol}' was not in the active registry.", "active_symbols": symbol_manager.get_active_symbols()}

    await broadcast_ws({
        "type": "symbols_updated",
        "action": "removed",
        "active_symbols": symbol_manager.get_active_symbols(),
    })
    return {
        "message": f"Successfully removed '{symbol}' from active trading.",
        "active_symbols": symbol_manager.get_active_symbols(),
    }


@app.get("/api/portfolio")
async def get_portfolio():
    current_symbols = symbol_manager.get_active_symbols()
    prices = {s: candle_buffers[s][-1].close for s in current_symbols if candle_buffers.get(s)}
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


@app.get("/api/graphs/workflow", response_model=TradingState)
async def execute_multi_agent_graph(symbol: str = "BTC/USDT"):
    """Execute the multi-agent StateGraph workflow and return state trace."""
    workflow = TradingWorkflowGraph()
    latest_feat = feature_store.get_latest_features(symbol)
    price = candle_buffers[symbol][-1].close if candle_buffers[symbol] else 0.0
    return await workflow.execute_graph(symbol, price, latest_feat.features if latest_feat else {})


@app.get("/api/graphs/candles")
async def get_candle_chart_data(symbol: str = "BTC/USDT"):
    """Return OHLCV data formatted for frontend candlestick charts."""
    candles = candle_buffers.get(symbol, [])
    return ChartGenerator.generate_candle_chart_data(candles)


@app.get("/api/graphs/equity")
async def get_equity_chart(symbol: str = "BTC/USDT", days: int = 30):
    """Return equity curve data and base64 rendered PNG chart."""
    market_prov = SimulatedMarketDataProvider(seed=42)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    candles = await market_prov.fetch_historical_candles(symbol, "1h", start, end)

    strat = SentimentMomentumStrategy(symbols=[symbol])
    engine = BacktestEngine(initial_capital=100000.0)
    result = engine.run(strat, symbol, candles)

    curve_data = ChartGenerator.generate_equity_curve_data(result.equity_curve)
    image_b64 = ChartGenerator.render_equity_chart_image(result)

    return {
        "metrics": {
            "total_return_pct": result.total_return_pct,
            "sharpe_ratio": result.sharpe_ratio,
            "max_drawdown_pct": result.max_drawdown_pct,
            "win_rate_pct": result.win_rate_pct,
        },
        "chart_data": curve_data,
        "chart_image_base64": image_b64,
    }


@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_websockets.remove(websocket)
