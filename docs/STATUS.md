# Project Status

**Last updated:** 2026-03-20

## Current State

**Phase:** Paper Trading (Binance Testnet)
**Bot status:** Running, auto-managed (AI pause/resume)
**Dashboard:** http://10.48.14.85:8501

### Metrics
- Total trades: 89 (paper)
- Strategies: Grid, Momentum, MeanReversion, Breakout (auto-selected by regime)
- Indicators: 50+ (trend, momentum, volatility, volume, support/resistance, patterns)
- Tests: 681
- Total commits: 120+
- Codebase: ~14,500 lines Python

### Infrastructure
- **Server:** ts1-rnd-llm01 (Docker)
- **Containers:** centric-void-01-app-service, centric-void-01-app-api, centric-void-01-app-dashboard
- **Exchange:** Binance Testnet (BTC/USDT)
- **AI Model:** MiniMax M2.5 via OpenRouter
- **Database:** SQLite (WAL mode)

### Completed Sprints (1-23)
1-14: Core bot, grid trading, monorepo structure
15: Market factors analysis
16: Vector DB for news sentiment
17: Testing infrastructure + CI/CD
18: Hyperparameter optimization (Optuna)
19: Advanced backtesting engine
20: Bi-directional grid (long + short)
21: TP/SL per grid level + trailing stop
22: Multi-strategy engine + regime detection
23: 50+ indicators + multi-timeframe

### Sprint 24 — P0 Runtime Crash Fixes (COMPLETED)
**Date:** 2026-03-12
**Branch:** `feature/sprint-24-p0-fixes`
**Issues fixed:** 26 P0 issues across 5 phases

| Phase | Focus | Issues |
|-------|-------|--------|
| 1 | Foundation (config, DB, state) | P0-CORE-1, P0-CORE-2, P0-CORE-3 |
| 2 | Indicators + factors (div/zero) | P0-CORE-4, P0-STRAT-1, P0-STRAT-2, P0-FACTORS-1 |
| 3 | Services (AI, alerts, risk, backtest, vector_db) | P0-AI-1, P0-AI-2, P0-ALERT-1, P0-ALERT-2, P0-RISK-1, P0-RISK-2, P0-BACK-1, P0-VDB-1, P0-VDB-2 |
| 4 | Bot & strategies | P0-BOT-1..4, P0-STRAT-3..6 |
| 5 | Jesse bot | P0-JESSE-1..3 |

Key changes:
- Settings: empty defaults for API keys + runtime validation
- 9 division-by-zero fixes across indicators (`.replace(0, np.nan)` + `fillna`)
- Lazy TradingAgent proxy (no import-time crash)
- DB session leak fix (try/except/finally)
- `float('inf')` → `9999.99` for JSON safety
- `asyncio.get_event_loop()` → `asyncio.get_running_loop()`
- Jesse candle column index 2 → 4 (high → close)
- 40+ new tests in `tests/unit/test_sprint24_p0.py`

### Sprint 25 — Jesse Bot Fixes (COMPLETED)
**Date:** 2026-03-12
**Branch:** `feature/sprint-25-jesse-fixes`
**Issues fixed:** 6 issues (4 P1, 2 P2)

| Phase | Issue | Severity | File | Fix |
|-------|-------|----------|------|-----|
| 1 | P1-JESSE-3 | P1 (CRITICAL) | `live_trader.py` | Only rebuild grid on direction change, not every iteration |
| 2 | P1-JESSE-4 | P1 | `live_trader.py` | Bounded `filled_order_ids` with deque(maxlen=500) |
| 3 | P1-JESSE-1 | P1 | `grid_logic.py` | `get_crossed_buy_level_price` now returns most recent fill |
| 4 | P1-JESSE-2 | P1 | `factors_mixin.py` | Fixed candle-to-dataframe column mapping for 5-col arrays |
| 5 | P2-JESSE-1 | P2 | `ai_mixin.py` | Parameterized hardcoded "BTCUSDT" symbol |
| 6 | P2-JESSE-2 | P2 | `ai_mixin.py` | Parameterized hardcoded total_balance=10000 |

