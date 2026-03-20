# Sprint 30: Code Quality & Cleanup — Implementation Plan

**Branch:** `sprint-30-cleanup`
**Goal:** Clean up all P3 issues, unused code, dead imports, duplicate patterns
**Issues:** 18 items (16 P3 + 1 P1 + 1 P2)
**Status:** PLANNING

---

## Verification Notes

All line numbers below were verified against the current codebase. Corrections from the original audit are noted with `[CORRECTED]`. Two audit claims were found to be **invalid** and are excluded:

- ~~P3-STRAT-1 (grid.py:23)~~: `GridConfig` is defined locally in `grid.py`, not imported from config. **No fix needed.**
- ~~P3-API-1 (main.py:3)~~: `import os` is used at line 57 for `os.getenv(...)`. **No fix needed.**

This leaves **16 valid issues** to fix.

---

## Issues

### 1. P3-BOT-1: Unused import `read_state`

**File:** `binance-bot/src/binance_bot/bot.py:26`
**Line:** `from shared.core.state import BotState as SharedBotState, write_state, read_state`
**Fix:** Remove `read_state` from the import statement.
**Test:** `pytest tests/ -k bot` — verify no ImportError or missing reference.

---

### 2. P3-BOT-2: Unused variable `old_state`

**File:** `binance-bot/src/binance_bot/bot.py:374` `[CORRECTED from 368]`
**Line:** `old_state = self.state`
**Fix:** Remove the `old_state = self.state` assignment. The next line `self.state = BotState.TRADING` works independently.
**Test:** `pytest tests/ -k bot` — state transitions still work.

---

### 3. P3-BOT-3: Import inside loop

**File:** `binance-bot/src/binance_bot/bot.py:449` `[CORRECTED from 443]`
**Line:** `from shared.core.state import read_command` (inside `while self.running:` loop)
**Fix:** Move import to file-level imports (line ~26, alongside other `shared.core.state` imports). The existing line 26 already imports from `shared.core.state`, so add `read_command` there.
**Test:** `pytest tests/ -k bot` — command handling still works.

---

### 4. P3-BOT-4: Duplicate `_write_shared_state` calls

**File:** `binance-bot/src/binance_bot/bot.py:447,486` `[CORRECTED from 440,457,476]`
**Problem:** First call at line 447 writes `current_price=None`, then line 486 writes again with the actual price. The first call is wasteful.
**Fix:** Remove the first `self._write_shared_state(current_price=None)` call at line 447. The second call at line 486 with the actual price is sufficient.
**Test:** `pytest tests/ -k bot` — shared state still written correctly.

---

### 5. P3-STRAT-1: Unused imports (4 files)

**5a.** `binance-bot/src/binance_bot/core/data_collector.py:5`
- **Unused:** `delete` from `from sqlalchemy import select, delete`
- **Fix:** Change to `from sqlalchemy import select`

**5b.** `binance-bot/src/binance_bot/core/data_collector.py:3`
- **Unused:** `from datetime import datetime`
- **Fix:** Remove entire line.

**5c.** `binance-bot/src/binance_bot/core/position_manager.py:3`
- **Unused:** `field` from `from dataclasses import dataclass, field`
- **Fix:** Change to `from dataclasses import dataclass`

**5d.** `binance-bot/src/binance_bot/core/position_manager.py:4`  `[CORRECTED from 5]`
- **Unused:** `from datetime import datetime`
- **Fix:** Remove entire line.

**Test:** `pytest tests/` — no ImportError, modules still load.

---

### 6. P3-STRAT-2: Unused variable `pnl_color`

**File:** `binance-bot/src/binance_bot/core/position_manager.py:285` `[CORRECTED from 237]`
**Line:** `pnl_color = "green" if pos.unrealized_pnl >= 0 else "red"`
**Fix:** Remove the line. It's never referenced (logger calls below use plain text, not colored output).
**Test:** `pytest tests/ -k position` — summary printing still works.

---

