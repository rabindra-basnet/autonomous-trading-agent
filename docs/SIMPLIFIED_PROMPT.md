# Self-Contained Prompt: Build "TradePulse" from scratch

> Paste this whole file into any capable coding agent, in any codebase/empty
> repo, to generate a working simplified trading-research agent. It is fully
> self-contained: it does NOT require access to the TradingAgents repo or any
> other source. Everything needed is specified below.

---

## Role

You are a senior Python engineer. Build a new, self-contained Python project
called **TradePulse**: a single-pass, multi-stage LLM trading research
framework. Given a ticker and an optional date, it analyzes the asset through
four analyst stages, synthesizes them, and produces a final
`Buy / Overweight / Hold / Underweight / Sell` decision with an executive
summary, investment thesis, optional price target, and optional time horizon.

This is a from-scratch reimplementation of the *feature set* of the open-source
project TradingAgents (TauricResearch), but with a drastically simpler process
flow: one linear pipeline, one LLM call per stage, no graph orchestration, no
multi-agent debate loops. You must not copy any TradingAgents code — you do not
have access to it; reproduce the behavior from the specification below.

## Hard constraints

- **No LangGraph, no LangChain.** No `StateGraph`, `ToolNode`, `ToolMessage`
  loops, `RemoveMessage`, message-clearing cycles, or checkpoint databases.
- **No multi-agent debates.** No bull/bear rounds, no aggressive/conservative/
  neutral rounds, no debate `count` thresholds. Stage G does the judging in a
  single call.
- Runtime dependencies are a hard limit: `openai` (for OpenAI and any
  OpenAI-compatible endpoint), optionally `anthropic` and `google-genai`, plus
  `yfinance`. Everything else from the Python stdlib, plus `pydantic` and
  `typer`. Optionally `rich` for the CLI, `python-dotenv` for `.env` loading.
- Target **1,000–1,800 lines** of Python total (excluding tests). One engineer
  should be able to re-derive every file. Keep each file focused and readable.

## Deliverable

A pip-installable package with an interactive CLI, programmatic API, on-disk
markdown reports, a decision memory log, config (defaults + env overrides +
`.env`), unit tests, and an optional Dockerfile. See "Project layout" and
"Acceptance criteria".

## Inputs and entry points

- Programmatic:
  ```python
  from tradepulse.graph.pipeline import TradePulseGraph
  ta = TradePulseGraph(config=DEFAULT_CONFIG.copy())
  final_state, signal = ta.propagate("AAPL", "2026-09-01")
  print(signal)  # "Buy" | "Overweight" | "Hold" | "Underweight" | "Sell" | "REVIEW"
  ```
- CLI: `tradepulse analyze` (or `python -m cli.main`). Interactive prompts:
  1. ticker (auto-detect asset type — see Ticker handling)
  2. trade date (default today, any `YYYY-MM-DD`)
  3. LLM provider (openai / anthropic / google / openai_compatible)
  4. deep model (complex reasoning) and quick model (cheap, fast)
  5. which of the 4 analyst stages to run (default: all)
  6. research depth (light/standard/deep → maps to article limits)
  7. output language (default English)
  - While running, print each stage's report to the terminal as it completes
    (plain text or `rich` panels are fine).
  - Support `tradepulse load <config.json>` / `tradepulse dump <config.json>`
    for non-interactive runs. A non-interactive run requires an API key;
    otherwise exit with a clear message, never a traceback.

## Ticker handling

- `BTC-USD`, `ETH-USD` (any `*-USD`/`*-USDT`) → crypto pipeline:
  fundamentals stage SKIPPED, labels use "asset" not "company", and prompts say
  company fundamentals may be unavailable.
- Exchange-suffixed tickers pass through untouched: `.NS`, `.BO`, `.T`, `.HK`,
  `.L`, `.TO`, `.AX`, `.SS`, `.SZ`. Plain tickers are US-listed.
- Benchmark for alpha: `benchmark_map` keyed by suffix
  (`.NS`→^NSEI, `.T`→^N225, `.HK`→^HSI, `.L`→^FTSE, `.TO`→^GSPTSE,
  `.AX`→^AXJO, `.SS`→000001.SS, `.SZ`→399001.SZ, `""`→SPY), overridable by
  config `benchmark_ticker`.

## Instrument identity grounding (crucial anti-hallucination)

Before any LLM call, resolve the ticker once with `yfinance.Ticker(ticker)`:
pull `longName`/`shortName`, `sector`, `industry`, `exchange`. Build a context
string:

```
The instrument to analyze is `<TICKER>`. Use this exact ticker in every report
and tool call, preserving any exchange suffix. Resolved identity: Company: X;
Business classification: SECTOR / INDUSTRY; Exchange: EXCH. Do not substitute a
different company or ticker unless tool output explicitly disproves this.
```