Key changes:
- Grid state now persists across loop iterations (only rebuilds on trend change)
- `level_order_map` cleared on rebuild to prevent stale order matching
- `_last_filled_buy/sell` tracking in GridManager with serialization support
- `base_currency` derived from symbol instead of hardcoded "BTC"
- Symbol format conversion in callers: `"ETH-USDT"` → `"ETHUSDT"`
- 28 new tests in `tests/test_sprint25.py`

### Sprint 26 — Bot Logic & State Machine (COMPLETED)
**Date:** 2026-03-15
**Branch:** `feature/sprint-26-bot-logic`
**Issues fixed:** 13 (7 P1-BOT + 6 P1-STRAT)

| File | Issues | Changes |
|------|--------|---------|
| `bot.py` | P1-BOT-1,2,4,5,6,7,8 | PAUSED auto-resume fix, risk-gated dashboard resume, first AI review trigger, EMA 8/21 key match, actual PnL recording, ticker reuse, KeyboardInterrupt removal |
| `grid.py` | P1-STRAT-1,2 | Offset short levels in direction=both, _close_level trade recording |
| `order_manager.py` | P1-STRAT-4,5 | abs(amount) for short orders, order preservation on fetch failure |
| `position_manager.py` | P1-STRAT-7,8 | Short position tracking + unrealized PnL for shorts |

Key changes:
- PAUSED state now runs auto-resume logic (entry check + AI review)
- Dashboard resume blocked when risk limits breached
- PnL correctly calculated for sell/cover trades (risk limits now functional)
- Grid direction=both produces unique price levels (no duplicates)
- Short positions fully tracked in PositionManager with PnL
- 28 new tests in `tests/unit/test_sprint26_bot_logic.py`

### Sprint 27 — Risk Management Fixes (COMPLETED)
**Date:** 2026-03-17
**Branch:** `feature/sprint-27-risk`
**Issues fixed:** 10 (9 P1-RISK + 1 P1-BOT)

| File | Issues | Changes |
|------|--------|---------|
| `position_sizer.py` | P1-RISK-2 | Fixed risk_amount double-applying percentage |
| `metrics.py` | P1-RISK-3, P1-RISK-4, P1-RISK-9 | Sortino/profit factor sentinel for all-winning; sqrt(N) annualization |
| `limits.py` | P1-RISK-5, P1-RISK-6 | Max drawdown halt persists across days; drawdown from overall HWM |
| `trades.py` | P1-RISK-7, P1-RISK-8 | FIFO win/loss pairing; symbol filter applied to TradeLog queries |
| `stop_loss.py` | P1-RISK-10 | Composite key for multi-position per symbol; backward-compatible API |
| `state.py` + `bot.py` | P1-BOT-3 | strategy_engine field added to BotState; write before persist |

Key changes:
- Position sizing risk_amount no longer squared (was 0.04% instead of 2%)
- All-winning strategies now show sentinel 99.99 for Sortino/profit factor
- Max drawdown halt survives daily reset; drawdown measured from overall HWM
- Trade pairing uses FIFO instead of broken any()/all() logic
- StopLossManager supports multiple positions per symbol via composite keys
- Strategy engine status persisted in shared state file
- 33 new tests in `tests/unit/test_sprint27_risk.py`

### Sprint 28 — Alerts, API & Data Fixes (COMPLETED)
**Date:** 2026-03-19
**Branch:** `feature/sprint-28-alerts-api`
**Issues fixed:** 15 (7 P1 + 8 P2)

