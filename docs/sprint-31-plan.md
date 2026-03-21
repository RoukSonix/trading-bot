# Sprint 31: Simplification & Final Regression — Plan

**Branch:** `sprint-31-simplify`
**Baseline:** 19,245 total lines across 82 Python files
**Goal:** Reduce complexity, eliminate dead code, consolidate duplicates, full regression

---

## Phase 1 — Simplify

### 1.1 Split Functions Over 50 Lines

| File | Function | Lines | Action |
|------|----------|-------|--------|
| `binance-bot/src/binance_bot/bot.py` | `__init__()` | 105 | Extract AI setup, alert setup, and risk manager init into `_init_ai()`, `_init_alerts()`, `_init_risk()` |
| `binance-bot/src/binance_bot/bot.py` | `start()` | 63 | Extract balance fetch + grid setup into `_initialize_trading()` |
| `binance-bot/src/binance_bot/bot.py` | `_check_entry_conditions()` | 54 | Extract individual checks into named booleans, return early |
| `binance-bot/src/binance_bot/bot.py` | `_main_loop()` | 98 | Extract tick phases: `_tick_trading()`, `_tick_monitoring()`, `_tick_status()` |
| `binance-bot/src/binance_bot/bot.py` | `_execute_trading()` | 143 | Split into `_execute_signal()`, `_execute_paper_trade()`, `_execute_live_trade()` |
| `binance-bot/src/binance_bot/bot.py` | `_maybe_ai_review()` | 62 | Extract prompt building and response handling |
<!-- VALIDATION NOTE: _maybe_ai_review() is 62 lines (L687-748), not 61. -->
| `binance-bot/src/binance_bot/bot.py` | `_print_stats()` | 52 | Extract stat formatting into helper |
| `binance-bot/src/binance_bot/bot.py` | `_write_shared_state()` | 58 | Extract dict building into `_build_state_dict()` |
| `binance-bot/src/binance_bot/bot.py` | `_handle_emergency_stop()` | 51 | Extract position closing and alert sending |
| `binance-bot/src/binance_bot/strategies/grid.py` | `detect_trend()` | 62 | Extract indicator scoring into `_score_trend_indicators()` |
| `binance-bot/src/binance_bot/strategies/grid.py` | `calculate_signals()` | 69 | Extract signal generation per level into `_evaluate_level()` |
| `binance-bot/src/binance_bot/strategies/grid.py` | `check_tp_sl()` | 80 | Split into `_check_take_profit()` and `_check_stop_loss()` |
| `binance-bot/src/binance_bot/strategies/grid.py` | `_close_level()` | 56 | Extract PnL recording and position update |
| `binance-bot/src/binance_bot/strategies/grid.py` | `get_status()` | 70 | Extract level summary building into `_summarize_levels()` |
| `binance-bot/src/binance_bot/strategies/ai_grid.py` | `analyze_and_setup()` | 99 | Split into `_fetch_ai_analysis()` and `_apply_ai_config()` |
| `binance-bot/src/binance_bot/strategies/ai_grid.py` | `periodic_review()` | 114 | Split into `_build_review_prompt()`, `_execute_review()`, `_apply_review()` |
| `binance-bot/src/binance_bot/strategies/ai_grid.py` | `_parse_review_response()` | 69 | Consolidate with shared JSON parsing utility |
| `binance-bot/src/binance_bot/core/emergency.py` | `close_all_positions()` | 95 | Extract per-symbol closing into `_close_symbol_position()` |
| `binance-bot/src/binance_bot/core/order_manager.py` | `create_limit_order()` | 60 | Extract response parsing into shared `_parse_order_response()` |
| `binance-bot/src/binance_bot/core/order_manager.py` | `create_market_order()` | 52 | Reuse `_parse_order_response()` from above |
| `binance-bot/src/binance_bot/core/position_manager.py` | `update_position()` | 85 | Split into `_update_long()` and `_update_short()` |
| `shared/ai/agent.py` | `_parse_market_analysis()` | 132 | Extract JSON extraction, field parsing, fallback logic into separate methods |
| `shared/ai/agent.py` | `_parse_grid_optimization()` | 86 | Reuse consolidated JSON parsing utility |
| `shared/ai/agent.py` | `_parse_risk_assessment()` | 83 | Reuse consolidated JSON parsing utility |
| `shared/backtest/engine.py` | `run()` (x2) | 158, 133 | Split long run methods into phases |
| `shared/backtest/engine.py` | `_compute_result()` | 89 | Extract metric calculations |
| `shared/dashboard/app.py` | `_tab_overview()` | 95 | Extract widget builders |
| `shared/dashboard/app.py` | `_tab_activity()` | 86 | Extract table/chart builders |
| `shared/dashboard/app.py` | `_tab_grid()` | 76 | Extract grid visualization |
| `shared/dashboard/app.py` | `_grid_chart()` | 77 | Extract chart rendering |
| `shared/dashboard/app.py` | `_tab_settings()` | 77 | Extract settings form builders |
| `jesse-bot/strategies/AIGridStrategy/__init__.py` | `hyperparameters()` | 114 | Extract into grouped config builders |
<!-- VALIDATION NOTE: hyperparameters() is 114 lines (L103-216), not 116. -->
| `binance-bot/src/binance_bot/core/data_collector.py` | `fetch_and_store_ohlcv()` | 56 | Extract storage logic |

