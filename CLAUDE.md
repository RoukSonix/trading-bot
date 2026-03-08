# AGENTS.md — Trading Bots Monorepo

> Context document for AI agents working on this codebase.
> Read this file first before making any changes.

### Maintenance Rule
**After fixing any bug, issue, or task listed in this file — remove its entry from AGENTS.md and add a note to CHANGELOG.md.** Keep this file clean and current. If CHANGELOG.md doesn't exist, create it.

### Development Workflow (MANDATORY)

**All development MUST use branches + git worktree. NEVER commit directly to main.**

1. **Create branch + worktree:**
   ```bash
   cd ~/projects/CentricVoid/trading-bots
   git worktree add ../trading-bots-<task> -b <branch-name>
   cd ../trading-bots-<task>
   ```
   Branch naming: `sprint-m<N>/<short-description>` (e.g. `sprint-m2/grid-logic`)

2. **Do all work in the worktree**, commit to the branch.

3. **Run tests before pushing** — all tests must pass:
   ```bash
   cd jesse-bot && ../.venv/bin/python -m pytest tests/ -v
   ```

4. **When done**, push branch and create PR:
   ```bash
   git push origin <branch-name>
   gh pr create --title "Sprint M<N>: <description>" --body "..."
   ```

5. **Code review is done by a SEPARATE ACP agent** (never the same agent that wrote the code). The reviewer reads the diff and leaves inline comments or approves.

6. **After review approval**, merge via GitHub:
   ```bash
   gh pr merge <PR-number> --merge
   ```

7. **Cleanup worktree (ALWAYS after merge):**
   ```bash
   git worktree remove ../trading-bots-<task>
   git branch -d <branch-name>
   ```

**Why:** Multiple ACP agents develop in parallel. Direct commits to main cause conflicts, untested code, and broken builds. Code review by a different agent catches blind spots.

---

## Project Overview

**What:** AI-assisted automated trading bots for crypto and prediction markets.
**Architecture:** Python monorepo with shared library + individual bot packages.
**Owner:** Andrey (RoukSonix)
**Repository:** https://github.com/RoukSonix/trading-bot
**Server:** ts1-rnd-llm01 (10.48.14.85), Docker deployment

---

## Repository Structure

