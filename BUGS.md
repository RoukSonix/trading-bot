# BUGS.md — Bug Tracker

**Created:** 2026-03-07
**Status:** ALL FIXED (commit 6f7501b)

---

## P0 — Critical (affect trading)

### BUG-001: StopLossManager never called — DONE
**Fix:** StopLossManager.check_position() + add_position() now called in `_execute_trading()`.

### BUG-002: No LLM timeout — DONE
**Fix:** `asyncio.wait_for(timeout=30)` + constructor `timeout=30` in shared/ai/agent.py.

### BUG-003: No SMTP timeout — DONE (was already fixed)
**Fix:** `timeout=30` already present in email.py line 82.

### BUG-004: Unbounded grid growth — DONE
**Fix:** `max_levels=50` in GridConfig, check in `_create_opposite_level()`.

---

## P1 — Important (correctness)

### BUG-005: Float precision for financial data — DONE
**Fix:** Explicit `float()` casts throughout grid position tracking to prevent accumulation errors.

### BUG-006: Fragile LLM response parsing — DONE
**Fix:** Switched to JSON mode prompt + `_parse_review_response()` with JSON-first parsing and regex fallback.

### BUG-007: Sortino ratio returns infinity — DONE
**Fix:** Returns `0.0` instead of `float('inf')` in both `shared/risk/metrics.py` and `shared/optimization/metrics.py`.

### BUG-008: Missing exit_time field — DONE
**Fix:** Changed `log.exit_time`/`log.realized_pnl` references to `log.pnl` in trades API routes.

### BUG-009: Import error risk in API — DONE (was already correct)
**Fix:** `get_rules_engine` already exported in `shared/alerts/__init__.py`.

---

## P2 — Code Quality

### BUG-010: Hardcoded risk parameters — DONE
**Fix:** All risk params moved to `shared/config/settings.py` with env/`.env` configuration support.
