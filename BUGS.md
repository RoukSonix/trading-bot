# BUGS.md — Open Issues to Fix

**Created:** 2026-03-07
**Status:** All items need fixing

---

## P0 — Critical (affect trading)

### BUG-001: StopLossManager never called
**File:** `binance-bot/src/binance_bot/bot.py`
**Problem:** StopLossManager is imported and instantiated but no methods are ever called during trading loop. Zero stop-loss protection in live trading.
**Fix:** Call `check_stop_loss()` and `check_take_profit()` in `_execute_trading()` after each price update.

### BUG-002: No LLM timeout
**File:** `binance-bot/src/binance_bot/strategies/ai_grid.py`
**Problem:** `_call_llm()` has no timeout. If OpenRouter is slow/down, entire bot loop blocks indefinitely.
**Fix:** Add `timeout=30` to LLM calls. Wrap in try/except with graceful fallback.

### BUG-003: No SMTP timeout
**File:** `shared/alerts/email.py`
**Problem:** `aiosmtplib.send()` without timeout, can block indefinitely.
**Fix:** Add `timeout=30` parameter.

### BUG-004: Unbounded grid growth
**File:** `binance-bot/src/binance_bot/strategies/grid.py`
**Problem:** `_create_opposite_level()` creates new levels without limit. Over time grid can grow to hundreds of levels consuming memory.
**Fix:** Add `max_levels` config (default 50). Skip level creation when limit reached.

---

## P1 — Important (correctness)

### BUG-005: Float precision for financial data
**File:** `shared/core/database.py`
**Problem:** `Trade.amount`, `Trade.cost`, `Position.amount` use SQLAlchemy `Float`. Floating point errors accumulate (we already hit 2.71e-20 bug).
**Fix:** Use `Numeric(precision=18, scale=8)` for all financial columns. Or use Python `Decimal`.

### BUG-006: Fragile LLM response parsing
**File:** `binance-bot/src/binance_bot/strategies/ai_grid.py` lines ~332-357
**Problem:** Line-by-line string parsing of AI responses. Breaks if LLM format varies slightly.
**Fix:** Use JSON mode in LLM call. Parse with `json.loads()`. Add fallback for malformed responses.

### BUG-007: Sortino ratio returns infinity
**File:** `shared/risk/metrics.py` or `shared/optimization/metrics.py`
**Problem:** Returns `float('inf')` when downside deviation is 0. Not JSON serializable, breaks API responses.
**Fix:** Return 0.0 or a large finite number when downside deviation is 0.

### BUG-008: Missing exit_time field
**File:** `shared/api/routes/trades.py` ~line 144
**Problem:** References `log.exit_time` which doesn't exist on `TradeLog` model. Will throw AttributeError.
**Fix:** Check if field exists, or add `exit_time` to TradeLog model.

### BUG-009: Import error risk in API
**File:** `shared/api/main.py` ~line 29
**Problem:** Imports `get_rules_engine` from `shared.alerts` which may not be exported in `__init__.py`.
**Fix:** Verify export exists in `shared/alerts/__init__.py` or add it.

---

## P2 — Code Quality

### BUG-010: Hardcoded risk parameters
**File:** `binance-bot/src/binance_bot/bot.py`
**Problem:** `risk_per_trade=0.02`, `daily_loss_limit=0.05` etc. are hardcoded. Should come from config.
**Fix:** Move all risk params to `shared/config/settings.py` and read from .env.

---

## Instructions for Fix Agent

1. Fix each bug in order (P0 first)
2. Add test for each fix
3. Run full regression: `pytest tests/ -v --tb=short`
4. After ALL fixes, commit: `fix: resolve all open bugs from BUGS.md`
5. Push to GitHub
6. Mark each bug as DONE in this file