```
trading-bots/
├── shared/                    # Shared library (ALL bots use this)
│   ├── ai/                    # LLM integration (LangChain + OpenRouter)
│   │   ├── agent.py           # TradingAgent — market analysis, grid optimization
│   │   └── prompts.py         # Prompt templates for LLM calls
│   ├── alerts/                # Multi-channel notifications
│   │   ├── manager.py         # AlertManager — central orchestrator
│   │   ├── discord.py         # Discord webhook alerts (PRIMARY)
│   │   ├── email.py           # SMTP email alerts (secondary)
│   │   ├── telegram.py        # ⚠️ ORPHANED — never wired into AlertManager
│   │   └── rules.py           # Alert rules engine (price/volume/PnL thresholds)
│   ├── api/                   # FastAPI backend (port 8000)
│   │   ├── main.py            # App setup, CORS, health checks, /metrics
│   │   └── routes/            # REST endpoints: bot, candles, orders, positions, trades
│   ├── backtest/              # Backtesting engine
│   │   ├── engine.py          # Core backtest runner
│   │   ├── benchmark.py       # Walk-forward benchmark
│   │   └── charts.py          # Backtest visualization
│   ├── config/
│   │   └── settings.py        # Pydantic Settings (.env based)
│   ├── core/
│   │   ├── database.py        # SQLAlchemy/SQLite — OHLCV, Trade, Position, TradeLog
│   │   ├── indicators.py      # Technical indicators (RSI, SMA, EMA, BB, MACD, ATR)
│   │   └── state.py           # JSON file-based inter-process state
│   ├── dashboard/             # Streamlit frontend (port 8501)
│   │   ├── app.py             # Main dashboard app
│   │   └── components/        # grid_view, candlestick_chart, order_book, pnl_chart, trade_table
│   ├── factors/               # Multi-factor analysis (Sprint 15)
│   │   ├── factor_calculator.py  # Momentum, volatility, RSI, volume factors
│   │   └── factor_strategy.py   # Market regime detection, grid suitability scoring
│   ├── monitoring/
│   │   └── metrics.py         # Prometheus metrics (⚠️ bot records data but verify)
│   ├── optimization/          # Hyperparameter optimization (Sprint 18)
│   │   ├── optimizer.py       # Optuna-based optimization
│   │   ├── walk_forward.py    # Walk-forward analysis
│   │   └── metrics.py         # Optimization metrics
│   ├── risk/                  # Risk management
│   │   ├── position_sizer.py  # Kelly criterion, fixed %, ATR-based sizing
│   │   ├── stop_loss.py       # ⚠️ StopLossManager instantiated but NEVER CALLED in bot.py
│   │   ├── limits.py          # Daily loss limit, max drawdown, consecutive losses
│   │   └── metrics.py         # Sharpe, Sortino, Calmar ratios
│   ├── vector_db/             # News sentiment (Sprint 16)
│   │   ├── news_fetcher.py    # CryptoCompare + CoinGecko news
│   │   ├── vector_store.py    # ChromaDB persistent storage
│   │   ├── embeddings.py      # Ollama nomic-embed-text embeddings
│   │   └── sentiment.py       # Keyword-based sentiment → trading signals
│   └── requirements.txt
│
├── binance-bot/               # Binance Grid Trading Bot (ACTIVE)
│   ├── src/binance_bot/
│   │   ├── bot.py             # Main bot runner (853 lines) — state machine: WAITING/TRADING/PAUSED
│   │   ├── core/
│   │   │   ├── exchange.py    # CCXT Binance client
│   │   │   ├── data_collector.py
│   │   │   ├── order_manager.py
│   │   │   ├── position_manager.py
│   │   │   └── emergency.py   # Emergency stop mechanism
│   │   └── strategies/
│   │       ├── base.py        # Signal, SignalType, BaseStrategy
│   │       ├── grid.py        # GridStrategy — core grid logic
│   │       └── ai_grid.py     # AIGridStrategy — AI-enhanced grid with factors
│   ├── scripts/               # Entry points: run_bot, run_paper_trading, run_backtest, etc.
│   ├── docs/                  # Project docs: strategies, exchanges, instruments, project-plan
│   ├── monitoring/            # Prometheus + Grafana configs
│   ├── docker-compose*.yml    # base, dev, prod, monitoring
│   ├── Dockerfile
│   └── .env                   # API keys (gitignored)
│
├── jesse-bot/                 # Jesse-based Grid Trading Bot (PARALLEL, Sprint M1+)
│   ├── strategies/
│   │   └── AIGridStrategy/    # Grid strategy as Jesse plugin
│   │       ├── __init__.py    # Jesse Strategy subclass
│   │       └── grid_logic.py  # Pure Python grid logic (testable without Redis)
│   ├── tests/                 # 28 unit tests for grid logic
│   ├── docker/                # docker-compose.yml (jesse + postgres + redis)
│   ├── config.py              # Jesse exchange/optimization config
│   ├── routes.py              # Trading routes (symbol + timeframe + strategy)
│   └── .env                   # Jesse config (gitignored)
│
├── polymarket-bot/            # Prediction Markets Bot (EMPTY SCAFFOLD)
│   ├── src/polymarket_bot/    # Only __init__.py files
│   └── Dockerfile
│
├── tests/                     # 255 test functions across 19 files (binance-bot)
│   ├── unit/                  # grid, indicators, database, paper_trades, alerts, etc.
│   ├── integration/           # trade flow, backtest, optimization, bidirectional, news
│   ├── test_factors/          # factor calculator + strategy tests
│   └── test_vector_db/        # sentiment + news fetcher tests
│
├── data/                      # SQLite databases, optimized params
├── .github/workflows/test.yml # CI: pytest on push/PR
├── AUDIT.md                   # Detailed functionality audit (2026-03-06)
├── RESEARCH.md                # Market research, open-source tools comparison
└── README.md                  # Setup guide, architecture overview
```

