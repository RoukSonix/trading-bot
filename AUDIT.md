# Trading-Bots Monorepo Audit

**Date:** 2026-03-06
**Scope:** Functionality, dead code, integration wiring, unused dependencies

---

## 1. Functionality Status

### shared/core/

| Module | Status | Notes |
|--------|--------|-------|
| `database.py` | ✅ Working | SQLAlchemy/SQLite. Tables: OHLCV, Trade, Position, TradeLog. Heavily used (7 consumers). |
| `indicators.py` | ✅ Working | RSI, SMA, EMA, Bollinger, MACD, ATR all implemented via pandas. Used by 4+ consumers. |
| `state.py` | ✅ Working | JSON file-based inter-process state sharing. BotState, GridLevel, Position dataclasses. Used by 4 consumers. |

**Issues found:**
- `datetime.utcnow()` used in 7 places — deprecated in Python 3.12+, will be removed in future versions
- Module-level side effects: importing `database.py` creates `data/` dir and opens SQLite connection
- `state.BotState.from_dict()` mutates the input dictionary via `.pop()`
- Name collision: both `database.py` and `state.py` define a `Position` class with different shapes
- `GridLevel` / `Position` dataclasses in `state.py` are never actually instantiated (raw dicts used instead)

### shared/ai/

| Module | Status | Notes |
|--------|--------|-------|
| `agent.py` | ✅ Working | OpenRouter via LangChain ChatOpenAI. 4 capabilities: market analysis, grid optimization, risk assessment, signal confirmation. Graceful degradation when API key missing. |
| `prompts.py` | ✅ Working | All 4 prompt templates are used by agent.py. |

**Issues found:**
- `assess_risk()` method + `RiskAssessment` dataclass: fully implemented but never called anywhere — dead code
- `ai_grid.py` `periodic_review()` calls `trading_agent._call_llm()` directly (private method access)

### shared/alerts/

| Module | Status | Notes |
|--------|--------|-------|
| `discord.py` | ✅ Working | Async webhook via aiohttp. Trade alerts, status, errors, daily summary. Primary alert channel. |
| `email.py` | ✅ Working | Async SMTP via aiosmtplib. Wired into AlertManager as secondary channel. Disabled by default (`email_enabled=False`). |
| `telegram.py` | ❌ Disconnected | Fully implemented but **completely orphaned** — AlertManager does not route to it, no consumer imports it. |
| `manager.py` | ✅ Working | Central orchestrator with rate limiting, per-type dedup, daily summary scheduler. Routes to Discord + Email only. |
| `rules.py` | ✅ Working | Alert rules engine with price, volume, PnL thresholds. Used by bot.py. |

**Issues found:**
- **Telegram is dead code** — the entire module is never imported by any consumer
- `telegram = TelegramAlerter()` at module level causes eager initialization on package import (potential ImportError if `python-telegram-bot` not installed)
- Recursive retry in `discord.py` on HTTP 429 — unbounded recursion, stack overflow risk
- `silent` flag lost on Discord retry (not forwarded in recursive call)
- No SMTP timeout in `email.py` — `aiosmtplib.send()` can block indefinitely
- Broken f-string in `manager.py` status email (lines 248-249) — `TypeError` when `current_price` is None
- `AlertType` enum defined but never used
- `RuleType.CUSTOM` has no evaluation handler

### shared/factors/ (Sprint 15)

| Module | Status | Notes |
|--------|--------|-------|
| `factor_calculator.py` | ✅ Working | 4 factor groups: momentum, volatility, RSI, volume. Composite score with configurable weights. |
| `factor_strategy.py` | ✅ Working | Market regime detection, grid suitability scoring, grid action recommendations. |

| Integration | Status |
|-------------|--------|
| Wired into AIGridStrategy? | ⚠️ **Code exists but DISCONNECTED** |
| Wired into base GridStrategy? | ❌ None |

**CRITICAL: The factor system is never executed in the live trading flow.** `bot.py:_check_entry_conditions()` calls `strategy.analyze_and_setup()` but does NOT pass `ohlcv_df`. The factor analysis block is gated on `if ohlcv_df is not None` (defaults to `None`). The OHLCV data exists in `_fetch_market_data()` but is not included in its return dict.