**Total functions to split: ~35**
<!-- VALIDATION NOTE: Scan found 8 additional >50L functions (3 in backtest/engine.py, 5 in dashboard/app.py), plus data_collector. Updated total from ~27 to ~35. -->

---

### 1.2 Remove Dead Code Paths

| File | Location | Dead Code | Action |
|------|----------|-----------|--------|
| `binance-bot/src/binance_bot/bot.py` | L692-697 | `pass` in first AI review trigger branch | Simplify: replace if/pass/else with `if last_review is not None and interval not elapsed: return` |
<!-- VALIDATION NOTE: The `pass` branch at L692 IS reachable (first review case). Not dead code — it's a deliberate no-op. Simplify the if/else structure, don't "remove unreachable branch". -->
| `binance-bot/src/binance_bot/core/order_manager.py` | L328-330 | `except` that only re-raises after rollback | Simplify to context manager or let propagate |
<!-- VALIDATION NOTE: This is valid error handling (rollback + re-raise), not dead code. Move to §1.6 error handling instead. -->
| `shared/ai/agent.py` | ~L215-217 | Negation regex — review for correctness | Review regex edge cases (e.g. `{0,4}` gap may miss close negations) |
<!-- VALIDATION NOTE: _NEGATION_RE at L215 IS actively used by _keyword_negated() at L221. NOT dead/unused. Moved from "remove" to "review". -->

**Estimated dead code removal: ~20-40 lines**
<!-- VALIDATION NOTE: Original estimate of 80-120 lines was inflated. The agent.py fallback paths are NOT dead code — they're active fallbacks for non-JSON LLM responses. The negation regex is actively used. Reduced estimate to reflect actual dead code (the pass branch simplification + minor cleanup). -->

---

### 1.3 Consolidate Duplicate Implementations

| Duplicate Pattern | Locations | Action |
|-------------------|-----------|--------|
| **JSON parsing with fallback** | `agent.py` (5 methods), `ai_grid.py` (2 methods) | Create `shared/ai/parsing.py` with `parse_llm_json(text, schema)` utility |
| **Response field extraction** | `_parse_market_analysis()`, `_parse_grid_optimization()`, `_parse_risk_assessment()` | Use `parse_llm_json()` + field-specific validators |
| **Order response parsing** | `create_limit_order()`, `create_market_order()` in `order_manager.py` | Extract `_parse_order_response(response)` |
| **Position update logic (long/short)** | `grid.py` `_execute_long_paper()` / `_execute_short_paper()` / `_update_long_position()` / `_update_short_position()` | Parameterize direction: `_execute_paper(side)`, `_update_position(side)` |
<!-- VALIDATION NOTE: Short sells in _execute_short_paper() (L718-726) don't check balance before crediting (opening short gives cash). Long buys in _execute_long_paper() (L694-703) DO check paper_balance >= cost. Parameterized _execute_paper(side) MUST preserve this asymmetry. -->
| **JSON parsing** | `agent.py` `_try_parse_json()` vs `ai_grid.py` `_extract_json()` | Consolidate into shared utility |
<!-- VALIDATION NOTE: _try_parse_json() (agent.py L135-162) tries full-text JSON parse first, then brace extraction. _extract_json() (ai_grid.py L28-44) only does brace extraction. Consolidated utility must preserve the full-text-first approach from agent.py. -->
<!-- VALIDATION NOTE: Removed "Error alert pattern" — bot.py L525-530 and L939-943 already call self.alert_manager.send_error_alert(). These are two call sites with different params, not duplicate implementations. -->
<!-- VALIDATION NOTE: Removed "Negation detection regex" duplication — no negation regex exists in ai_grid.py. _NEGATION_RE only exists in agent.py (L215). No consolidation needed. -->