### Key Files to Read

| Purpose | File |
|---------|------|
| How the bot works | `binance-bot/src/binance_bot/bot.py` |
| Grid strategy logic | `binance-bot/src/binance_bot/strategies/grid.py` |
| AI-enhanced strategy | `binance-bot/src/binance_bot/strategies/ai_grid.py` |
| All configuration | `shared/config/settings.py` + `binance-bot/.env.example` |
| Sprint history & plan | `binance-bot/docs/project-plan.md` |
| Previous code audit | `AUDIT.md` |
| Previous code review | `shared/REVIEW.md` |

---

## Current State (as of 2026-03-07)

### What Works

- **Grid Trading Bot** — runs 24/7 on testnet via Docker on ts1-rnd-llm01
- **AI Layer** — LLM (OpenRouter/Claude Sonnet) analyzes market, optimizes grid, periodic reviews
- **State Machine** — WAITING → TRADING → PAUSED with AI-driven transitions
- **Factor Analysis** — calculates momentum/volatility/RSI/volume factors, feeds to AI context
- **News Sentiment** — fetches crypto news, analyzes sentiment, passes to AI (via Ollama embeddings)
- **Alerts** — Discord webhook notifications (trade, status, errors, daily summary)
- **Dashboard** — Streamlit UI with grid view, charts, trade history
- **API** — FastAPI with 20+ endpoints
- **Risk Management** — position sizing (Kelly/fixed %), daily loss limits, max drawdown
- **Backtesting** — engine with metrics and visualization
- **Hyperparameter Optimization** — Optuna-based with walk-forward analysis
- **Bidirectional Grid** — long and short grid trading with trend detection
- **255 tests** across unit + integration suites

### What Does NOT Work (Known Issues)

#### Critical — Features Built But Disconnected

1. **StopLossManager** — instantiated in `bot.py` (`self.stop_loss_mgr` or similar) but **no methods are ever called**. Zero stop-loss protection in live trading.

2. **Telegram Alerts** — `shared/alerts/telegram.py` is fully implemented but **AlertManager never routes to it**. No consumer imports it.

3. **PnL Reporter** — `shared/reports/pnl.py` exists but is **never imported anywhere**.

4. **Logging Config** — `shared/utils/logging_config.py` exists but every file rolls its own loguru setup.

#### Bugs

5. **Discord retry stack overflow** — `shared/alerts/discord.py` uses recursive `_send_webhook()` on HTTP 429. No max retry limit. Can overflow stack on sustained rate limiting.

6. **Broken f-string in AlertManager** — `shared/alerts/manager.py` lines ~248-249: `TypeError` when `current_price` is None in status email.

7. **No SMTP timeout** — `shared/alerts/email.py`: `aiosmtplib.send()` without timeout, can block indefinitely.

8. **No LLM timeout** — `ai_grid.py` `_call_llm()` has no timeout. If OpenRouter is slow/down, the entire bot loop blocks.

9. **`datetime.utcnow()` deprecated** — used in 7+ places in `database.py` and alert files. Deprecated since Python 3.12.

10. **Float precision** — `database.py` uses `Float` for `Trade.amount`. Should be `Decimal`/`Numeric` for financial data.

11. **Fragile LLM parsing** — `ai_grid.py:332-357`: line-by-line string parsing of AI responses. Breaks if format varies.

12. **Unbounded grid growth** — `grid.py` `_create_opposite_level()` creates new levels without limit.

13. **Streamlit `width="stretch"`** — used in 9 places, not a valid parameter (should be `use_container_width=True`).