**Fix required:** Two changes in `bot.py`:
1. Add `"ohlcv_df": ohlcv_df` to `_fetch_market_data()` return dict
2. Pass `ohlcv_df=data["ohlcv_df"]` in `_check_entry_conditions()` call

**Dead code within factors:**
- `calculate_from_candles()` — never called
- `to_dict()` — never called (strategy uses `to_ai_context()` instead)
- `analyze_and_score()` — only used in tests, not production

### shared/vector_db/ (Sprint 16)

| Module | Status | Notes |
|--------|--------|-------|
| `embeddings.py` | ✅ Working | Correctly uses Ollama `nomic-embed-text` via `langchain_ollama.OllamaEmbeddings`. No sentence-transformers dependency. |
| `vector_store.py` | ✅ Working | ChromaDB `PersistentClient` with cosine distance. Upsert support. |
| `news_fetcher.py` | ✅ Working | Two sources: CryptoCompare News API + CoinGecko Trending. Rate limiting, dedup, parallel fetch. |
| `sentiment.py` | ✅ Working | Keyword-based sentiment analysis. Trading signal generation with RSI confluence. 13 tests passing. |

| Integration | Status |
|-------------|--------|
| Wired into bot decision-making? | ❌ **Completely disconnected** |

**CRITICAL: The entire vector_db module produces zero effect on trading decisions.** The complete pipeline exists but nobody calls it:

```
news_fetcher.fetch_all()           — NEVER called by bot
     ↓
vector_store.add_with_embeddings() — NEVER called by bot
     ↓
vector_store.query()               — NEVER called by bot
     ↓
sentiment_analyzer.analyze()       — NEVER called by bot
     ↓
sentiment_analyzer.to_ai_context() — NEVER called by bot
     ↓
ai_grid.analyze_and_setup(news_sentiment_context=...) — ALWAYS receives ""
```

**Fix required:** The bot loop needs a pre-analysis step that fetches news, generates embeddings, queries for relevant articles, runs sentiment analysis, and passes the context string to `analyze_and_setup()`.

**Remaining sentence-transformers references:**
- `news_fetcher.py:258` — parameter named `use_sentence_transformers` (misleading, actually triggers Ollama)
- `binance-bot/docs/project-plan.md:513` — stale documentation

**Dead code:**
- `lru_cache` import in `embeddings.py` — unused
- `Optional` import in `embeddings.py` — unused

### shared/dashboard/

| Module | Status | Notes |
|--------|--------|-------|
| `app.py` | ✅ Working | Streamlit frontend. All 5 component types rendered. Full API integration. |
| `grid_view.py` | ✅ Working | Plotly grid visualization |
| `candlestick_chart.py` | ✅ Working | OHLCV candlestick with optional grid overlay |
| `order_book.py` | ✅ Working | Buy/sell order visualization |
| `pnl_chart.py` | ✅ Working | Cumulative and daily PnL charts |
| `trade_table.py` | ✅ Working | Trade history with summary stats |

### shared/api/

| Module | Status | Notes |
|--------|--------|-------|
| `main.py` | ✅ Working | FastAPI app with 20+ endpoints. CORS, health checks, Prometheus metrics endpoint. |
| `routes/` | ✅ Working | bot, candles, orders, positions, trades — all endpoints return structured data |

**Issues found:**
- `width="stretch"` used in 9 Streamlit call sites — not a valid parameter (should be `use_container_width=True`). Charts may not fill container width.
- `time.sleep()` for auto-refresh blocks the Streamlit main thread
- Potential duplicate orders in `/api/orders` GET when both state file and bot instance are present
- 3 unused component methods: `render_mini()`, `render_compact()` (x2)
- Unused imports: `plotly.express`, `datetime`, `timedelta`, `Optional` in `pnl_chart.py`; `datetime` in `app.py`

### Other Modules

