# Autonomous AI Trading Agent

A provider-agnostic, self-improving autonomous AI quantitative trading platform and research engine built with **DuckDB**, **PostgreSQL**, **Redis Streams**, and **FastAPI**, managed with **uv**.

---

## 🏛️ System Architecture

```mermaid
flowchart TD
    subgraph Ingestion["1. Multi-Source Ingestion Layer"]
        direction LR
        Market["Market Data (CCXT / Native WS)"]
        News["News (GDELT 2.0 / RSS)"]
        Social["Social (Reddit / StockTwits)"]
        Macro["Macro (FRED Fed Rates)"]
        OnChain["On-Chain (DefiLlama TVL)"]
    end

    subgraph DataHygiene["2. Normalization & Quality Assurance"]
        Normalizer["Data Normalizer (Canonical Schemas)"]
        Cleaner["Data Cleaner (Spike Filter, Clock Sync)"]
    end

    subgraph EventStream["3. Distributed Event Backbone"]
        RedisStreams[("Upstash Redis Streams\n(Topic Streams & Consumer Groups)")]
    end

    subgraph StorageTier["4. Dual-Tier Storage Layer"]
        DuckDB[("DuckDB Time-Series Lake\n(Candles, Ticks, PIT Features)")]
        Postgres[("PostgreSQL (AsyncPG)\n(Orders, Positions, Strategy Registry)")]
    end

    subgraph CoreEngines["5. Core Processing & Execution"]
        subgraph TradingEngine["Production Trading & Risk Engine"]
            PIT_FS["Point-in-Time Feature Store"]
            StratRunner["Active Strategy Runner"]
            RiskGuard["Risk Engine (Drawdown Circuit Breakers)"]
            OMS["Order Management System"]
            Paper["Paper Trading Simulator / Broker"]
        end

        subgraph ResearchEngine["AI Research & Self-Improvement Loop"]
            Researcher["Autonomous AI Researcher"]
            Optimizer["Walk-Forward Cross-Validator"]
        end
    end

    subgraph APITier["6. FastAPI & Real-Time WebSockets"]
        FastAPIServer["FastAPI Server (:8000)"]
        WS["WebSocket Streamer (/ws/live)"]
        REST["REST API (/api/portfolio, /api/orders, /api/backtest)"]
    end

    Ingestion --> Normalizer --> Cleaner -->|"XADD market.candle / info.*"| RedisStreams
    RedisStreams -->|"Batch Ingest"| DuckDB
    RedisStreams -->|"Real-Time Features"| PIT_FS

    PIT_FS --> StratRunner -->|"Signal"| RiskGuard -->|"Approved"| OMS --> Paper
    Paper -->|"Fills & Realized PnL"| Postgres
    Paper -->|"XADD order.filled"| RedisStreams

    DuckDB -->|"Training Slices"| Optimizer
    Researcher --> Optimizer -->|"Promoted Strategy Configs"| Postgres
    Postgres -.->|"Auto-Deploy Strategies"| StratRunner

    Paper -.-> FastAPIServer
    RedisStreams -.-> WS
    FastAPIServer --> REST
```

---

## ⚡ Quick Start with `uv`

### 1. Installation & Environment Sync
```bash
# Sync virtual environment & dependencies
uv sync
```

### 2. Run Tests
```bash
uv run pytest
```

### 3. Run Backend Server
```bash
# Run with uv
uv run uvicorn app.server:app --host 0.0.0.0 --port 8000 --reload
```

* **Interactive Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
* **WebSocket Real-Time Feed**: `ws://localhost:8000/ws/live`
* **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## 🧩 Architecture Summary

* **Provider-Agnostic Ingestion**: Hot-swappable providers for Market Data, News (GDELT), Social (Reddit), Macro (FRED), and On-Chain (DefiLlama).
* **Point-In-Time Feature Store**: Strict historical temporal alignment preventing lookahead bias.
* **Risk Engine & Circuit Breakers**: Position sizing, maximum drawdown circuit breakers, and bracket stops.
* **Autonomous AI Researcher**: Hypothesis generation, hyperparameter optimization, and out-of-sample walk-forward cross validation.
* **Dual Storage**: DuckDB for analytical time-series and PostgreSQL for transactional orders and experiment registries.