14. **Sortino ratio returns `float('inf')`** — `risk/metrics.py:209` when downside deviation is 0. Not JSON serializable.

15. **Import error risk** — `api/main.py:29` imports `get_rules_engine` from `shared.alerts` which may not be exported in `__init__.py`.

16. **Missing `exit_time` field** — `api/routes/trades.py:144` references `log.exit_time` which doesn't exist on `TradeLog` model.

#### Dead Code

| File/Module | Status |
|-------------|--------|
| `shared/reports/pnl.py` + `__init__.py` | Never imported |
| `shared/utils/logging_config.py` + `__init__.py` | Never imported |
| `shared/alerts/telegram.py` | Never wired into AlertManager |
| `binance-bot/src/binance_bot/main.py` | Sprint 4 test script, not entry point |
| `shared/ai/agent.py` — `assess_risk()` method | Fully implemented, never called |
| `shared/core/state.py` — `GridLevel`, `Position` dataclasses | Never instantiated |
| `shared/core/state.py` — `delete_state()` | Never called |
| `shared/alerts/manager.py` — `AlertType` enum | Never referenced |
| Various unused imports | See `AUDIT.md` for full list |

#### Unused Dependencies

| Dependency | Why unused |
|------------|-----------|
| `ta>=0.11.0` | All indicators hand-rolled in `indicators.py` |
| `aiosqlite>=0.20.0` | DB uses synchronous SQLAlchemy |
| All 8 deps in `polymarket-bot/pyproject.toml` | Empty skeleton |

---

## Sprint History

| Sprint | What | Status | Date |
|--------|------|--------|------|
| 1 | Exchange Connection (CCXT → Binance testnet) | ✅ Done | 2026-02-19 |
| 2 | Data Layer (OHLCV, indicators, SQLite) | ✅ Done | 2026-02-19 |
| 3 | Grid Strategy (levels, signals, paper trading) | ✅ Done | 2026-02-19 |
| 4 | Order Execution (limit/market, position tracking) | ✅ Done | 2026-02-19 |
| 5 | AI Layer (LangChain, market analysis, grid optimization) | ✅ Done | 2026-02-20 |
| 6 | Integration (bot.py, backtesting, Telegram alerts) | ✅ Done | 2026-02-20 |
| 7 | Risk Management (sizing, stop-loss, limits, metrics) | ✅ Done | 2026-02-28 |
| 8 | Live Trading Prep (emergency stop, trade logging, PnL) | ✅ Done | 2026-03-01 |
| 9 | Web Dashboard (Streamlit + FastAPI) | ✅ Done | 2026-03-02 |
| 10 | UI/UX Improvements | ✅ Done | 2026-03-03 |
| 11 | Alerts & Monitoring (Discord, Telegram, Email) | ✅ Done | 2026-03-04 |
| 12 | Production Hardening (healthchecks, Prometheus, logging) | ✅ Done | 2026-03-05 |
| 13 | VPS Deployment (Docker, 24/7) | ✅ Done | 2026-03-05 |
| 14 | Monorepo Restructure | ✅ Done | 2026-03-05 |
| 15 | Factor Analysis Integration | ✅ Done | 2026-03-05 |
| 16 | Vector DB / News Sentiment | ✅ Done | 2026-03-05 |
| 17 | NautilusTrader Study & Setup | ⏭️ Skipped | — |
| 18 | Hyperparameter Optimization (Optuna) | ✅ Done | recent |
| 19 | Advanced Backtesting | ✅ Done | recent |
| 20 | Bidirectional Grid Trading | ✅ Done | recent |

### Planned

| Sprint | What | Priority |
|--------|------|----------|
| M2-M7 | Jesse bot development (see Jesse Bot Sprint Plan above) | HIGH |
| — | Polymarket Bot | MEDIUM |
| — | Stocks Bot (Interactive Brokers) | FUTURE |

### Decision: Jesse Framework (Decided 2026-03-07)