Cache per ticker (`lru_cache`). Fail open: if yfinance errors, fall back to a
ticker-only context. Inject this string near the top of every stage prompt.

## The 7-stage linear pipeline (the core "simple process flow")

Run exactly in this order, one LLM call per stage, no loops:

```
┌─ Non-LLM ─────────────────────────────────────────────┐
│ 1. resolve instrument identity (yfinance, cached)      │
│ 2. resolve pending memory outcomes for this ticker     │
└────────────────────────────────────────────────────────┘
   │
   ▼
┌────────────────────────────────────────────────────────┐
│ A. Market/Technical analyst      → market_report       │
│ B. News/Macro analyst            → news_report         │
│ C. Sentiment analyst             → sentiment_report    │
│ D. Fundamentals analyst          → fundamentals_report │ (skipped for crypto)
│ E. Research synthesis (deep LLM) → investment_plan     │ reads A–D
│ F. Trader proposal  (quick LLM)  → trader_proposal     │ reads E + market_report
│ G. Portfolio Manager (deep LLM)  → final_trade_decision│ reads E, F + memory log
└────────────────────────────────────────────────────────┘
   │
   ▼  write reports → append memory entry → print final decision
```

Rules:

- Each stage runs once, sequentially, consuming the reports of the previous
  stages. A stage may make ONE round of data-fetch calls before its single LLM
  call (see Stage A/B/C/D); it never loops back.
- User-selected stages form a shorter chain. Unselected stages are skipped and
  their missing report is passed to later prompts as e.g.
  `Fundamentals report: (not selected)`. At least one analyst stage must run.
- The final decision (stage G) must contain the literal rating word, an
  executive summary (2–4 sentences: entry strategy, sizing, key risk levels,
  time horizon), an investment thesis (detailed, evidence-anchored), and
  optional price target + time horizon — rendered as markdown with these exact
  section headers: `**Rating**`, `**Executive Summary**`, `**Investment
  Thesis**`, optionally `**Price Target**`, `**Time Horizon**`.
- Failure containment: non-core data fetch failures return a sentinel string
  `DATA_UNAVAILABLE: <reason> ... Proceed without it; do not fabricate values.`
  and the run continues. Core-data failures (prices, financials) abort loudly.
  An unreachable LLM provider after retries aborts with a clean clear message.
- The pipeline must be the single core module: a small `pipeline.py` that
  imports the stages and runs them in order. No framework.

## Stage specifications (with prompt guidance)