### 7. P3-ALERT-1: `AlertLevel` enum underutilized

**File:** `shared/alerts/manager.py:16-21`
**Problem:** `AlertLevel` enum is defined but routing uses hardcoded strings instead of enum values.
**Fix:** Replace hardcoded string comparisons in the file with `AlertLevel.INFO`, `AlertLevel.WARNING`, etc. where applicable. This is a refactor to use the enum as intended.
**Test:** `pytest tests/ -k alert` — alert routing unchanged.

---

### 8. P3-ALERT-2: `trades_list` dropped for Discord

**File:** `shared/alerts/manager.py` — parameter at line 321, Discord call at lines 329-341
**Problem:** `send_daily_summary` accepts `trades_list` and passes it to email but not to Discord's `send_daily_summary`.
**Fix:** Pass `trades_list=trades_list` to the Discord `send_daily_summary` call. Verify the Discord adapter's `send_daily_summary` method accepts `trades_list`; if not, add it.
**Test:** `pytest tests/ -k alert` — daily summary includes trades in Discord output.

---

### 9. P3-API-2: Duplicate `force_buy`/`force_sell`

**File:** `shared/api/routes/orders.py:116-158,161-203`
**Problem:** `force_buy` and `force_sell` are nearly identical — only differ by side (`buy`/`sell`) and method name (`create_market_buy_order`/`create_market_sell_order`).
**Fix:** Extract common logic into `_force_trade(side: str)` helper. Both endpoints call it with their respective side.
**Test:** `pytest tests/ -k api` — force buy/sell endpoints still work.

---

### 10. P3-API-3: Duplicate `max_drawdown` computation

**File:** `shared/risk/metrics.py:132-150,152-168`
**Problem:** `max_drawdown` (percentage) and `max_drawdown_amount` (absolute) iterate the equity curve independently with identical peak-tracking logic.
**Fix:** Extract shared peak/drawdown iteration into a private method `_compute_drawdowns()` that returns both values. Both properties call it.
**Test:** `pytest tests/ -k metrics` — drawdown values unchanged.

---

### 11. P3-BACK-1: Unused `colors` variable

**File:** `shared/backtest/charts.py:145`
**Line:** `colors = ["#26A69A" if p >= 0 else "#EF5350" for p in pnls]`
**Fix:** Remove the line. The histogram below uses hardcoded `marker_color="#42A5F5"`.
**Test:** `pytest tests/ -k backtest` — charts still render.

---

### 12. P3-BACK-2: Unused `numpy` import

**File:** `shared/backtest/charts.py:5`
**Line:** `import numpy as np`
**Fix:** Remove the line. Only `pandas` is used in this file.
**Test:** `pytest tests/ -k backtest` — charts still render.

---

### 13. P3-JESSE-1: Duplicate `logger` assignment

**File:** `jesse-bot/strategies/AIGridStrategy/__init__.py:15,36`
**Problem:** `logger = logging.getLogger(__name__)` appears twice — line 15 and line 36. The second overrides the first.
**Fix:** Remove the duplicate at line 36.
**Test:** `pytest tests/ -k jesse` — logging still works.

---

### 14. P3-JESSE-2: Deprecated `asyncio.get_event_loop()` pattern

**File:** `jesse-bot/strategies/AIGridStrategy/ai_mixin.py:273` `[CORRECTED from 259]`
**Problem:** `asyncio.get_event_loop()` is deprecated in Python 3.10+. The pattern also has a fragile fallback chain.
**Fix:** Replace with `asyncio.run(asyncio.wait_for(coro, timeout))` wrapped in a try/except for `RuntimeError` (when loop is already running, use `concurrent.futures.ThreadPoolExecutor`).
**Test:** `pytest tests/ -k jesse` — AI calls still work.

---

### 15. P3-JESSE-3: Unused `atr` parameter in `setup_grid`