| Issue | Severity | File(s) | Fix |
|-------|----------|---------|-----|
| P1-ALERT-1 | P1 | `alerts/manager.py` | `datetime.now()` → `datetime.now(timezone.utc)` in rate limiter |
| P1-ALERT-2 | P1 | `alerts/rules.py` | `reversed()` iteration for most-recent price before cutoff |
| P1-ALERT-3 | P1 | `alerts/manager.py` | New `send_tp_sl_alert()` routed through AlertManager |
| P1-CORE-1 | P1 | `core/state.py` | TOCTOU fix: exception-based file read instead of exists() check |
| P1-CORE-2 | P1 | `core/state.py` | Atomic write via tempfile + os.replace |
| P1-CORE-3 | P1 | `core/indicators.py` | Early return for empty candle list in `to_dataframe()` |
| P1-CORE-4 | P1 | `core/database.py` | Lazy init: `get_engine()` / `get_session()` factories |
| P1-RISK-1 | P1 | `api/routes/orders.py` | Early return after state-file orders (no duplicate fallback) |
| P2-CORE-1 | P2 | 13+ files | All bare `datetime.now()` → `datetime.now(timezone.utc)` |
| P2-API-3 | P2 | `api/main.py` | CORS restricted to env-configurable origins |
| P2-API-6 | P2 | `api/auth.py` + routes | API key auth on write endpoints |
| P2-ALERT-1 | P2 | `alerts/discord.py` | `if current_price:` → `if current_price is not None:` |
| P2-RISK-1 | P2 | `risk/limits.py` | `trade_history` bounded to deque(maxlen=1000) |
| P2-RISK-2 | P2 | `risk/metrics.py` | `equity_curve` bounded to deque(maxlen=10000) |
| P2-BOT-1 | P2 | `config/settings.py` + bot/dashboard | `paper_initial_balance` from settings, not hardcoded |

Key changes:
- All datetime operations now timezone-aware (UTC) across entire codebase
- Database module no longer creates dirs/connections at import time
- File-based IPC is race-condition-free (atomic write + exception-based read)
- CORS and API auth properly secured
- Memory leak vectors eliminated (bounded deques for trade history + equity curve)
- 31 new tests in `tests/unit/test_sprint28_alerts_api.py`

### Current Sprint Plan (24-31)
Based on Audit V2 (118 issues found):
- **Sprint 24:** P0 runtime crash fixes ✅
- **Sprint 25:** Jesse bot fixes ✅
- **Sprint 26:** Bot logic & state machine ✅
- **Sprint 27:** Risk management fixes ✅
- **Sprint 28:** Alerts, API & data consistency ✅
- **Sprint 29:** Architecture & decoupling ✅
- **Sprint 30:** Code quality & cleanup ✅
- **Sprint 31:** Simplification + full regression

See `docs/SPRINT_PLAN.md` for details.

### Sprint 29 — Architecture & Decoupling (COMPLETED)
**Date:** 2026-03-20
**Branch:** `feature/sprint-29-architecture`
**Issues fixed:** 11 (4 P1-STRAT + 3 P1-AI + 1 P1-BACK + 1 P1-DASH + 1 P3-STRAT)

| Issue | Severity | File(s) | Fix |
|-------|----------|---------|-----|
| P1-BACK-1 | P1 | `shared/backtest/engine.py`, `shared/optimization/optimizer.py` | Late imports + TYPE_CHECKING for binance_bot deps |
| P1-STRAT-3 | P1 | `order_manager.py`, `base.py` | Added `symbol` field to Signal; `execute_signal` uses `signal.symbol` |
| P1-STRAT-6 | P1 | `exchange.py` | `_retry_on_network_error` decorator on all exchange methods |
| P1-STRAT-9 | P1 | `emergency.py` | Paths use `BOT_DATA_DIR` env var via `_DATA_DIR` |
| P1-STRAT-10 | P1 | `ai_grid.py` | Relative tolerance `max(price * 0.001, 0.001)` replaces hardcoded 0.01 |
| P1-STRAT-11 | P1 | `ai_grid.py` | Balanced-brace JSON extractor replaces `[^{}]+` regex |
| P1-AI-1 | P1 | `shared/ai/agent.py` | Negation-aware keyword matching (within 5-word window) |
| P1-AI-2 | P1 | `shared/ai/agent.py` | `assess_risk()` docstring documents jesse-bot caller |
| P1-AI-3 | P1 | `shared/ai/agent.py` | JSON-first parsing in all 4 LLM parsers with string fallback |
| P1-DASH-1 | P1 | `shared/dashboard/app.py` | Timestamp-based rerun replaces `time.sleep()` |
| P3-STRAT-3 | P3 | `grid.py` | Inline EMA/RSI/ADX/ATR replaced with `shared/indicators/` calls |