| Module | Status | Notes |
|--------|--------|-------|
| `shared/config/settings.py` | ✅ Working | Pydantic Settings with .env support. Used by 6+ consumers. |
| `shared/risk/` | ⚠️ Partial | `PositionSizer`, `RiskLimits`, `RiskMetrics` imported and used by bot.py. **But `StopLossManager` is instantiated and never called.** |
| `shared/backtest/engine.py` | ✅ Working | Used by `run_backtest.py` and `run_backtest_series.py`. |
| `shared/monitoring/metrics.py` | ⚠️ Partial | Prometheus metrics defined, `/metrics` endpoint exists, but **bot never records data** — all metrics stay at zero. |
| `shared/reports/pnl.py` | ❌ Orphaned | `PnLReporter` class never imported by any consumer. |
| `shared/utils/logging_config.py` | ❌ Orphaned | Never imported. Every file rolls its own loguru setup. |
| `polymarket-bot/` | ❌ Empty skeleton | Zero functional code. Only `__init__.py` files with docstrings. All 8 dependencies unused. |

---

## 2. Dead Code List

### Files to Delete (completely orphaned)

| File/Directory | Reason |
|----------------|--------|
| `shared/reports/pnl.py` | Never imported anywhere |
| `shared/reports/__init__.py` | Never imported anywhere |
| `shared/utils/logging_config.py` | Never imported; every consumer has inline loguru setup |
| `shared/utils/__init__.py` | Only imports from orphaned logging_config |
| `shared/alerts/telegram.py` | AlertManager does not route to it; no consumer imports it |
| `binance-bot/src/binance_bot/main.py` | Sprint 4 test script, not real entry point (bot uses `bot.py`) |

### Dead Code Within Active Files

| File | Dead Code | Line(s) |
|------|-----------|---------|
| `shared/ai/agent.py` | `assess_risk()` method + `RiskAssessment` dataclass | ~335-423, ~69-76 |
| `shared/core/indicators.py` | `from typing import Optional` (unused import) | 5 |
| `shared/core/indicators.py` | `from loguru import logger` (unused import) | 6 |
| `shared/core/indicators.py` | `import numpy as np` (unused import) | 4 |
| `shared/core/indicators.py` | `indicators = Indicators()` (module-level instance, never imported) | 203 |
| `shared/core/state.py` | `delete_state()` function (never called) | ~141-147 |
| `shared/core/state.py` | `GridLevel` dataclass (never instantiated) | ~21-27 |
| `shared/core/state.py` | `Position` dataclass (never instantiated, shadowed by database.Position) | ~31-38 |
| `shared/factors/factor_calculator.py` | `calculate_from_candles()` method | ~230-247 |
| `shared/factors/factor_calculator.py` | `to_dict()` method | ~249-267 |
| `shared/vector_db/embeddings.py` | `from functools import lru_cache` (unused) | 13 |
| `shared/vector_db/embeddings.py` | `from typing import Optional` (unused) | 14 |
| `shared/dashboard/components/pnl_chart.py` | `import plotly.express as px` (unused) | 5 |
| `shared/dashboard/components/pnl_chart.py` | `from datetime import datetime, timedelta` (unused) | 8 |
| `shared/dashboard/components/pnl_chart.py` | `from typing import Optional` (unused) | 6 |
| `shared/dashboard/app.py` | `from datetime import datetime` (unused) | 6 |
| `shared/dashboard/app.py` | `direction` variable in `render_price_ticker()` (assigned, never read) | ~144 |
| `shared/alerts/manager.py` | `from typing import ... Any` (unused) | 7 |
| `shared/alerts/manager.py` | `AlertType` enum (never referenced) | 24 |
| `shared/monitoring/metrics.py` | All `TradingMetrics` methods (never called by bot) | entire class |
| `bot.py` | `self.stop_loss_mgr` (StopLossManager instantiated, never used) | init |

### Unused Dependencies

| Dependency | Location | Reason |
|------------|----------|--------|
| `ta>=0.11.0` | `binance-bot/requirements.txt`, `pyproject.toml` | Never imported. All TA indicators are hand-rolled in `indicators.py`. |
| `aiosqlite>=0.20.0` | `binance-bot/requirements.txt`, `pyproject.toml` | Never imported. Database uses synchronous SQLAlchemy. |
| All 8 deps in `polymarket-bot/pyproject.toml` | `polymarket-bot/` | Empty skeleton project with zero code. |

---

## 3. Missing Integrations

### CRITICAL: Sprint 15 Factors Not Wired In