Shared system framing for any stage that calls tools:
"You are a helpful AI assistant collaborating with other assistants. Use the
provided data to progress toward the analysis date `<date>` (treat it as 'now'
for all date ranges).` + instrument context. If a downstream stage already
produced `FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**`, stop early.

### Stage A — Market/Technical analyst

Fetch OHLCV history for the ticker over a trailing window (default ~1 year)
ending at the trade date. **Compute indicators yourself** from the DataFrame
(pure functions, no indicator library): 50-SMA, 200-SMA, 10-EMA, MACD
(line/signal/histogram), RSI(14), Bollinger (20, 2 std), ATR(14), VWMA. Prompt
the model to: pick up to 8 complementary indicators relevant to the current
market state (categorize them: moving averages, MACD, momentum, volatility,
volume); explain why each is chosen; write a detailed technical report; ground
every exact price / percentage / support-resistance claim in the fetched data
(no invented numbers — if attributing a level, cite the concrete date and
price); append a markdown summary table of key points.

### Stage B — News/Macro analyst

Fetch ticker-specific news (limit from config, default 20) and global/macro
news (limit 10, lookback 7 days) around the trade date. Optionally surface
macro indicators (CPI, unemployment, fed funds rate, 10y treasury, yield curve)
and market-implied probabilities of forward-looking events when a free source
is reachable (e.g. FRED via its public CSV API, Polymarket keyless API). Prompt
for a macro/event-impact report; ground claims in fetched items; append a
markdown summary table.

### Stage C — Sentiment analyst

Fetch ticker news plus public chatter (StockTwits API is public; Reddit via
`praw` is optional — skip politely if it doubles the dependency set). Output a
structured sentiment read (see Schemas) with band, score, confidence, and a
narrative containing: source-by-source breakdown with counts/quotes,
cross-source divergences, dominant themes, catalysts and risks, then a markdown
table of signals.

### Stage D — Fundamentals analyst

Fetch income statement, balance sheet, cash flow, and valuation metrics from
`yfinance`. Prompt for: intrinsic health, revenue/profit trends, cash position,
debt, red flags, valuation context; append a markdown table. (Skipped for
crypto.)

### Stage E — Research synthesis (deep model)

No tools. Input: all four analyst reports (or "(not selected)") + instrument
context. Output (structured): `recommendation` (one of the 5-tier rating),
`rationale` (conversational summary of both bull and bear sides, ending with
why the recommendation won), `strategic_actions` (concrete steps incl. position
sizing consistent with the rating). Render to markdown:
`**Recommendation**`, `**Rationale**`, `**Strategic Actions**`.

### Stage F — Trader (quick model)

No tools. Input: investment plan + the market/technical report (for price
structure grounding). Output (structured): `action` (`Buy`/`Hold`/`Sell`),
`reasoning` (2–4 sentences), optional `entry_price`, `stop_loss`,
`position_sizing`. Entry/stop must be absolute price numbers in the
instrument's quote currency, never percentages or ranges. Render to markdown
ending with the literal line `FINAL TRANSACTION PROPOSAL: **BUY|HOLD|SELL**`.

### Stage G — Portfolio Manager (deep model)

No tools. Input: investment plan, trader proposal, risk-relevant notes from the
analysts, and the injected memory context (past decisions/outcomes when
present). Output (structured): `rating`, `executive_summary`, `investment_thesis`,
optional `price_target`, `time_horizon`. Render as the final decision markdown.

## Rating scale (use exactly one, everywhere)

- **Buy** — strong conviction to enter or add
- **Overweight** — favorable, gradually increase exposure
- **Underweight** — reduce exposure / take partial profits
- **Sell** — exit or avoid entry
- **Hold** — maintain position, no action. **Hold is the default when evidence
  is balanced, conflicting, ambiguous, or insufficient.** Never force a
  direction to appear decisive.

## Schemas (pydantic)

- `PortfolioRating` enum: Buy/Overweight/Hold/Underweight/Sell.
- `TraderAction` enum: Buy/Hold/Sell.
- `SentimentBand` enum: Bullish/Mildly Bullish/Neutral/Mixed/Mildly Bearish/Bearish.
- `SentimentReport`: `overall_band`, `overall_score` (0–10, 5=neutral,
  10=bullish), `confidence` (low/medium/high), `narrative`.
- `ResearchPlan`: `recommendation`, `rationale`, `strategic_actions`.
- `TraderProposal`: `action`, `reasoning`, `entry_price|None`, `stop_loss|None`,
  `position_sizing|None`. Coerce placeholder strings ("None"/"N/A"),
  percentages ("15%"), and formatted prices ("$1,234.50") before validation —
  drop placeholders and percentages, strip currency formatting.
- `PortfolioDecision`: `rating`, `executive_summary`, `investment_thesis`,
  `price_target|None`, `time_horizon|None`.
- Every structured stage uses a shared helper `invoke_structured_or_freetext`:
  try `with_structured_output(schema)` on the provider; on any failure warn and
  re-invoke as free text so the run never blocks. If the provider has no
  structured output, log a warning once and always use free text, then parse
  the best-effort rating from the text.

## LLM client abstraction

`create_llm_client(provider, model, base_url=None, temperature=None, ...)`
returns a tiny uniform interface:
`invoke(prompt) -> str` and `invoke_structured(schema, prompt) -> parsed | None`.

- `openai` — OpenAIClient over the `openai` SDK. Also the route for provider
  strings `openrouter`, `groq`, `deepseek`, `mistral`, `together` via
  `base_url` + `OPENAI_COMPATIBLE_API_KEY`.
- `openai_compatible` — any OpenAI-compatible server (vLLM, LM Studio,
  llama.cpp, custom relay): `base_url` (or `TRADEPULSE_LLM_BACKEND_URL`, default
  `http://localhost:8000/v1` for vLLM).
- `anthropic` — AnthropicClient; `google` — GoogleClient (Gemini), both optional
  but implement the same interface.
- `model_catalog.py` — a curated dict of current model IDs per provider with a
  "deep" and "quick" entry, e.g. openai: `gpt-5.6` deep / `gpt-5.6-luna` quick;
  anthropic: Claude 5-class; google: Gemini 3.x-class. Allow a free "Custom
  model ID" input in the CLI for any model not listed.
- Load keys from `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`,
  `OPENAI_COMPATIBLE_API_KEY`. Validate presence at startup per provider;
  exit with a clear message if missing.
- Forward `temperature` to providers when set (lower = more repeatable on
  models that honor it; reasoning models largely ignore it — note this in the
  README).

## Decision memory (simplified)

- Append-only markdown file at `~/.tradepulse/memory.md`
  (override `TRADEPULSE_MEMORY_LOG_PATH`).
- Other paths: results under `~/.tradepulse/logs`, cache under
  `~/.tradepulse/cache` (enables `TRADEPULSE_RESULTS_DIR`/`TRADEPULSE_CACHE_DIR`).
- Entry format: header line
  `[YYYY-MM-DD | TICKER | RATING | pending]` followed by `DECISION:` and the
  final decision markdown, then a hard separator comment. Use one regex for the
  header and one to extract the decision body.
