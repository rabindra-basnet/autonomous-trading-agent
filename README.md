# Autonomous AI Quantitative Trading Agent

A provider-agnostic, self-improving autonomous AI quantitative trading platform and research engine built with **DuckDB**, **PostgreSQL (Neon)**, **Redis Streams (Upstash)**, and **FastAPI**, managed with **uv**.

---

## 🏛️ System Architecture

```mermaid
flowchart TD
    subgraph Ingestion["1. Multi-Source Ingestion Layer"]
        direction LR
        Market["Market Data (CCXT / Native WS)"]
        News["News (GDELT 2.0 / RSS)"]
        Social["Social (Reddit Velocity)"]
        Macro["Macro (FRED Fed Rates)"]
        OnChain["On-Chain (DefiLlama TVL)"]
    end

    subgraph DataHygiene["2. Normalization & Quality Assurance"]
        Normalizer["Data Normalizer (Canonical Schemas)"]
        Cleaner["Data Cleaner (Spike Filter, Clock Sync)"]
        SymbolMgr["SymbolManager (Dynamic Runtime Registry)"]
    end

    subgraph EventStream["3. Distributed Event Backbone"]
        RedisStreams[("Upstash Redis Streams\n(Topic Streams & Consumer Groups)")]
    end

    subgraph StorageTier["4. Dual-Tier Storage Layer"]
        DuckDB[("DuckDB Time-Series Lake\n(Candles, Ticks, PIT Features)")]
        Postgres[("Neon PostgreSQL (AsyncPG)\n(Orders, Positions, Strategy Registry)")]
    end

    subgraph MultiAgentEngine["5. Multi-Agent Trading Desk & StateGraph"]
        TechAnalyst["📈 Technical Analyst"]
        SentAnalyst["📰 Sentiment Analyst"]
        MacroAnalyst["🌐 Macro Strategist"]
        Debate["⚔️ Bull vs Bear Debate"]
        CRO["🛡️ Chief Risk Officer (CRO)"]
        StateGraph["🔄 StateGraph Workflow & Reflection"]
    end

    subgraph CoreEngines["6. Execution & Risk Engine"]
        PIT_FS["Point-in-Time Feature Store"]
        StratRunner["Active Strategy Runner"]
        RiskGuard["Risk Engine (Drawdown Circuit Breakers)"]
        OMS["Order Management System"]
        Paper["Paper Trading Simulator / Broker"]
    end

    subgraph ResearchEngine["7. Autonomous AI Research Loop"]
        Researcher["Autonomous AI Researcher"]
        Optimizer["Walk-Forward Cross-Validator"]
    end

    subgraph APITier["8. FastAPI & Real-Time WebSockets"]
        FastAPIServer["FastAPI Server (:8000)"]
        WS["WebSocket Streamer (/ws/live)"]
        Charts["Visual Chart & Telemetry Engine"]
        REST["REST APIs (/api/*)"]
    end

    Ingestion --> Normalizer --> Cleaner --> RedisStreams
    SymbolMgr -.->|"Dynamic Pairs"| Ingestion
    RedisStreams --> DuckDB
    RedisStreams --> PIT_FS
    PIT_FS --> TechAnalyst & SentAnalyst & MacroAnalyst
    TechAnalyst & SentAnalyst & MacroAnalyst --> Debate --> CRO --> StateGraph
    StateGraph --> RiskGuard --> OMS --> Paper
    Paper -->|"Fills & Realized PnL"| Postgres
    Paper -->|"XADD order.filled"| RedisStreams

    DuckDB -->|"Training Slices"| Optimizer
    Researcher --> Optimizer -->|"Promoted Strategy Configs"| Postgres
    Postgres -.->|"Auto-Deploy Strategies"| StratRunner

    Paper -.-> FastAPIServer
    RedisStreams -.-> WS
    FastAPIServer --> REST
    FastAPIServer --> Charts
```

---

## ⚡ Quick Start with `uv`

### 1. Installation & Environment Sync
```bash
# Sync dependencies and virtual environment
uv sync --extra dev
```

### 2. Database Migrations with Alembic
```bash
# Apply migrations to Neon PostgreSQL
uv run alembic upgrade head
```

### 3. Run Test Suite
```bash
uv run pytest
```

### 4. Run Application Server
```bash
# Option A: Run directly with uv
uv run uvicorn app.server:app --host 0.0.0.0 --port 8000 --reload

# Option B: Run via Procfile / Honcho (Starts Web + Background Worker)
honcho start
```

* **Interactive Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
* **WebSocket Real-Time Feed**: `ws://localhost:8000/ws/live`
* **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## 🌐 API Reference

### 1. Dynamic Symbol Management
* **`GET /api/symbols`**: Retrieve all active trading pairs and asset details.
* **`POST /api/symbols`**: Dynamically add pairs at runtime (e.g., `{"symbols": ["AVAX/USDT", "DOGE/USDT"]}`).
* **`DELETE /api/symbols/{symbol}`**: Deactivate a symbol from active streaming.

### 2. Multi-Agent & StateGraph Reasoning
* **`GET /api/agents/consensus`**: Get real-time Multi-Agent consensus (Technical, Sentiment, Macro, Bull/Bear debate, CRO).
* **`GET /api/graphs/workflow`**: Execute the multi-agent StateGraph workflow and inspect node trace.

### 3. Visual Charts & Analytics
* **`GET /api/graphs/equity`**: Returns strategy equity curve data points and base64 PNG chart image.
* **`GET /api/graphs/candles`**: Returns OHLCV candlestick time series formatted for TradingView Lightweight Charts.

### 4. Portfolio & Execution
* **`GET /api/portfolio`**: Real-time cash, total equity, drawdown %, and active positions.
* **`GET /api/orders`**: Recent filled and pending orders from PostgreSQL.
* **`POST /api/backtest`**: Run on-demand multi-modal historical backtesting.
* **`POST /api/research/run`**: Trigger background autonomous AI research & strategy evolution loop.

---

## ⚙️ Environment Configuration (`.env`)

```env
# PostgreSQL Database (Neon)
DATABASE_URL=postgresql+asyncpg://neondb_owner:...@ep-proud-breeze-...tech/neondb?sslmode=require&channel_binding=require

# DuckDB Local Analytical Storage
DUCKDB_PATH=data/trading_agent.duckdb

# Redis Streams (Upstash Event Bus)
REDIS_URL=rediss://default:...@informed-sunfish-...io:6379
EVENT_BUS=redis_streams

# OpenAI-Compatible LLM (Groq / OpenRouter / Ollama)
OPENAI_BASE_URL=https://api.groq.com/openai/v1
OPENAI_API_KEY=gsk_your_groq_api_key_here
OPENAI_MODEL=llama-3.3-70b-versatile

# Dynamic Trading Symbols (Optional)
SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT
```

---

## 🧪 CI/CD & Verification

Every commit and pull request is automatically tested using **GitHub Actions** ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)).
