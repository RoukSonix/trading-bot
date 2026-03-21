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
| `binance-bot/src/binance_bot/bot.py` | `_maybe_ai_review()` | 61 | Extract prompt building and response handling |
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
| `shared/backtest/engine.py` | (scan needed) | ~696 total | Identify and split any >50 line functions |
| `shared/dashboard/app.py` | (scan needed) | ~891 total | Identify and split any >50 line functions |
| `jesse-bot/strategies/AIGridStrategy/__init__.py` | `hyperparameters()` | 116 | Extract into grouped config builders |

**Total functions to split: ~27**

---

### 1.2 Remove Dead Code Paths

| File | Location | Dead Code | Action |
|------|----------|-----------|--------|
| `binance-bot/src/binance_bot/bot.py` | ~L693 | `pass` in first AI review trigger branch | Remove unreachable branch |
| `binance-bot/src/binance_bot/core/order_manager.py` | ~L328-330 | `except` that only re-raises after rollback | Simplify to context manager or let propagate |
| `shared/ai/agent.py` | Multiple locations | Verbose fallback parsing paths after JSON attempt | Remove fallback paths that are never reached when JSON parse succeeds |
| `shared/ai/agent.py` | ~L215-217 | Negation regex with potential escape issues | Fix or remove if unused |

**Estimated dead code removal: ~80-120 lines**

---

### 1.3 Consolidate Duplicate Implementations

| Duplicate Pattern | Locations | Action |
|-------------------|-----------|--------|
| **JSON parsing with fallback** | `agent.py` (5 methods), `ai_grid.py` (2 methods) | Create `shared/ai/parsing.py` with `parse_llm_json(text, schema)` utility |
| **Response field extraction** | `_parse_market_analysis()`, `_parse_grid_optimization()`, `_parse_risk_assessment()` | Use `parse_llm_json()` + field-specific validators |
| **Order response parsing** | `create_limit_order()`, `create_market_order()` in `order_manager.py` | Extract `_parse_order_response(response)` |
| **Position update logic (long/short)** | `grid.py` `_execute_long_paper()` / `_execute_short_paper()` / `_update_long_position()` / `_update_short_position()` | Parameterize direction: `_execute_paper(side)`, `_update_position(side)` |
| **Error alert pattern** | `bot.py` L525-530, L939-943 | Extract `_send_error_alert(error, context)` |
| **Negation detection regex** | `agent.py`, `ai_grid.py` | Move to `shared/ai/parsing.py` as constant |

**Estimated lines saved: ~200-300 lines**

---

### 1.4 Simplify Conditional Logic

| File | Location | Issue | Action |
|------|----------|-------|--------|
| `binance-bot/src/binance_bot/bot.py` | `_main_loop()` | 3+ nesting levels | Extract phases into named methods, use early returns |
| `binance-bot/src/binance_bot/strategies/grid.py` | `check_tp_sl()` L525-583 | 4+ nesting levels | Guard clause pattern, extract `_should_take_profit()` / `_should_stop_loss()` |
| `binance-bot/src/binance_bot/strategies/grid.py` | `get_status()` L869-935 | 3+ nesting levels | Extract `_format_level_status()` |
| `binance-bot/src/binance_bot/core/position_manager.py` | `update_position()` L65-118 | 4+ nesting levels | Split long/short branches into methods |
| `shared/ai/agent.py` | `_parse_market_analysis()` | Complex nested try/except | Flatten with early returns |
| `binance-bot/src/binance_bot/strategies/ai_grid.py` | `periodic_review()` L382-412 | Nested try/except | Flatten with consolidated error handler |

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
| Functions >50 lines | ~27 | Target: 0 | TBD |
| Magic numbers | ~50+ | Target: 0 | TBD |
| Bare except blocks | 22+ | Target: 0 | TBD |
| Duplicate patterns | 6 major | Target: 0 | TBD |
| Dead code paths | 4+ | Target: 0 | TBD |
| Test pass rate | TBD | 100% | - |

---

## File Impact Summary

| File | Lines | Issues | Priority |
|------|-------|--------|----------|
| `binance-bot/src/binance_bot/bot.py` | 1,010 | 9 functions >50L, magic numbers, duplicates | **HIGH** |
| `binance-bot/src/binance_bot/strategies/grid.py` | 970 | 5 functions >50L, magic numbers, nesting | **HIGH** |
| `shared/ai/agent.py` | 680 | 3 functions >50L, massive duplicate parsing | **HIGH** |
| `binance-bot/src/binance_bot/strategies/ai_grid.py` | 514 | 3 functions >50L, magic numbers, duplicates | **HIGH** |
| `binance-bot/src/binance_bot/core/order_manager.py` | 336 | 2 functions >50L, 8 bare excepts, duplicates | MEDIUM |
| `binance-bot/src/binance_bot/core/position_manager.py` | 286 | 1 function >50L, deep nesting | MEDIUM |
| `binance-bot/src/binance_bot/core/emergency.py` | 284 | 1 function >50L, magic numbers | MEDIUM |
| `jesse-bot/strategies/AIGridStrategy/__init__.py` | 673 | 1 function >50L, magic numbers | MEDIUM |
| `jesse-bot/strategies/AIGridStrategy/grid_logic.py` | 367 | Magic numbers | LOW |
| `shared/strategies/engine.py` | 169 | Magic numbers | LOW |
| `shared/risk/position_sizer.py` | 225 | Magic numbers | LOW |
| `shared/risk/limits.py` | 282 | Magic numbers | LOW |
| `shared/backtest/engine.py` | 696 | Needs scan for >50L functions | MEDIUM |
| `shared/dashboard/app.py` | 891 | Needs scan for >50L functions | MEDIUM |
| `binance-bot/src/binance_bot/core/exchange.py` | 181 | Magic retry constants | LOW |
| `binance-bot/src/binance_bot/core/data_collector.py` | 155 | 1 function >50L, magic numbers | LOW |

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