NautilusTrader was considered but **Jesse was chosen** as the trading framework for a parallel bot (`jesse-bot/`). Rationale: see `docs/analysis/jesse-comparison.md` and `docs/analysis/migration-plan.md`.

**Approach:** Build jesse-bot in parallel with binance-bot. Compare results. Best performer stays.

### Jesse Bot Sprint Plan

| Sprint | What | Status |
|--------|------|--------|
| M1 | Jesse Foundation (install, basic strategy, backtest) | ✅ Done (2026-03-08) |
| M2 | Grid Logic Refinement (bidirectional, TP/SL, trailing, multi-TF) | Planned |
| M3 | AI Integration (LLM agent as strategy mixin) | Planned |
| M4 | Sentiment + Factors Integration | Planned |
| M5 | Alerts + Dashboard Adaptation | Planned |
| M6 | Live Trading Setup | Planned |
| M7 | Cleanup + Optimization | Planned |

---

## Architecture Deep Dive

### Bot State Machine (bot.py)

```
                    ┌──────────┐
          start() → │ WAITING  │ ← AI says market bad
                    └────┬─────┘
                         │ AI approves entry
                    ┌────▼─────┐
                    │ TRADING  │ ← Main loop: grid signals → paper trades
                    └────┬─────┘
                         │ Risk limit hit / AI says pause
                    ┌────▼─────┐
                    │  PAUSED  │ → checks entry conditions periodically
                    └──────────┘
```

### Main Loop (every 5 seconds)

```
1. Check emergency stop
2. Fetch current price (CCXT)
3. Update alert rules engine
4. State-dependent:
   - WAITING: Check entry conditions every 5 min (AI analysis)
   - TRADING: Calculate grid signals → execute paper trades → risk checks
   - PAUSED: Check entry conditions every 5 min
5. Periodic AI review (every 15 min when TRADING)
6. Periodic news fetch (every 15 min)
7. Status log every 5 min
8. Write shared state (JSON) for API/dashboard
```

### Grid Trading Logic

```
1. AI analyzes market → sets grid center price and bounds
2. Grid levels created above and below center
3. Each level = limit order (buy below center, sell above)
4. When price crosses a level → paper trade executed
5. Opposite level created after fill
6. AI periodic review can: CONTINUE, PAUSE, ADJUST, STOP
```

### Data Flow

```
Binance (CCXT) → OHLCV/Ticker/OrderBook
       ↓
Indicators (SMA, EMA, RSI, BB, MACD, ATR)
       ↓
Factor Analysis (momentum, volatility, RSI signal, volume)
       ↓
News Sentiment (CryptoCompare/CoinGecko → ChromaDB → sentiment score)
       ↓
AI Agent (LangChain → OpenRouter/Claude) — analyzes all inputs
       ↓
Grid Strategy — creates/adjusts grid levels
       ↓
Paper Trading — simulated order execution
       ↓
Risk Management — position sizing, limits, drawdown
       ↓
Alerts (Discord) + Dashboard (Streamlit) + API (FastAPI)
```

---

## Development Setup

### Prerequisites

- Python 3.12+ (3.14 on server)
- Docker + Docker Compose
- Ollama with `nomic-embed-text` model (for news embeddings)

### Local Development

```bash
cd trading-bots/binance-bot

# Virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,dashboard]"

# Set PYTHONPATH (required for shared/ imports)
export PYTHONPATH=/path/to/trading-bots:/path/to/trading-bots/binance-bot/src

# Configure
cp .env.example .env
# Edit .env with API keys

# Run tests
pytest tests/ -v

# Run bot locally
python scripts/run_paper_trading.py

# Run dashboard
python scripts/run_dashboard.py
```

### Docker

```bash
cd binance-bot

# Development (hot reload)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up

# Production
docker compose -f docker-compose.prod.yml up -d

# Monitoring (Prometheus + Grafana)
docker compose -f docker-compose.monitoring.yml up -d
```