**Status:** Code complete but disconnected at the call site.

The `FactorCalculator` and `FactorStrategy` are fully implemented and imported by `AIGridStrategy`. However, `bot.py:_check_entry_conditions()` never passes `ohlcv_df` to `analyze_and_setup()`, so the entire factor analysis branch (`if ohlcv_df is not None`) is dead in production.

**Impact:** Zero factor-based intelligence in live trading decisions.

### CRITICAL: Sprint 16 Vector DB / News Sentiment Not Wired In

**Status:** All modules implemented and tested in isolation, but completely disconnected from the bot flow.

No production code:
- Fetches news
- Generates embeddings
- Queries the vector store
- Runs sentiment analysis
- Passes results to the AI agent

**Impact:** Zero news/sentiment intelligence in live trading decisions.

### Telegram Alerts Disconnected

`AlertManager` routes to Discord and Email only. `TelegramAlerter` exists but is never registered as a channel.

### Prometheus Metrics Never Populated

The `/metrics` endpoint exists and Prometheus metric objects are defined, but the bot never calls `TradingMetrics.record_trade()`, `record_error()`, etc. All metrics remain at zero.

### StopLossManager Instantiated But Never Used

`bot.py` creates `self.stop_loss_mgr` but never calls any of its methods in the trading loop.

---

## 4. Recommendations

### Priority 1 — Wire Up Sprint 15 & 16 Features

1. **Fix factor integration** (2 lines in `bot.py`):
   - Add `"ohlcv_df": ohlcv_df` to `_fetch_market_data()` return dict
   - Pass `ohlcv_df=data["ohlcv_df"]` in `_check_entry_conditions()` call

2. **Wire up vector_db / news sentiment** (new code in bot loop):
   - Add a periodic news fetch step using `news_fetcher.fetch_and_store()`
   - Query recent articles, run `sentiment_analyzer.analyze_articles()`
   - Pass `sentiment_analyzer.to_ai_context()` result as `news_sentiment_context` to `analyze_and_setup()`

### Priority 2 — Fix Bugs

3. **Fix Discord retry** — replace recursive `_send_webhook()` with loop + max retries
4. **Fix broken f-string** in `manager.py` status email (TypeError when price is None)
5. **Add SMTP timeout** to `email.py`
6. **Rename `use_sentence_transformers`** parameter in `news_fetcher.py` to `use_ollama_embeddings`

### Priority 3 — Clean Up Dead Code

7. Delete orphaned files: `shared/reports/`, `shared/utils/`, `shared/alerts/telegram.py`, `binance-bot/src/binance_bot/main.py`
8. Remove unused imports across `indicators.py`, `embeddings.py`, `pnl_chart.py`, `app.py`, `manager.py`
9. Remove unused dependencies: `ta`, `aiosqlite`
10. Fix `width="stretch"` to `use_container_width=True` in 9 Streamlit call sites

### Priority 4 — Technical Debt

11. Replace `datetime.utcnow()` with `datetime.now(timezone.utc)` (7 occurrences in `database.py`, plus alert files)
12. Wire `StopLossManager` into the trading loop or remove it
13. Wire `TradingMetrics` recording into the bot or remove Prometheus metrics
14. Decide on Telegram: wire into AlertManager or delete
15. Make database initialization lazy (avoid side effects on import)

### Priority 5 — Polymarket Bot

16. Either implement `polymarket-bot/` or remove the skeleton to avoid confusion

---

## Appendix: Module Dependency Map

```
binance-bot/src/binance_bot/
  bot.py ──────────► shared/core/{database, indicators, state}
    │                shared/ai/{agent}
    │                shared/alerts/{manager, rules}
    │                shared/config/settings
    │                shared/risk/{position_sizer, limits, metrics, stop_loss}
    │
    ├── strategies/
    │   ├── grid.py ──► shared/core/database
    │   ├── ai_grid.py ──► shared/ai, shared/factors  ← factors disconnected
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

shared/dashboard/ ─► shared/api (HTTP)

shared/vector_db/ ─► (ORPHANED — nobody imports this in production)
shared/reports/ ───► (ORPHANED — nobody imports this)
shared/utils/ ─────► (ORPHANED — nobody imports this)
```