**Estimated lines saved: ~150-250 lines**
<!-- VALIDATION NOTE: Reduced estimate after removing 2 invalid consolidation targets. -->

---

### 1.4 Simplify Conditional Logic

| File | Location | Issue | Action |
|------|----------|-------|--------|
| `binance-bot/src/binance_bot/bot.py` | `_main_loop()` | 3+ nesting levels | Extract phases into named methods, use early returns |
| `binance-bot/src/binance_bot/strategies/grid.py` | `check_tp_sl()` L525-583 | 4+ nesting levels | Guard clause pattern, extract `_should_take_profit()` / `_should_stop_loss()` |
| `binance-bot/src/binance_bot/strategies/grid.py` | `get_status()` L867-936 | 1-2 nesting levels (mostly flat) | Extract `_format_level_status()` — low priority |
<!-- VALIDATION NOTE: get_status() is mostly flat dict construction and list comprehensions. Max nesting is 1-2 levels (if self.center_price block). Downgraded from 3+ to low priority. -->
| `binance-bot/src/binance_bot/core/position_manager.py` | `update_position()` L65-118 | 4+ nesting levels | Split long/short branches into methods |
| `shared/ai/agent.py` | `_parse_market_analysis()` L229-360 | Length (132 lines), not nesting | Reduce length via consolidated JSON utility; nesting is already shallow |
<!-- VALIDATION NOTE: _parse_market_analysis() doesn't have complex nested try/except. It has one _try_parse_json() call then linear field extraction. Main issue is length, not nesting depth. -->
| `binance-bot/src/binance_bot/strategies/ai_grid.py` | `periodic_review()` L299-412 | Single outer try/except wrapping method body | Split method to reduce length; nesting is acceptable at 1 level |
<!-- VALIDATION NOTE: L382-412 is actually prompt string construction, not nested try/except. The try at L378 is the only exception handler. Plan line reference was misleading. -->

---

### 1.5 Extract Magic Numbers to Named Constants

Create `shared/constants.py` and per-module constant sections:

| Category | Values | Constant Names |
|----------|--------|----------------|
| **Timing** | `5`, `12`, `60` | `TICK_INTERVAL_SEC`, `RULES_CHECK_INTERVAL`, `STATUS_UPDATE_SEC` |
| **RSI Thresholds** | `30`, `45`, `50`, `55`, `70` | `RSI_OVERSOLD`, `RSI_WEAK_BEAR`, `RSI_NEUTRAL`, `RSI_WEAK_BULL`, `RSI_OVERBOUGHT` |
| **Trend Detection** | `25`, `50`, `4` | `ADX_STRONG_THRESHOLD`, `MIN_CANDLES_TREND`, `TREND_SCORE_THRESHOLD` |
| **Grid Bias** | `0.3`, `0.5`, `0.7` | `GRID_BIAS_BEARISH`, `GRID_BIAS_NEUTRAL`, `GRID_BIAS_BULLISH` |
| **Price Precision** | `0.00000001`, `0.001` | `MIN_POSITION_AMOUNT`, `PRICE_MATCH_TOLERANCE` |
| **AI Defaults** | `15`, `50`, `60`, `70` | `AI_REVIEW_INTERVAL_MIN`, `MIN_CONFIDENCE_DEFAULT`, `MIN_CONFIDENCE_TRADE`, `DEFAULT_ADJUSTMENT_CONFIDENCE` |
| **Grid Suitability** | `0.3`, `0.235` | `MIN_GRID_SUITABILITY`, `JESSE_MIN_GRID_SUITABILITY` |
| **Risk** | `0.5`, `0.7`, `2.0` | `HALF_KELLY_FACTOR`, `RISK_WARNING_THRESHOLD`, `ATR_STOP_MULTIPLIER` |
| **Retry/Network** | `3`, `1.0`, `2`, `30` | `MAX_RETRIES`, `RETRY_BASE_DELAY`, `RETRY_BACKOFF_BASE`, `LLM_TIMEOUT_SEC` |
| **Order Book** | `10`, `30`, `100` | `ORDER_BOOK_DEPTH_SMALL`, `ORDER_BOOK_DEPTH_DEFAULT`, `CANDLE_FETCH_LIMIT` |
| **Fallback Prices** | `0.999`, `1.001` | `BID_FALLBACK_FACTOR`, `ASK_FALLBACK_FACTOR` |

**Estimated magic numbers to extract: ~50+**

---

### 1.6 Standardize Error Handling Patterns

