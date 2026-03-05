# Code Review — Sprint 15-16 Baseline

**Reviewer:** Claude Code Review Agent
**Date:** 2026-03-05
**Scope:** `shared/` library, `binance-bot/`
**Sprint 15-16 Status:** `shared/factors/` and `shared/vector_db/` not yet created — dev agent has not started. This review covers the existing codebase baseline.

---

## Overall Assessment

| Category | Score | Notes |
|---|---|---|
| Architecture | 8/10 | Clean modular design, good strategy pattern |
| Type Hints | 8/10 | ~85% coverage, minor gaps |
| Error Handling | 6/10 | Inconsistent — some bare excepts |
| Async Patterns | 8/10 | Mostly correct, one recursive issue |
| Security | 7/10 | .env properly gitignored, but some code-level gaps |
| Testing | 2/10 | No unit tests found |
| Logging | 9/10 | Excellent structured logging with loguru |
| Integration | 8/10 | Clean shared lib usage |

**Verdict:** APPROVED with issues noted below. Solid codebase for Sprint 15-16 to build on.

---

## Critical Issues (Must Fix)

### 1. Bare `except` in order_manager.py:272
**File:** `binance-bot/src/binance_bot/core/order_manager.py:272`
```python
except:  # Too broad — catches KeyboardInterrupt, SystemExit
    pass
```
**Fix:** Use `except Exception as e:` with logging.

### 2. Hardcoded symbol in order_manager.py:185
**File:** `binance-bot/src/binance_bot/core/order_manager.py:185`
```python
symbol="BTC/USDT",  # TODO: get from signal
```
**Fix:** Use `signal.symbol` or pass symbol from strategy context.

### 3. Import error in api/main.py:29
**File:** `shared/api/main.py:29`
`get_rules_engine` imported from `shared.alerts` but not exported in `shared/alerts/__init__.py`. Will crash at runtime.

### 4. Missing `exit_time` field on TradeLog model
**File:** `shared/core/database.py`
`api/routes/trades.py:144` references `log.exit_time` but the field doesn't exist on the model.

---

## High Priority Issues

### 5. Recursive retry in discord.py (stack overflow risk)
**File:** `shared/alerts/discord.py:~82`
```python
if response.status == 429:
    await asyncio.sleep(retry_after)
    return await self._send_webhook(payload)  # Recursive!
```
**Fix:** Use a loop with max retries and exponential backoff.

### 6. No timeout on SMTP operations
**File:** `shared/alerts/email.py:75`
`aiosmtplib.send()` called without timeout — can hang indefinitely.

### 7. No timeout on AI/LLM calls
**File:** `binance-bot/src/binance_bot/strategies/ai_grid.py`
`_call_llm()` has no timeout — could block the entire bot loop if LLM is slow/down.

### 8. Risk parameters hardcoded in bot.py
**File:** `binance-bot/src/binance_bot/bot.py`
```python
risk_per_trade=0.02,      # Should be in config
max_position_pct=0.10,    # Should be in config
daily_loss_limit=0.05,    # Should be in config
```
**Fix:** Move to `shared/config/settings.py` as configurable values.

### 9. Unbounded grid growth
**File:** `binance-bot/src/binance_bot/strategies/grid.py`
`_create_opposite_level()` creates new levels without limit. Grid can grow indefinitely in volatile markets.

### 10. Float precision for financial amounts
**File:** `shared/core/database.py`
`Trade.amount` uses `Float` type. For financial data, use `Decimal` or `Numeric` to avoid precision loss on large trades.

---

## Medium Priority

### 11. Hardcoded starting balance (10000.0)
Multiple files reference `10000` as initial balance:
- `shared/monitoring/metrics.py:109`
- `shared/alerts/telegram.py:108`
- `binance-bot/src/binance_bot/bot.py` (5+ occurrences)

**Fix:** Pull from config or database.

### 12. No database migrations
No Alembic or migration tool configured. Schema changes require manual DB recreation.

### 13. Fragile AI response parsing
**File:** `binance-bot/src/binance_bot/strategies/ai_grid.py:332-357`
Line-by-line string parsing of LLM responses. Will break if format varies.
**Suggestion:** Use structured output (JSON mode) or add robust fallback.

### 14. SQLite for concurrent access
SQLite doesn't handle concurrent writes well. Fine for paper trading, but needs PostgreSQL for production multi-service deployment.

### 15. Sortino ratio returns infinity
**File:** `shared/risk/metrics.py:209`
When downside deviation is 0, returns `float('inf')` — not JSON serializable.

---

## Testing Gap (Major)

**No unit tests exist anywhere in the codebase.** Only `scripts/test_ai.py` exists (manual AI agent test).

**Recommendation for Sprint 15-16:**
- New `shared/factors/` and `shared/vector_db/` modules MUST include tests
- Target: pytest with 80%+ coverage on new code
- Add `tests/` directories in both shared/ and binance-bot/

---

## Security Notes

- `.env` is properly gitignored (verified)
- No API keys found in committed source code
- Docker runs as non-root user (good)
- SQLAlchemy uses parameterized queries (no SQL injection)
- SMTP password loaded from env vars (acceptable)

---

## Files Reviewed

### shared/ (all modules)
- `__init__.py`, `config/settings.py`
- `core/database.py`, `core/indicators.py`, `core/state.py`
- `ai/agent.py`, `ai/prompts.py`
- `alerts/manager.py`, `alerts/discord.py`, `alerts/email.py`, `alerts/telegram.py`, `alerts/rules.py`
- `api/main.py`, `api/routes/bot.py`, `api/routes/candles.py`, `api/routes/orders.py`, `api/routes/positions.py`, `api/routes/trades.py`
- `backtest/engine.py`
- `monitoring/metrics.py`
- `reports/pnl.py`
- `risk/position_sizer.py`, `risk/limits.py`, `risk/metrics.py`, `risk/stop_loss.py`
- `utils/logging_config.py`

### binance-bot/ (all modules)
- `src/binance_bot/bot.py`, `main.py`
- `src/binance_bot/core/exchange.py`, `order_manager.py`, `position_manager.py`, `data_collector.py`, `emergency.py`
- `src/binance_bot/strategies/base.py`, `grid.py`, `ai_grid.py`
- All 9 scripts in `scripts/`
- `Dockerfile`, `docker-compose.yml` (all variants)
- `pyproject.toml`, `requirements.txt`
- `.env.example`

---

## Sprint 15-16 Readiness

The codebase is ready for Sprint 15-16 development. The modular architecture in `shared/` makes it straightforward to add new modules (`factors/`, `vector_db/`).

**Requirements for new modules:**
1. Follow existing patterns in `shared/` (pydantic models, async, loguru logging)
2. Include `__init__.py` with proper exports
3. Add type hints on all public functions
4. Include `tests/` with pytest
5. No hardcoded API keys — use `shared/config/settings.py`
6. Add any new dependencies to `pyproject.toml`

**Will re-review once Sprint 15-16 code is committed.**

---

*Review by Claude Code Review Agent — 2026-03-05 22:10 UTC*