### Jesse Bot (Docker)

```bash
cd jesse-bot/docker

# Start jesse + postgres + redis
sg docker -c "docker compose up -d"

# Dashboard
open http://localhost:9000  # password: test

# Run tests (from host, no Redis needed)
cd jesse-bot
../.venv/bin/python -m pytest tests/ -v
```

### URLs (when running)

| Service | Local | Server |
|---------|-------|--------|
| binance-bot Dashboard | http://localhost:8501 | http://10.48.14.85:8501 |
| binance-bot API | http://localhost:8000 | http://10.48.14.85:8000 |
| binance-bot API Docs | http://localhost:8000/docs | http://10.48.14.85:8000/docs |
| **jesse-bot Dashboard** | **http://localhost:9000** | — |
| Prometheus | http://localhost:9090 | — |
| Grafana | http://localhost:3000 | — |

---

## Coding Guidelines

### Patterns Used

- **Pydantic Settings** for configuration (`shared/config/settings.py`)
- **loguru** for logging (every module)
- **SQLAlchemy** for database (synchronous, SQLite)
- **asyncio** for bot main loop and alerts
- **dataclasses** for data structures (Signal, GridLevel, etc.)
- **CCXT** for exchange connectivity

### Rules

1. All shared code goes in `shared/`, bot-specific code in `<bot-name>/src/`
2. Import shared modules as `from shared.X import Y`
3. Import bot modules as `from binance_bot.X import Y`
4. PYTHONPATH must include repo root AND bot `src/` dir
5. Configuration via `.env` files, never hardcode secrets
6. Use `loguru.logger` for logging (NOT stdlib logging)
7. Tests go in `tests/` at repo root

### CI

GitHub Actions runs `pytest tests/ -v --tb=short` on push/PR to main.
Python 3.12 in CI. Dependencies from `binance-bot/requirements.txt`.

---
## Module Dependency Map

```
binance-bot/src/binance_bot/
  bot.py ──────────► shared/core/{database, indicators, state}
    │                shared/ai/{agent}
    │                shared/alerts/{manager, rules}
    │                shared/config/settings
    │                shared/risk/{position_sizer, limits, metrics}
    │                shared/vector_db/{news_fetcher, sentiment}
    │                shared/monitoring/metrics
    │
    ├── strategies/
    │   ├── grid.py ──► shared/core/database
    │   ├── ai_grid.py ──► shared/ai, shared/factors
    │   └── base.py
    │
    └── core/
        ├── exchange.py ──► shared/config/settings
        ├── data_collector.py ──► shared/core/database
        ├── order_manager.py ──► shared/core/database
        ├── position_manager.py ──► shared/core/database
        └── emergency.py

shared/api/ ──────► shared/core/{database, state}
                    shared/alerts/{manager, rules}
                    shared/monitoring/metrics

shared/dashboard/ ─► shared/api (HTTP calls)
```

---

## Reference Materials

- `AUDIT.md` — detailed module-by-module audit (2026-03-06)
- `shared/REVIEW.md` — code review with scores (2026-03-05)
- `binance-bot/docs/project-plan.md` — full sprint plan with future sprints
- `binance-bot/docs/strategies.md` — 9 trading strategies documentation
- `binance-bot/docs/exchanges.md` — exchange comparison
- `binance-bot/docs/market-research-2024-2025.md` — market research
- `RESEARCH.md` — open-source trading tools comparison

---

## Stats

### binance-bot
- **Total Python LOC:** ~14,270
- **Test functions:** 255
- **Test files:** 19
- **Completed sprints:** 23
- **Bot uptime:** 24/7 on testnet since 2026-03-05
- **Live trading:** Not yet (still on testnet)

### jesse-bot
- **Test functions:** 28
- **Test files:** 1
- **Completed sprints:** M1
- **Framework:** Jesse 1.13.7 (Docker: jesse + postgres + redis)