| Issue | Count | Action |
|-------|-------|--------|
| Bare `except Exception` | 22+ | Replace with specific exceptions: `ccxt.NetworkError`, `json.JSONDecodeError`, `KeyError`, `ValueError` |
| Silent failures (return default) | ~8 | Add `logger.warning()` before returning defaults |
| Inconsistent rollback pattern | ~4 | Use `session.begin()` context manager or consistent try/except/rollback |
| Missing input validation | ~6 | Add guards at method entry for exchange responses |

---

## Phase 2 — Verify

### 2.1 Test Suite
```bash
pytest tests/ -v --tb=short
```
- **Requirement:** Zero failures, zero errors
- **Coverage target:** Maintain >80%

### 2.2 Functional Checks
- [ ] Bot starts on testnet without errors
- [ ] Dashboard loads all tabs
- [ ] API endpoints respond (health, positions, trades, orders, candles)
- [ ] Docker build succeeds

### 2.3 Line Count Comparison
```bash
# Before (baseline)
find binance-bot/src shared jesse-bot/strategies -name "*.py" -exec wc -l {} + | tail -1
# Current baseline: 19,245 lines

# After (target: net reduction)
# Expected: ~18,200-18,600 lines (3-5% reduction)
```

---

## Phase 3 — Report

Create `SIMPLIFICATION_REPORT.md` with:

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Total lines | 19,245 | TBD | TBD |
| Functions >50 lines | ~35 | Target: 0 | TBD |
| Magic numbers | ~50+ | Target: 0 | TBD |
| Bare except blocks | 22+ | Target: 0 | TBD |
| Duplicate patterns | 6 major | Target: 0 | TBD |
| Dead code paths | 2 | Target: 0 | TBD |
| Test pass rate | TBD | 100% | - |

---

## File Impact Summary

| File | Lines | Issues | Priority |
|------|-------|--------|----------|
<!-- VALIDATION NOTE: All line counts corrected +1 (original counts excluded trailing newline). -->
| `binance-bot/src/binance_bot/bot.py` | 1,011 | 9 functions >50L, magic numbers, duplicates | **HIGH** |
| `binance-bot/src/binance_bot/strategies/grid.py` | 971 | 5 functions >50L, magic numbers, nesting | **HIGH** |
| `shared/ai/agent.py` | 681 | 3 functions >50L, massive duplicate parsing | **HIGH** |
| `binance-bot/src/binance_bot/strategies/ai_grid.py` | 515 | 3 functions >50L, magic numbers, duplicates | **HIGH** |
| `binance-bot/src/binance_bot/core/order_manager.py` | 337 | 2 functions >50L, 8 bare excepts, duplicates | MEDIUM |
| `binance-bot/src/binance_bot/core/position_manager.py` | 287 | 1 function >50L, deep nesting | MEDIUM |
| `binance-bot/src/binance_bot/core/emergency.py` | 285 | 1 function >50L, magic numbers | MEDIUM |
| `jesse-bot/strategies/AIGridStrategy/__init__.py` | 674 | 1 function >50L (114 lines, not 116), magic numbers | MEDIUM |
| `jesse-bot/strategies/AIGridStrategy/grid_logic.py` | 367 | Magic numbers | LOW |
| `shared/strategies/engine.py` | 169 | Magic numbers | LOW |
| `shared/risk/position_sizer.py` | 225 | Magic numbers | LOW |
| `shared/risk/limits.py` | 282 | Magic numbers | LOW |
| `shared/backtest/engine.py` | 696 | 3 functions >50L: run() x2 (158, 133 lines), _compute_result() (89 lines) | **HIGH** |
| `shared/dashboard/app.py` | 891 | 5 functions >50L: _tab_overview (95), _tab_activity (86), _tab_grid (76), _grid_chart (77), _tab_settings (77) | **HIGH** |
| `binance-bot/src/binance_bot/core/exchange.py` | 181 | Magic retry constants | LOW |
| `binance-bot/src/binance_bot/core/data_collector.py` | 155 | 1 function >50L (56 lines), magic numbers | LOW |

**New file to create:** `shared/constants.py` — centralized named constants
**New file to create:** `shared/ai/parsing.py` — consolidated LLM response parsing

---

## Execution Order

1. Create `shared/constants.py` and `shared/ai/parsing.py` (foundations)
2. Consolidate duplicates (agent.py parsing, order response parsing, position updates)
3. Split >50 line functions (bot.py → grid.py → agent.py → ai_grid.py → rest)
4. Extract magic numbers to constants
5. Simplify conditionals (flatten nesting, early returns)
6. Standardize error handling
7. Remove dead code
8. Run full test suite
9. Fix any regressions
10. Generate SIMPLIFICATION_REPORT.md
