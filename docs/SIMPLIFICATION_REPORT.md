# Sprint 31 — Simplification Report

**Date:** 2026-03-21
**Branch:** `feature/sprint-31-simplify`

## Line Count

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Total lines (Python) | 19,245 | 19,107 | -138 (-0.7%) |
| Python files | 82 | 84 | +2 (constants.py, parsing.py) |

> Net reduction is modest because two new utility files (173 lines) were added.
> Excluding new files, existing code was reduced by ~311 lines through consolidation and deduplication.

## Functions Over 50 Lines

**Split 15+ large functions** across 6 files:

| File | Function | Original Lines | Split Into |
|------|----------|---------------|------------|
| `bot.py` | `_execute_trading()` | 143 | `_check_risk_limits()`, `_run_strategy_engine()`, `_check_stop_loss()`, `_process_signals()`, `_calculate_signal_pnl()` |
| `bot.py` | `_write_shared_state()` | 58 | `_collect_grid_levels()`, `_collect_paper_stats()` |
| `shared/ai/agent.py` | `_parse_market_analysis()` | 132 | `_extract_trend()`, `_extract_risk()`, `_extract_support_resistance()`, `_extract_grid_recommended()`, `_extract_volatility_suitable()`, `_extract_confidence()`, `_extract_analysis_summary()` |
| `shared/ai/agent.py` | `_parse_grid_optimization()` | 86 | Uses `parse_llm_json()` + `extract_field()` |
| `shared/ai/agent.py` | `_parse_risk_assessment()` | 83 | Uses `parse_llm_json()` + `extract_field()` |
| `ai_grid.py` | `analyze_and_setup()` | 99 | `_fetch_analysis()`, `_apply_analysis()` |
| `ai_grid.py` | `periodic_review()` | 114 | `_build_review_prompt()`, `_execute_review()`, `_apply_review_action()` |
| `shared/backtest/engine.py` | `run()` | 158 | `_prepare_data()`, `_fill_pending_orders()` |
| `shared/dashboard/app.py` | `_tab_overview()` | 95 | `_sum_unrealized()`, `_overview_balance_section()`, `_overview_metrics_row()` |
| `shared/dashboard/app.py` | `_tab_activity()` | 85 | `_build_activity_entries()` |
| `shared/dashboard/app.py` | `_tab_grid()` | 76 | `_grid_level_ladder()` |
| `shared/dashboard/app.py` | `_tab_settings()` | 77 | `_settings_bot_control()`, `_settings_strategy_config()`, `_render_cfg_group()` |
| `jesse-bot/__init__.py` | `before()` | 85 | `_update_live_safety()`, `_update_factors_and_sentiment()`, `_update_trend_direction()`, `_maybe_periodic_alerts()` |
| `jesse-bot/__init__.py` | `hyperparameters()` | 114 | `_grid_hyperparameters()`, `_ai_hyperparameters()` |

## Magic Numbers Extracted

**Created `shared/constants.py`** (76 lines) with 30+ named constants:

| Category | Constants |
|----------|-----------|
| Timing | `TICK_INTERVAL_SEC`, `RULES_CHECK_INTERVAL`, `STATUS_UPDATE_INTERVAL` |
| RSI | `RSI_OVERSOLD`, `RSI_WEAK_BEAR`, `RSI_NEUTRAL`, `RSI_WEAK_BULL`, `RSI_OVERBOUGHT` |
| Trend | `ADX_STRONG_THRESHOLD`, `MIN_CANDLES_TREND`, `TREND_SCORE_THRESHOLD` |
| Grid Bias | `GRID_BIAS_BEARISH`, `GRID_BIAS_NEUTRAL`, `GRID_BIAS_BULLISH` |
| Precision | `MIN_POSITION_AMOUNT`, `PRICE_MATCH_TOLERANCE` |
| Retry/Network | `MAX_RETRIES`, `RETRY_BASE_DELAY`, `RETRY_BACKOFF_BASE` |
| Order Book | `CANDLE_FETCH_LIMIT` |
| Fallback Prices | `BID_FALLBACK_FACTOR`, `ASK_FALLBACK_FACTOR` |
| Risk | `HALF_KELLY_FACTOR`, `RISK_WARNING_THRESHOLD`, `ATR_STOP_MULTIPLIER` |
| Grid Suitability | `MAX_ATR_VOLATILITY`, `MAX_GRID_FILL_PCT`, `JESSE_MIN_GRID_SUITABILITY` |

**Files updated with constant imports:** 12 files

## Duplicate Code Consolidated

**Created `shared/ai/parsing.py`** (97 lines):
- `parse_llm_json(text)` — consolidated from `agent._try_parse_json()` + `ai_grid._extract_json()`
- `_extract_json_object(text)` — brace-balanced JSON extraction
- `parse_price_value(raw)` — price string cleanup
- `extract_field(parsed, keys, converter, default)` — generic field extractor

**Eliminated duplicate parsing** in:
- `shared/ai/agent.py` — 3 parser methods now use shared utility
- `binance-bot/strategies/ai_grid.py` — 2 methods now use shared utility

## Conditional Simplification

| File | Change |
|------|--------|
| `bot.py` | `_maybe_ai_review`: removed `if None: pass / else:` → `if self.last_review is not None:` |
| `exchange.py` | All 5 `@_retry_on_network_error(max_retries=3)` → `@_retry_on_network_error()` (defaults from constants) |

## Test Results

```
681 passed, 0 failed, 3 warnings in 7.05s
```

- Updated 2 test files to reference new method names after function splitting
- All 681 tests pass with zero regressions

## Files Changed

| File | Insertions | Deletions | Net |
|------|-----------|-----------|-----|
| `shared/ai/agent.py` | 178 | 399 | -221 |
| `binance-bot/src/binance_bot/bot.py` | 151 | 176 | -25 |
| `jesse-bot/strategies/AIGridStrategy/__init__.py` | 105 | 187 | -82 |
| `binance-bot/src/binance_bot/strategies/ai_grid.py` | 182 | 229 | -47 |
| `shared/dashboard/app.py` | 109 | 118 | -9 |
| `shared/backtest/engine.py` | 78 | 78 | 0 |
| `binance-bot/src/binance_bot/strategies/grid.py` | 27 | 20 | +7 |
| Other 7 files | 36 | 6 | +30 |
| **New: `shared/constants.py`** | 76 | 0 | +76 |
| **New: `shared/ai/parsing.py`** | 97 | 0 | +97 |
| Tests (2 files) | 17 | 19 | -2 |
| **Total** | **902+** | **1,213+** | **-311+** |