- At the start of each run, resolve *pending* entries for the same ticker:
  fetch realized returns (raw and alpha vs the benchmark index) over a fixed
  holding window (default 5 trading days) from the entry date using yfinance;
  require the full window to have traded, else leave pending for next run.
  Write the update as `[... | raw% | alpha% | 5d]` + `REFLECTION:` section
  (one short LLM paragraph on what worked/didn't). Use atomic write
  (temp file + `os.replace`). ~100–150 lines total. No point-in-time
  filtering, no rotation cap needed (a `memory_log_max_entries` rotation is
  optional).

## Config

`default_config.py` defining:
`llm_provider` ("openai"), `deep_think_llm`, `quick_think_llm`,
`backend_url` (None), `output_language` ("English"), `temperature` (None),
`news_article_limit` (20), `global_news_article_limit` (10),
`global_news_lookback_days` (7), `max_holding_days` (5),
`results_dir`, `data_cache_dir`, `memory_log_path`, `benchmark_ticker` (None),
`benchmark_map`, `data_vendors` dict (tool → vendor, e.g.
`{"get_news": "yfinance", "get_stock_data": "yfinance"}`).

Env overrides: any `TRADEPULSE_<KEY>` (mapping table) coerced to the type of
the existing default (bool/int/float/str); invalid values raise at startup with
a clear message, never silently ignore. Load `.env` if present.

## Data layer (single file, ~150–250 lines)

One `dataflows/yfinance.py` + `dataflows/route.py`:

- `get_stock_data(ticker, date) -> DataFrame` (OHLCV)
- `get_indicators(df) -> DataFrame` (the computed indicators above)
- `get_news(ticker, start, end, limit) -> list[dict]`
- `get_global_news(date, lookback_days, limit, queries) -> list[dict]`
- `get_fundamentals/income_statement/balance_sheet/cashflow(ticker) -> str`
- `route("get_stock_data", ...)` → looks up `data_vendors`, tries the vendors
  in order, returns the sentinel string on clean "no data" and raises on a
  hard vendor failure. Include a `NO_DATA_AVAILABLE: ... do not fabricate
  values` sentinel for unavailable symbols (e.g. delisted/invalid) so agents
  never invent prices.

`yfinance` should be called with explicit date ranges bounded by the trade date
so a historical run never sees future data.

## Project layout

```
tradepulse/
  __init__.py
  main.py                 # programmatic entry (TradePulseGraph)
  default_config.py
  llm_clients/
    base_client.py
    factory.py
    openai_client.py
    anthropic_client.py   # optional
    google_client.py      # optional
    model_catalog.py
  dataflows/
    yfinance.py
    indicators.py
    route.py
  agents/
    schemas.py            # enums + pydantic schemas + render helpers
    context.py            # instrument identity + language helper
    memory.py             # decision log
    analysts.py           # stages A–D (market/news/sentiment/fundamentals)
    synthesis.py          # stage E
    trader.py             # stage F
    portfolio_manager.py  # stage G
  graph/
    pipeline.py           # the linear pipeline — the heart of the project
cli/
  main.py                 # typer CLI
  utils.py
tests/                    # pytest, no network, no LLM
test.py                   # import-smoke entry
Dockerfile                # optional
docker-compose.yml        # optional
pyproject.toml            # deps + console_scripts entrypoint "tradepulse"
.env.example              # TRADEPULSE_* vars + API keys
README.md
```

## Tests (pytest, offline)

Cover at least: indicator math on a synthetic DataFrame (values within sane
bounds, RSI 0–100, SMA equals rolling mean), instrument-context builder,
memory-log append/parse/resolve (tmp_path), config env-override coercion
(bool/int/float + invalid→ValueError), sentiment/schema placeholder coercion,
rating parse from free text. No network calls, no real LLM invocations.

## Acceptance criteria (verify before stopping)

1. Clean import: `python -c "from tradepulse.graph.pipeline import TradePulseGraph; print('ok')"`.
2. `pip install -e .` works; `tradepulse --help` works; `python -m cli.main` works.
3. Starting the CLI without a configured provider/key exits with a helpful
   message and a 0/1 exit code — no traceback.
4. `pytest -q` passes.
5. Generated code contains NO: `langgraph`, `langchain`, `StateGraph`,
   `ToolNode`, `create_react_agent`, `RemoveMessage`, debate-round loops,
   checkpointing, or SQLite.
6. `main.py`'s `propagate()` example runs the whole linear pipeline and returns
   the final decision string.
7. README documents install, `.env`, the CLI flows, the linear flow diagram,
   the rating scale, reproducibility caveats (LLM sampling + live data make two
   runs differ), and a research-only / not-financial-advice disclaimer.
8. Total Python ≤ ~1,800 lines excluding tests.

On completion, report: the project tree, `pytest -q` output, and a 5-line
summary of the pipeline flow.