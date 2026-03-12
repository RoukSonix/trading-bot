# BUGS.md — Open Issues to Fix

**Created:** 2026-03-07
**Status:** ALL FIXED

---

## P0 — Critical (affect trading)

### BUG-001: StopLossManager never called — DONE
**File:** `binance-bot/src/binance_bot/bot.py`
**Problem:** StopLossManager is imported and instantiated but no methods are ever called during trading loop. Zero stop-loss protection in live trading.
**Fix:** Added `StopLossManager` import, instantiation with configurable params, `check_position()` call in `_execute_trading()`, and `add_position()` on buy fills.

### BUG-002: No LLM timeout — DONE
**File:** `shared/ai/agent.py`
**Problem:** `_call_llm()` has no timeout. If OpenRouter is slow/down, entire bot loop blocks indefinitely.
**Fix:** Added `timeout=30` to ChatOpenAI constructor and `asyncio.wait_for(timeout=30)` in `_call_llm()`.

### BUG-003: No SMTP timeout — DONE (already fixed)
**File:** `shared/alerts/email.py`
**Problem:** `aiosmtplib.send()` without timeout, can block indefinitely.
**Fix:** `timeout=30` was already present on line 82.

### BUG-004: Unbounded grid growth — DONE
**File:** `binance-bot/src/binance_bot/strategies/grid.py`
**Problem:** `_create_opposite_level()` creates new levels without limit. Over time grid can grow to hundreds of levels consuming memory.
**Fix:** Added `max_levels=50` to `GridConfig`. `_create_opposite_level()` now skips creation when limit reached.

---

## P1 — Important (correctness)

### BUG-005: Float precision for financial data — DONE
**File:** `shared/core/database.py`
**Problem:** `Trade.amount`, `Trade.cost`, `Position.amount` use SQLAlchemy `Float`. Floating point errors accumulate.
**Fix:** Changed all financial columns (price, amount, cost, fee, pnl, etc.) to `Numeric(precision=18, scale=8)`. Updated grid.py position tracking to use `float()` casts for arithmetic.

### BUG-006: Fragile LLM response parsing — DONE
**File:** `binance-bot/src/binance_bot/strategies/ai_grid.py`
**Problem:** Line-by-line string parsing of AI responses. Breaks if LLM format varies slightly.
**Fix:** Added `_parse_review_response()` static method with JSON-first parsing (regex extraction) and line-by-line fallback. Updated prompt to request JSON output.

### BUG-007: Sortino ratio returns infinity — DONE
**File:** `shared/risk/metrics.py` and `shared/optimization/metrics.py`
**Problem:** Returns `float('inf')` when downside deviation is 0. Not JSON serializable, breaks API responses.
**Fix:** Returns `0.0` instead of `float('inf')` in both files. Also fixed `profit_factor` in risk/metrics.py.

### BUG-008: Missing exit_time field — DONE
**File:** `shared/api/routes/trades.py`
**Problem:** References `log.exit_time` and `log.realized_pnl` which don't exist on `TradeLog` model.
**Fix:** Changed to use `TradeLog.timestamp` for ordering, `log.pnl` for PnL values, and `log.datetime_utc` for display.

### BUG-009: Import error risk in API — DONE (already correct)
**File:** `shared/api/main.py`
**Problem:** Imports `get_rules_engine` from `shared.alerts` which may not be exported in `__init__.py`.
**Fix:** Already correctly exported in `shared/alerts/__init__.py`.

---

## P2 — Code Quality

### BUG-010: Hardcoded risk parameters — DONE
**File:** `binance-bot/src/binance_bot/bot.py`
**Problem:** `risk_per_trade=0.02`, `daily_loss_limit=0.05` etc. are hardcoded.
**Fix:** Added `risk_per_trade`, `risk_max_position_pct`, `risk_daily_loss_limit`, `risk_max_drawdown_limit`, `risk_max_consecutive_losses`, `risk_stop_loss_pct`, `risk_take_profit_pct` to `shared/config/settings.py`. Bot.py now reads from `settings.*`.

---

## Instructions for Fix Agent

1. Fix each bug in order (P0 first)
2. Add test for each fix
3. Run full regression: `pytest tests/ -v --tb=short`
4. After ALL fixes, commit: `fix: resolve all open bugs from BUGS.md`
5. Push to GitHub
6. Mark each bug as DONE in this file
