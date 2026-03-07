# AGENTS.md — Trading Bots Monorepo

> Context document for AI agents working on this codebase.
> Read this file first before making any changes.

### Maintenance Rule
**After fixing any bug, issue, or task listed in this file — remove its entry from AGENTS.md and add a note to CHANGELOG.md.** Keep this file clean and current. If CHANGELOG.md doesn't exist, create it.

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
├── polymarket-bot/            # Prediction Markets Bot (EMPTY SCAFFOLD)
│   ├── src/polymarket_bot/    # Only __init__.py files
│   └── Dockerfile
│
├── tests/                     # 255 test functions across 19 files
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

### Planned (from project-plan.md)

| Sprint | What | Priority |
|--------|------|----------|
| 17 | NautilusTrader Study & Setup | HIGH (decision pending) |
| 18-20 | NautilusTrader Grid + AI + Live | HIGH (if migrating) |
| 21 | Polymarket Bot | MEDIUM |
| 22 | Stocks Bot (Interactive Brokers) | FUTURE |
| 23 | Rust Core Performance | FUTURE |
| — | Factor/Strategy Framework from QuantMuse | FUTURE |
| — | API Gateway & Caching (Redis) | FUTURE |

### Key Decision Pending: NautilusTrader Migration

The project plan has a migration path to NautilusTrader (Sprints 17-23) as the production platform. NautilusTrader offers:
- Rust core (<1ms latency)
- Ready-made adapters: Binance, Polymarket, Interactive Brokers, Bybit, OKX
- Professional backtesting, risk management, order management

However, Sprints 18-20 were built on the current custom architecture instead. **The team needs to decide: migrate to NautilusTrader or continue building on the current stack.**

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

### URLs (when running)

| Service | Local | Server |
|---------|-------|--------|
| Dashboard | http://localhost:8501 | http://10.48.14.85:8501 |
| API | http://localhost:8000 | http://10.48.14.85:8000 |
| API Docs | http://localhost:8000/docs | http://10.48.14.85:8000/docs |
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

## Priority Task List

### P0 — Fix Broken Things

1. **Wire StopLossManager into bot.py trading loop** — the code exists in `shared/risk/stop_loss.py`, it's imported and instantiated, but no methods are called during `_execute_trading()`. Add SL/TP checks after each trade.

2. **Fix Discord retry stack overflow** — `shared/alerts/discord.py`: replace recursive `_send_webhook()` call on 429 with a loop + max retries (3-5).

3. **Add LLM timeout** — `ai_grid.py` `_call_llm()`: add `timeout=30` or similar to prevent blocking the bot loop.

4. **Add SMTP timeout** — `shared/alerts/email.py`: pass `timeout=30` to `aiosmtplib.send()`.

5. **Fix f-string crash** — `shared/alerts/manager.py` ~line 248: handle `current_price=None`.

### P1 — Complete Integrations

6. **Wire Telegram into AlertManager** — or delete `telegram.py` if not needed.

7. **Verify Prometheus metrics** — `bot.py` calls `self.trading_metrics.record_trade()` but verify the metrics endpoint actually serves non-zero data.

8. **Wire StopLossManager** — call `check_stop_loss()` and `check_take_profit()` in the trading loop.

### P2 — Code Quality

9. **Replace `datetime.utcnow()`** with `datetime.now(timezone.utc)` — 7+ occurrences.

10. **Use Decimal for financial amounts** — at minimum in `Trade.amount` and grid level amounts.

11. **Fix LLM response parsing** — use JSON mode or structured output instead of line-by-line string parsing.

12. **Add grid level cap** — `grid.py` `_create_opposite_level()` needs a max levels limit.

13. **Fix Streamlit `width="stretch"`** — replace with `use_container_width=True` in 9 places.

14. **Move risk params to config** — hardcoded `risk_per_trade=0.02`, `daily_loss_limit=0.05`, etc. in `bot.py` should come from `settings.py`.

### P3 — Cleanup

15. **Delete dead files:** `shared/reports/`, `shared/utils/`, `binance-bot/src/binance_bot/main.py`
16. **Remove unused imports** — see AUDIT.md for full list
17. **Remove unused deps:** `ta`, `aiosqlite` from requirements
18. **Clean polymarket-bot** — implement or remove the skeleton

### P4 — Strategic

19. **Decide on NautilusTrader** — migrate (rewrite on professional platform) or continue custom?
20. **Move to mainnet** — small capital ($50-100), real money testing
21. **Add CHANGELOG.md** — track changes between versions
22. **Add Alembic** — database migrations for schema changes

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

- **Total Python LOC:** ~14,270
- **Test functions:** 255
- **Test files:** 19
- **Completed sprints:** 18 (of planned 23+)
- **Bot uptime:** 24/7 on testnet since 2026-03-05
- **Live trading:** Not yet (still on testnet)