**File:** `jesse-bot/live_trader.py:266` `[CORRECTED from 264]`
**Signature:** `def setup_grid(self, price: float, atr: float, closes: list[float]) -> list[dict]:`
**Problem:** `atr` is accepted but never used in the function body.
**Fix:** Remove `atr` parameter from signature. Update all call sites (e.g., line 635: `self.setup_grid(price, atr, closes)` → `self.setup_grid(price, closes)`).
**Test:** `pytest tests/ -k jesse` — grid setup still works.

---

### 16. P1-MON-1: Duplicate singleton pattern

**File:** `shared/monitoring/metrics.py:117-125,245-257`
**Problem:** `TradingMetrics` uses both `__new__` singleton AND a `_metrics` global with `get_metrics()` factory. Two patterns for the same thing.
**Fix:** Remove the `__new__` singleton (lines 117-125). Keep `get_metrics()` factory as the single entry point — it's more explicit and testable. Update `_instance` / `__new__` removal so the class is a normal class.
**Test:** `pytest tests/ -k metrics` — singleton behavior preserved via `get_metrics()`.

---

### 17. P2-CORE-4: Duplicate index on `TradeLog.timestamp`

**File:** `shared/core/database.py:170,182`
**Problem:** `timestamp` column has `index=True` (line 170) AND explicit `Index("idx_trade_logs_timestamp", "timestamp")` in `__table_args__` (line 182). Creates two identical indexes.
**Fix:** Remove `index=True` from line 170. Keep the explicit named index in `__table_args__` (more readable, consistent naming).
**Test:** `pytest tests/ -k database` — queries still work, no duplicate index warning.

---

## Implementation Order

Group by file to minimize context switches:

| Step | File(s) | Issues | Risk |
|------|---------|--------|------|
| 1 | `binance-bot/src/binance_bot/bot.py` | P3-BOT-1,2,3,4 | Low — removing dead code |
| 2 | `binance-bot/src/binance_bot/core/data_collector.py` | P3-STRAT-1a,1b | Low — unused imports |
| 3 | `binance-bot/src/binance_bot/core/position_manager.py` | P3-STRAT-1c,1d, P3-STRAT-2 | Low — unused imports/vars |
| 4 | `shared/alerts/manager.py` | P3-ALERT-1,2 | Medium — changes alert routing |
| 5 | `shared/api/routes/orders.py` | P3-API-2 | Medium — refactoring endpoints |
| 6 | `shared/risk/metrics.py` | P3-API-3 | Low — internal refactor |
| 7 | `shared/backtest/charts.py` | P3-BACK-1,2 | Low — unused code |
| 8 | `jesse-bot/strategies/AIGridStrategy/__init__.py` | P3-JESSE-1 | Low — duplicate line |
| 9 | `jesse-bot/strategies/AIGridStrategy/ai_mixin.py` | P3-JESSE-2 | Medium — asyncio change |
| 10 | `jesse-bot/live_trader.py` | P3-JESSE-3 | Low — unused param |
| 11 | `shared/monitoring/metrics.py` | P1-MON-1 | Medium — singleton refactor |
| 12 | `shared/core/database.py` | P2-CORE-4 | Low — index cleanup |

## Test Plan

After all changes:

```bash
# Full test suite
pytest tests/ -v

# Specific modules
pytest tests/ -k "bot" -v
pytest tests/ -k "alert" -v
pytest tests/ -k "api" -v
pytest tests/ -k "metrics" -v
pytest tests/ -k "backtest" -v
pytest tests/ -k "jesse" -v
pytest tests/ -k "database" -v

# Import validation — no circular imports
python -c "import binance_bot.bot"
python -c "import shared.alerts.manager"
python -c "import shared.api.main"
python -c "import shared.risk.metrics"
python -c "import shared.monitoring.metrics"
```

## Exit Criteria

- [ ] All 16 valid issues fixed
- [ ] `pytest tests/ -v` passes (zero failures)
- [ ] No new unused imports introduced
- [ ] No regressions in existing functionality
- [ ] 2 invalid audit claims documented (P3-STRAT-1 grid.py, P3-API-1)
