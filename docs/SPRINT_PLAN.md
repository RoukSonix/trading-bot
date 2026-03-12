# Sprint Plan — Audit V2 Fixes

**Based on:** AUDIT_V2.md (118 issues)
**Approach:** Fix by priority, each sprint includes tests
**Final sprint:** Code simplification + full regression

---

## Sprint 24: Critical Runtime Fixes (P0)
**Goal:** Eliminate all crashes and data corruption
**Issues:** 28 P0 items
**Estimated:** ~15 files, ~200 lines changed

| Issue | Description | Files |
|-------|-------------|-------|
| P0-STRAT-1 | Division by zero in RSI (4 locations) | grid.py, momentum.py, factors_mixin.py |
| P0-STRAT-2 | Division by zero in ADX (2 locations) | grid.py, trend.py |
| P0-STRAT-3 | Division by zero when num_levels=0 | ai_grid.py |
| P0-STRAT-4 | DB session leak in _save_trade_to_db | grid.py |
| P0-STRAT-5 | Bare `except:` swallows SystemExit | order_manager.py |
| P0-STRAT-6 | Missing rollback on DB commit failure | order_manager.py |
| P0-AI-1 | ZeroDivisionError when best_bid=0 | agent.py |
| P0-AI-2 | Module-level TradingAgent() crashes | agent.py |
| P0-ALERT-1 | Fragile co_varnames in AlertConfig | manager.py |
| P0-ALERT-2 | Invalid daily_summary_time infinite loop | manager.py |
| P0-CORE-1 | Settings() crashes without env vars | settings.py |
| P0-CORE-2 | from_dict() mutates caller's dict | state.py |
| P0-CORE-3 | Decimal not JSON-serializable | database.py |
| P0-CORE-4 | Division by zero in 8+ indicators | indicators/*.py |
| P0-RISK-1 | NameError in get_pnl_summary | trades.py |
| P0-RISK-2 | ZeroDivisionError in position_sizer | position_sizer.py |
| P0-BACK-1 | float('inf') in profit_factor crashes JSON | engine.py, metrics.py |
| P0-BOT-1 | asyncio.get_event_loop() deprecated | bot.py |
| P0-BOT-2 | Unhandled network error during startup | bot.py |
| P0-BOT-3 | ticker["last"] can be None | bot.py |
| P0-BOT-4 | _print_stats KeyError paper_trading | bot.py |
| P0-VDB-1 | Timezone mismatch in news_fetcher sort | news_fetcher.py |
| P0-VDB-2 | Timezone mismatch in sentiment comparison | sentiment.py |

**Tests:**
- Division by zero edge cases for all indicators
- Settings initialization with/without env vars
- JSON serialization of Decimal/inf values
- Null ticker handling
- DB session lifecycle (leak test)

---

## Sprint 25: Jesse Bot Fixes
**Goal:** Fix jesse-bot critical bugs
**Issues:** 5 items (P0-JESSE + P1-JESSE)

| Issue | Description | Files |
|-------|-------------|-------|
| P0-JESSE-1 | Wrong candle column index (HIGH vs CLOSE) | __init__.py |
| P0-JESSE-2 | _side accessed before assignment | grid_logic.py |
| P0-JESSE-3 | Division by zero in RSI | factors_mixin.py |
| P1-JESSE-3 | Live trader rebuilds grid every iteration | live_trader.py |
| P1-JESSE-4 | filled_order_ids grows unboundedly | live_trader.py |
| P1-JESSE-1 | get_crossed_buy_level_price returns wrong level | grid_logic.py |
| P1-JESSE-2 | Fragile candle-to-dataframe mapping | factors_mixin.py |
| P2-JESSE-1 | Hardcoded "BTCUSDT" in AI mixin | ai_mixin.py |
| P2-JESSE-2 | Hardcoded total_balance=10000 | ai_mixin.py |

**Tests:**
- Candle column index verification
- Grid rebuild frequency (should persist state)
- Order ID set bounds

---

## Sprint 26: Bot Logic & State Machine
**Goal:** Fix trading logic, state transitions, PnL recording
**Issues:** 12 P1-BOT + P1-STRAT items

| Issue | Description | Files |
|-------|-------------|-------|
| P1-BOT-1 | PAUSED auto-resume is dead code | bot.py |
| P1-BOT-2 | Dashboard resume bypasses risk checks | bot.py |
| P1-BOT-4 | _maybe_ai_review skips first review | bot.py |
| P1-BOT-5 | EMA period mismatch (8/21 vs 12/26) | bot.py |
| P1-BOT-6 | PnL always 0, risk limits disabled | bot.py |
| P1-BOT-7 | _fetch_market_data called redundantly | bot.py |
| P1-BOT-8 | KeyboardInterrupt dead code in async | bot.py |
| P1-STRAT-1 | Duplicate grid levels with direction=both | grid.py |
| P1-STRAT-2 | _close_level bypasses trade recording | grid.py |
| P1-STRAT-4 | Negative amount for short orders | order_manager.py |
| P1-STRAT-5 | Orders deleted on fetch failure | order_manager.py |
| P1-STRAT-7 | PositionManager only handles longs | position_manager.py |
| P1-STRAT-8 | Unrealized PnL only for longs | position_manager.py |

**Tests:**
- State machine transitions (all BotState combinations)
- PnL recording for grid trades
- Position manager short/long handling
- Resume with active risk limits

---

## Sprint 27: Risk Management Fixes
**Goal:** Fix all risk calculation bugs
**Issues:** 10 P1-RISK items

| Issue | Description | Files |
|-------|-------------|-------|
| P1-RISK-2 | risk_amount double-applies percentage | position_sizer.py |
| P1-RISK-3 | Sortino 0.0 for all-winning | metrics.py |
| P1-RISK-4 | Profit factor 0.0 for all-winning | metrics.py |
| P1-RISK-5 | Max drawdown auto-resets daily | limits.py |
| P1-RISK-6 | Drawdown uses daily HWM not overall | limits.py |
| P1-RISK-7 | Win/loss pairing logic broken | trades.py |
| P1-RISK-8 | Symbol filter ignored for TradeLog | trades.py |
| P1-RISK-9 | Sharpe/Sortino annualization wrong | metrics.py |
| P1-RISK-10 | StopLossManager one position per symbol | stop_loss.py |
| P1-BOT-3 | strategy_engine data never persisted | bot.py |

**Tests:**
- Position sizing with various risk percentages
- Sortino/Sharpe with edge cases (all wins, all losses, mixed)
- Drawdown across multi-day periods
- Win/loss pairing with FIFO accounting

---

## Sprint 28: Alerts, API & Data Fixes
**Goal:** Fix alerts, API issues, data consistency
**Issues:** P1-ALERT + P1-CORE + P2 items

| Issue | Description | Files |
|-------|-------------|-------|
| P1-ALERT-1 | Naive vs aware datetime mixing | manager.py |
| P1-ALERT-2 | Price movement iterates wrong direction | rules.py |
| P1-ALERT-3 | send_tp_sl_alert not wired | discord.py, manager.py |
| P1-CORE-1 | read_command TOCTOU race | state.py |
| P1-CORE-2 | write_command not atomic | state.py |
| P1-CORE-3 | Indicators crash on empty candles | indicators.py |
| P1-CORE-4 | Module-level side effects in database.py | database.py |
| P1-RISK-1 | Duplicate orders in API | orders.py |
| P2-CORE-1 | datetime.now() without timezone (30+ places) | everywhere |
| P2-API-3 | CORS allows all origins | main.py |
| P2-API-6 | No auth on trading endpoints | main.py, routes/* |
| P2-ALERT-1 | Truthiness check on current_price | discord.py |
| P2-RISK-1 | trade_history unbounded (memory leak) | limits.py |
| P2-RISK-2 | equity_curve unbounded (memory leak) | metrics.py |
| P2-BOT-1 | Hardcoded initial balance 10000.0 | 6+ files |

**Tests:**
- Atomic command write/read under concurrency
- API auth middleware
- Timezone consistency validation
- Memory leak bounds (deque limits)

---

## Sprint 29: Architecture & Decoupling
**Goal:** Clean architecture, remove cross-dependencies
**Issues:** P1-BACK + P1-STRAT + P3 items

| Issue | Description | Files |
|-------|-------------|-------|
| P1-BACK-1 | shared/ imports from binance_bot | backtest/engine.py, optimizer.py |
| P1-STRAT-3 | Hardcoded "BTC/USDT" in order_manager | order_manager.py |
| P1-STRAT-6 | No retry in ExchangeClient | exchange.py |
| P1-STRAT-9 | Relative paths for emergency stop | emergency.py |
| P1-STRAT-10 | Hardcoded $0.01 tolerance | ai_grid.py |
| P1-STRAT-11 | Regex rejects nested JSON from LLM | ai_grid.py |
| P1-AI-1 | LLM parsing false positives on negation | agent.py |
| P1-AI-2 | assess_risk() dead code (89 lines) | agent.py |
| P1-AI-3 | All LLM parsing is fragile strings | agent.py |
| P1-DASH-1 | time.sleep blocks Streamlit thread | app.py |
| P3-STRAT-3 | Duplicate RSI/EMA/ADX implementations | grid.py |

**Tests:**
- Shared module imports without binance_bot
- ExchangeClient retry on NetworkError
- LLM response parsing edge cases (nested JSON, negation, markdown)

---

## Sprint 30: Code Quality & Cleanup
**Goal:** Clean up all P3 issues, unused code, dead imports
**Issues:** 18 P3 items

| Issue | Description | Files |
|-------|-------------|-------|
| P3-BOT-1 | Unused import read_state | bot.py |
| P3-BOT-2 | Unused variable old_state | bot.py |
| P3-BOT-3 | Import inside loop | bot.py |
| P3-BOT-4 | Duplicate _write_shared_state calls | bot.py |
| P3-STRAT-1 | Unused imports in 5 files | multiple |
| P3-STRAT-2 | Unused variable pnl_color | position_manager.py |
| P3-ALERT-1 | AlertLevel enum underutilized | manager.py |
| P3-ALERT-2 | trades_list dropped for Discord | manager.py |
| P3-API-1 | Unused import os | main.py |
| P3-API-2 | Duplicate force_buy/force_sell | orders.py |
| P3-API-3 | Duplicate max_drawdown computation | metrics.py |
| P3-BACK-1 | Unused variable colors | charts.py |
| P3-BACK-2 | Unused numpy import | charts.py |
| P3-JESSE-1 | Duplicate logger assignment | __init__.py |
| P3-JESSE-2 | Deprecated asyncio pattern | ai_mixin.py |
| P3-JESSE-3 | Unused atr parameter | live_trader.py |
| P1-MON-1 | Duplicate singleton pattern | metrics.py |
| P2-CORE-4 | Duplicate index on TradeLog | database.py |

**Tests:**
- Ensure no regressions from cleanup
- Import validation (no unused, no circular)

---

## Sprint 31: Simplification & Final Regression
**Goal:** Simplify entire codebase, verify all functionality
**Approach:** Agent runs `simplify` pass on every module

**Phase 1 — Simplify:**
- Reduce function complexity (split >50 line functions)
- Remove dead code paths
- Consolidate duplicate implementations
- Simplify conditional logic
- Extract magic numbers to named constants
- Standardize error handling patterns

**Phase 2 — Verify:**
- Run full test suite: `pytest tests/ -v`
- All tests must pass (zero failures)
- Verify bot starts and trades on testnet
- Verify dashboard loads all tabs
- Verify API endpoints respond correctly
- Check Docker build succeeds
- Compare line count before/after (target: net reduction)

**Phase 3 — Report:**
- Create `SIMPLIFICATION_REPORT.md`
  - Files modified
  - Lines removed vs added
  - Functions simplified
  - Test results
  - Before/after complexity metrics

---

## Summary

| Sprint | Focus | Issues | Est. Files |
|--------|-------|--------|------------|
| 24 | P0 Runtime Crashes | 23 | ~15 |
| 25 | Jesse Bot Fixes | 9 | ~5 |
| 26 | Bot Logic & State Machine | 13 | ~5 |
| 27 | Risk Management | 10 | ~5 |
| 28 | Alerts, API & Data | 15 | ~15 |
| 29 | Architecture & Decoupling | 11 | ~10 |
| 30 | Code Quality & Cleanup | 18 | ~15 |
| 31 | Simplification + Regression | full | all |
| **Total** | | **118 + simplify** | |

---

_Each sprint: worktree + branch → develop → test → code review (separate agent) → merge → Docker rebuild_