Key changes:
- `shared/` no longer imports `binance_bot` at module level (breaks circular dep)
- All LLM response parsers try structured JSON extraction before string matching
- Negation patterns like "not bullish" no longer false-positive as bullish
- Grid indicator calculations consolidated into `shared/indicators/` (net ~50 lines removed)
- 45 new tests in `tests/unit/test_sprint29_architecture.py`

### Sprint 30 — Code Quality & Cleanup (COMPLETED)
**Date:** 2026-03-20
**Branch:** `feature/sprint-30-cleanup`
**Issues fixed:** 15 (13 P3 + 1 P1 + 1 P2) — 3 audit claims validated as invalid

| Issue | Severity | File(s) | Fix |
|-------|----------|---------|-----|
| P3-BOT-1 | P3 | `bot.py` | Removed unused `read_state` import, added `read_command` at file level |
| P3-BOT-2 | P3 | `bot.py` | Removed unused `old_state` variable |
| P3-BOT-3 | P3 | `bot.py` | Moved `read_command` import from inside loop to file level |
| P3-BOT-4 | P3 | `bot.py` | Removed duplicate `_write_shared_state(current_price=None)` call |
| P3-STRAT-1 | P3 | `data_collector.py`, `position_manager.py` | Removed 4 unused imports (`delete`, `field`, 2× `datetime`) |
| P3-STRAT-2 | P3 | `position_manager.py` | Removed unused `pnl_color` variable |
| P3-ALERT-2 | P3 | `alerts/discord.py`, `alerts/manager.py` | Added `trades_list` param propagation to Discord adapter |
| P3-API-2 | P3 | `api/routes/orders.py` | Extracted `_force_trade()` helper to deduplicate force_buy/force_sell |
| P3-API-3 | P3 | `risk/metrics.py` | Extracted `_compute_drawdowns()` to deduplicate drawdown computation |
| P3-BACK-1 | P3 | `backtest/charts.py` | Removed unused `colors` variable |
| P3-BACK-2 | P3 | `backtest/charts.py` | Removed unused `numpy` import |
| P3-JESSE-1 | P3 | `AIGridStrategy/__init__.py` | Removed duplicate `logger` assignment |
| P3-JESSE-2 | P3 | `AIGridStrategy/ai_mixin.py` | Replaced deprecated `asyncio.get_event_loop()` with `get_running_loop()` |
| P3-JESSE-3 | P3 | `live_trader.py` | Removed unused `atr` parameter from `setup_grid` |
| P1-MON-1 | P1 | `monitoring/metrics.py` | Removed `__new__` singleton, kept `get_metrics()` factory |
| P2-CORE-4 | P2 | `core/database.py` | Removed duplicate `index=True` on `TradeLog.timestamp` |

Key changes:
- Dead code, unused imports, and unused variables removed across 12 files
- Duplicate logic refactored with DRY helper methods (force trades, drawdowns)
- Singleton pattern simplified (factory function only)
- Deprecated asyncio API replaced
- Duplicate database index removed
- 3 invalid audit claims documented (P3-STRAT-1 grid.py, P3-API-1, P3-ALERT-1)
- 29 new tests in `tests/unit/test_sprint30_cleanup.py`
- Tests: 681 (all passing)

### Known Issues
See `docs/AUDIT_V2.md` for full list (118 items, P0-P3).

### Next Milestones
1. Complete Sprints 24-31 (fix all audit issues)
2. Achieve >80% test coverage
3. Live trading with small capital ($50-100)
