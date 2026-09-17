# Proposal: adopting TradingAgents' architecture into this repo

Design only — **no `tradingagents` dependency.** We adopt the *architecture* of
`TauricResearch/TradingAgents` (`main`, v0.4.0, Apache-2.0) and build it on
`langgraph` against our own data, LLM client, and OMS.

Status: research complete, no code or dependency changes made.

## 1. Reference design (what we are copying)

Read from the repo; this is what the upstream package does and what we want to
reproduce:

- LangGraph cyclic graph with conditional routing (their `ConditionalLogic`).
- Four analysts — market, social, news, fundamentals — selected via
  `selected_analysts`; each is an LLM + a `ToolNode` bound to its data tools.
- **Bull vs Bear researcher debate** for `max_debate_rounds`, then a Research
  Manager judge.
- Trader node produces a plan; then a **3-way risk debate** (aggressive /
  conservative / neutral) for `max_risk_discuss_rounds`, then a risk judge.
- Portfolio Manager emits `final_trade_decision`; `SignalProcessor` maps it to a
  5-tier rating (`Buy/Overweight/Hold/Underweight/Sell`, or `REVIEW`).
- `TradingMemoryLog`: persists each decision, later resolves the **realized return
  and alpha vs a benchmark**, LLM-reflects on it, and injects those lessons into
  the next run.
- `schemas.py`: structured Pydantic outputs for Research Manager / Trader / PM.
- Optional SqliteSaver checkpoint/resume keyed by a **run signature** (analysts +
  debate depth + asset type) so a crashed run resumes and a changed shape starts
  fresh.

We copy these *patterns*, not the code.

## 2. Feature-by-feature vs this repo

| Capability | This repo | TradingAgents (reference) | Gap |
|---|---|---|---|
| Orchestration | linear `TradingWorkflowGraph` (`app/research/agent_graph.py`), fan-in desk (`multi_agent.py`) | LangGraph cyclic graph w/ conditional routing | **large** |
| Analysts | Technical, Sentiment, Macro (`multi_agent.py:94/101/110`) | Market, Social, News, Fundamentals | medium |
| Peer interaction | none — specialists get identical `data_str`, never see peers | Bull vs Bear debate, N rounds + judge | **large** |
| Risk | single CRO synthesizer (`multi_agent.py:136`) | 3-way risk debate + judge | **large** |
| Structured output | `AgentOpinion` dataclass | Pydantic schemas (Research Mgr / Trader / PM) | small |
| Outcome memory | backtest gate only (Sharpe>1.0, DD<20%, WR>=45%, `researcher.py`) | decision log + realized return + alpha + reflection | **large** |
| Checkpoint/resume | none | LangGraph checkpointer + run signature | medium |
| Data | CCXT crypto, GDELT, Reddit, FRED, DefiLlama, DuckDB, `feature_store` | yfinance / alpha_vantage / FRED / polymarket | **we keep ours** |
| Execution | native risk + OMS | none (decision only) | **we keep ours** |
| Backtest | native metrics | backtrader | **we keep ours** |
| LLM layer | `app/core/llm.py::chat_completion` (OpenAI-compatible, cost accounting) | LangChain provider clients | **we keep ours** |

## 3. Why this is worth doing

The multi-agent desk feels useless for structural reasons, not prompt quality:
`_call_agent` sends all specialists the **same** `data_str` and collects
independent opinions. There is no dialogue, no rebuttal, and no memory of what
happened to past decisions. The reference design is built around those two missing
pieces (debate + reflection). That is the prize — not its dataflows.

## 4. Approach

Build a new debate graph in-repo, on `langgraph`, reusing our existing pieces:

- **Nodes call `app/core/llm.py::chat_completion`** directly (plain async
  functions). We do *not* use LangChain chat-model wrappers, so we keep our
  provider config, usage/cost accounting, and Groq/agentrouter setup as-is — no
  `langchain-openai` / `langchain-anthropic` / `langchain-google-genai` /
  `langchain-groq` needed.
- **Inputs** come from our `feature_store`, `candle_buffers`, news/social/macro
  providers — not yfinance.
- **Output** is our existing `MultiAgentConsensus` / `TradingSignal`; the existing
  `RiskGovernor` + OMS remain the single execution path.
- New dependency surface is deliberately tiny: `langgraph` (which pulls
  `langchain-core` transitively) and, only if we want resume, a
  `langgraph-checkpoint-*` package.

**New deps:** `langgraph`; optionally `langgraph-checkpoint-sqlite` (simple) or
`langgraph-checkpoint-postgres` (reuses our Postgres). No `tradingagents`, no
`yfinance`, no `backtrader`, no LangChain provider packages.

## 5. Phased plan

1. **Phase 1 — debate graph skeleton.** Add `langgraph`; new
   `app/research/debate_graph.py`. Wrap the existing Technical/Sentiment/Macro
   specialists as analyst nodes, add Bull/Bear nodes with `max_debate_rounds` and a
   Research Manager judge (structured output via Pydantic), emit
   `MultiAgentConsensus`. Expose behind `POST /api/agents/debate` and a feature
   flag (default off). Preserve the current 4-node `graph_history` contract and
   existing tests.
2. **Phase 2 — risk debate.** Add aggressive/conservative/neutral risk nodes +
   risk judge; keep `RiskGovernor` as the final gate.
3. **Phase 3 — memory + reflection.** Add an outcome ledger (realized return +
   alpha vs a crypto benchmark, e.g. BTC/ETH) persisted through
   `app/storage/database.py`; reflect on resolved outcomes and inject lessons into
   the next run. Reuse our backtest metrics for the return; no yfinance.
4. **Phase 4 — checkpoint/resume (optional).** Wire a langgraph checkpointer with
   a run signature (analysts + debate depth + symbol) so interrupted runs resume.

Budget note: a full run is ~15+ LLM calls (4 analysts + debate rounds + 3-way risk
+ judges + manager) vs our current 4. Measure latency and token cost after Phase 1.

## 6. Risks / friction

| Risk | Detail |
|---|---|
| Async/state semantics | LangGraph state reducers and our asyncio app must agree; a wrong reducer duplicates messages on resume (upstream bug #1249 is exactly this). |
| Unbounded loops | Cyclic debate can spin; bound with `max_debate_rounds` / `max_risk_discuss_rounds` and a recursion limit (upstream uses `max_recur_limit`). |
| Cost/latency | ~15+ calls per decision; must stay within LLM budget and endpoint timeouts. |
| Type/lint gates | New graph must pass `.venv/bin/ruff` and `.venv/bin/mypy` (bare invocation) and keep pytest green. |
| Duplicate authority | LLM nodes must never touch the OMS directly; a single executor path stays authoritative. |
| Checkpoint backend | Choosing sqlite vs postgres adds state to manage; defer to Phase 4. |

## 7. What we borrow vs build

**Borrow (design):** node topology, debate-round pattern, judge / manager
structured-output pattern, memory-log-with-realized-return pattern, checkpoint with
run-signature invalidation.

**Keep ours:** CCXT/GDELT/FRED/DefiLlama dataflows, `feature_store`, native
backtest metrics, `app/core/llm.py` LLM client + cost accounting, RiskGovernor +
OMS execution, FastAPI/`/ws/live` surface.

**Do not take:** the `tradingagents` package, its yfinance/alpha_vantage dataflows,
backtrader, its CLI, its markdown report tree, or its `~/.tradingagents` config.

## Next decision

Start Phase 1 (add `langgraph`, build `app/research/debate_graph.py` behind a
feature flag), or adjust scope first.
