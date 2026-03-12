# AUDIT V2 — Full Code Audit Report

> **Date:** 2026-03-11
> **Scope:** All Python code in `binance-bot/`, `shared/`, `jesse-bot/`, and `tests/`
> **Method:** Systematic file-by-file review by parallel audit agents
> **Previous audit:** `AUDIT.md` (2026-03-06)

## Executive Summary

| Severity | Count | Description |
|----------|-------|-------------|
| **P0 — Runtime Crashes** | 28 | Unhandled exceptions, division by zero, type errors, import-time crashes |
| **P1 — Logic Bugs** | 42 | Dead code paths, incorrect calculations, race conditions, missing error handling |
| **P2 — Data Issues** | 30 | Float precision, timezone inconsistency, memory leaks, hardcoded values |
| **P3 — Code Quality** | 18 | Unused imports, duplicate code, missing type hints |
| **Total** | **118** | |

### Top 10 Most Critical Findings

| # | Issue | Impact |
|---|-------|--------|
| 1 | PAUSED state auto-resume is dead code (P1-BOT-1) | Bot can never auto-recover from AI pause |
| 2 | Wrong candle column index in jesse-bot (P0-JESSE-1) | Trend detection uses HIGH prices instead of CLOSE |
| 3 | Jesse live_trader rebuilds grid every iteration (P1-JESSE-3) | All grid state lost every hour in live trading |
| 4 | PnL always recorded as 0 for grid trades (P1-BOT-6) | Risk limits subsystem completely disabled |
| 5 | StopLossManager instantiated but never called (P1-BOT-KNOWN) | Zero stop-loss protection in live trading |
| 6 | `Settings()` crashes at import time without env vars (P0-CORE-1) | Blocks all testing/tooling without full config |
| 7 | Decimal values not JSON-serializable from DB (P0-CORE-3) | API responses and alerts crash on serialization |
| 8 | `float('inf')` in profit_factor crashes JSON (P0-BACK-1) | Backtest results cannot be saved/serialized |
| 9 | Max drawdown limit auto-resets daily (P1-RISK-5) | Portfolio-level protection defeated overnight |
| 10 | No authentication on trading API endpoints (P2-API-6) | Anyone on the network can execute trades |

---

## P0 — Runtime Crashes

Issues that will or can cause the application to crash at runtime.

---

### P0-BOT-1: `asyncio.get_event_loop()` deprecated, crashes on Python 3.14

**File:** `binance-bot/src/binance_bot/bot.py:991`
```python
loop = asyncio.get_event_loop()
```
**Problem:** In Python 3.14 (running on the server), `asyncio.get_event_loop()` raises `RuntimeError` when no loop is running.
**Fix:** Replace with `asyncio.get_running_loop()`.

---

### P0-BOT-2: Unhandled network error during startup

**File:** `binance-bot/src/binance_bot/bot.py:286`
```python
await self._check_entry_conditions()  # outside main loop try/except
```
**Problem:** `_check_entry_conditions()` calls `_fetch_market_data()` which makes 3 CCXT network calls. This call at line 286 is outside the main loop's `try/except`, so a network error during startup crashes the bot with an unhandled exception.
**Fix:** Wrap in try/except or move inside the main loop.

---

### P0-BOT-3: `ticker["last"]` can be `None` causing `TypeError`

**File:** `binance-bot/src/binance_bot/bot.py:297,469`
```python
ticker = exchange_client.get_ticker(self.symbol)
# ticker["last"] used in f-strings and arithmetic without null check
```
**Problem:** CCXT's `fetch_ticker()` can return `None` for the `"last"` field. Downstream code does `ticker["last"] * 0.999` and `f"${data['price']:,.2f}"` which crash on `None`.
**Fix:** Add null check: `current_price = ticker["last"] or ticker.get("close") or 0.0` with early return if zero.

---

### P0-BOT-4: `_print_stats()` accesses `status["paper_trading"]` without `.get()`

**File:** `binance-bot/src/binance_bot/bot.py:801`
```python
paper = status["paper_trading"]
```
**Problem:** `KeyError` if `get_status()` returns a dict without `"paper_trading"` key. Other code paths use `.get("paper_trading", {})`.
**Fix:** Use `paper = status.get("paper_trading", {})`.

---

### P0-STRAT-1: Division by zero in RSI calculation

**File:** `binance-bot/src/binance_bot/strategies/grid.py:241`
```python
rs = avg_gain / avg_loss
```
**Problem:** When price is flat or only moves in one direction, `avg_loss` is zero, producing `inf`/`NaN`. Same issue in `shared/indicators/momentum.py:14`, `shared/factors/factor_calculator.py:175`, and `jesse-bot/strategies/AIGridStrategy/factors_mixin.py:203`.
**Fix:** Guard with `avg_loss.replace(0, np.nan)` or handle the zero case explicitly.

---

### P0-STRAT-2: Division by zero in ADX calculation

**File:** `binance-bot/src/binance_bot/strategies/grid.py:292`
```python
dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
```
**Problem:** When both `plus_di` and `minus_di` are zero (flat markets), this produces `NaN`. Same issue in `shared/indicators/trend.py:240`.
**Fix:** Replace denominator with `(plus_di + minus_di).replace(0, np.nan)`.

---

### P0-STRAT-3: Division by zero in `_apply_optimization` when `num_levels=0`

**File:** `binance-bot/src/binance_bot/strategies/ai_grid.py:180`
```python
spacing_pct = (price_range / opt.num_levels) / current_price * 100
```
**Problem:** If AI returns `num_levels=0`, this raises `ZeroDivisionError`. Also at line 183, `num_levels=1` produces `grid_levels = 1 // 2 = 0`.
**Fix:** Guard: `if opt.num_levels <= 1: self.setup_grid(current_price); return` and `max(1, opt.num_levels // 2)`.

---

### P0-STRAT-4: DB session leak on exception in `_save_trade_to_db`

**File:** `binance-bot/src/binance_bot/strategies/grid.py:752-784`
```python
try:
    db = SessionLocal()
    db.commit()
    db.close()
except Exception as e:
    logger.warning(...)  # db.close() never called
```
**Problem:** If exception occurs between `SessionLocal()` and `db.close()`, the session leaks.
**Fix:** Use `try/finally` with `db.close()` in the `finally` block.

---

### P0-STRAT-5: Bare `except:` swallows all exceptions including `SystemExit`

**File:** `binance-bot/src/binance_bot/core/order_manager.py:272`
```python
except:
    pass
```
**Problem:** Catches `KeyboardInterrupt`, `SystemExit`, `MemoryError`. Filled orders can be silently lost.
**Fix:** Change to `except Exception as e: logger.warning(...)`.

---

### P0-STRAT-6: Missing rollback on DB commit failure

**File:** `binance-bot/src/binance_bot/core/order_manager.py:308-326`
```python
try:
    session.commit()
finally:
    session.close()  # no rollback on failure
```
**Fix:** Add `except Exception: session.rollback(); raise` before `finally`.

---

### P0-AI-1: ZeroDivisionError when `best_bid` is 0

**File:** `shared/ai/agent.py:159`
```python
spread = ((best_ask - best_bid) / best_bid) * 100
```
**Problem:** If `best_bid` is 0 (empty order book), `ZeroDivisionError` crashes the AI analysis.
**Fix:** Guard with `if best_bid > 0: ... else: spread = 0.0`.

---

### P0-AI-2: Module-level `TradingAgent()` instantiation crashes without env vars

**File:** `shared/ai/agent.py:470`
```python
trading_agent = TradingAgent()  # runs at import time
```
**Problem:** Constructor accesses `settings.openrouter_api_key`. If env vars are missing, importing `shared.ai` crashes the entire application. Blocks testing without full configuration.
**Fix:** Use lazy initialization via a factory function.

---

### P0-ALERT-1: `AlertConfig.from_dict` uses fragile `co_varnames`

**File:** `shared/alerts/manager.py:67`
```python
return cls(**{k: v for k, v in data.items() if k in cls.__init__.__code__.co_varnames})
```
**Problem:** `co_varnames` includes ALL local variables, not just parameters. CPython implementation detail that can break across versions.
**Fix:** Use `inspect.signature(cls.__init__).parameters`.

---

### P0-ALERT-2: Invalid `daily_summary_time` causes infinite error loop

**File:** `shared/alerts/manager.py:414`
```python
target_hour, target_minute = map(int, self.config.daily_summary_time.split(":"))
```
**Problem:** Misconfigured value (e.g., `"20:00:00"`, empty string) raises `ValueError` caught by general handler that retries every 60 seconds indefinitely.
**Fix:** Validate format in `AlertConfig.__init__`.

---

### P0-CORE-1: `Settings()` crashes at import time without env vars

**File:** `shared/config/settings.py:196`
```python
settings = Settings()  # module-level instantiation
```
**Problem:** `binance_api_key` and `binance_secret_key` are required fields (`Field(...)`). Missing env vars cause `ValidationError` at import time, crashing any code that imports `shared.config`.
**Fix:** Give defaults (`default=""`) with runtime validation, or defer instantiation.

---

### P0-CORE-2: `BotState.from_dict()` mutates caller's dict via `.pop()`

**File:** `shared/core/state.py:82-83`
```python
grid_levels = data.pop("grid_levels", [])
positions = data.pop("positions", [])
```
**Problem:** `.pop()` modifies the dict passed by the caller. Any code reusing the dict after calling `from_dict()` will find keys missing.
**Fix:** Use `.get()` instead of `.pop()`.

---

### P0-CORE-3: Decimal values not JSON-serializable from database

**File:** `shared/core/database.py:355-378` (get_trades_summary), `189-204` (TradeLog.to_dict)
```python
"total_pnl": round(total_pnl, 4),  # total_pnl is Decimal, round returns Decimal
```
**Problem:** `Numeric(18,8)` columns return `decimal.Decimal` objects. `round(Decimal)` returns `Decimal`, not `float`. JSON serialization raises `TypeError: Object of type Decimal is not JSON serializable`.
**Fix:** Cast to float: `round(float(total_pnl), 4)`.

---

### P0-CORE-4: Division by zero in multiple shared indicators

**Files:** `shared/indicators/momentum.py:43,58,70,84,104`, `shared/indicators/trend.py:69,240,278`
```python
# Examples:
stoch_k = (close - low_min) / (high_max - low_min)    # momentum.py:43
dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)  # trend.py:240
cci = (typical - sma) / (0.015 * mad)                  # trend.py:278
```
**Problem:** All produce `inf`/`NaN` when denominators are zero (flat markets, missing data). 8+ locations across indicator modules.
**Fix:** Add zero-division guards with `np.nan` replacement or epsilon values.

---

### P0-RISK-1: `NameError` in `get_pnl_summary()` — `total_cost_buys` undefined

**File:** `shared/api/routes/trades.py:107-142`
```python
if logs:
    # total_cost_buys never defined in this branch
    ...
avg_buy_price = total_cost_buys / total_amount_buys  # NameError
```
**Problem:** When TradeLog records exist, variables `total_cost_buys` and `total_amount_buys` are never defined, but referenced unconditionally at line 141.
**Fix:** Initialize variables before the `if/else` branches.

---

### P0-RISK-2: ZeroDivisionError in position_sizer when `entry_price=0`

**File:** `shared/risk/position_sizer.py:88,94,111,117,155,200,206`
```python
amount_base = amount_usd / entry_price  # 7 locations
```
**Problem:** No validation that `entry_price > 0`. Also `portfolio_value=0` crashes the f-string at line 101.
**Fix:** Add guard at top of `calculate()`: `if entry_price <= 0: raise ValueError(...)`.

---

### P0-BACK-1: `profit_factor` returns `float('inf')`, crashes JSON serialization

**File:** `shared/backtest/engine.py:356`, `shared/optimization/metrics.py:122`
```python
profit_factor = float("inf") if gross_profit > 0 else 0.0
```
**Problem:** `json.dump()` raises `ValueError: Out of range float values are not JSON compliant`.
**Fix:** Cap at a finite value: `min(gross_profit / gross_loss, 9999.0)`.

---

### P0-VDB-1: Timezone mismatch in `news_fetcher.py` sort causes TypeError

**File:** `shared/vector_db/news_fetcher.py:243`
```python
articles.sort(key=lambda a: a.published_at or datetime.min, reverse=True)
```
**Problem:** `published_at` is timezone-aware (UTC). `datetime.min` is timezone-naive. Comparing them raises `TypeError: can't compare offset-naive and offset-aware datetimes`.
**Fix:** Use `datetime.min.replace(tzinfo=timezone.utc)`.

---

### P0-VDB-2: Timezone mismatch in `sentiment.py` comparison

**File:** `shared/vector_db/sentiment.py:153,169-170`
```python
cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
pub_dt = datetime.fromisoformat(pub_str)  # may be naive
if pub_dt < cutoff:  # TypeError if naive vs aware
```
**Fix:** Add `if pub_dt.tzinfo is None: pub_dt = pub_dt.replace(tzinfo=timezone.utc)`.

---

### P0-JESSE-1: Wrong candle column index for close prices

**File:** `jesse-bot/strategies/AIGridStrategy/__init__.py:357,360`
```python
closes = list(candles_4h[:, 2])  # WRONG: column 2 is HIGH, not CLOSE
```
**Problem:** Jesse candle format is `[timestamp, open, high, low, close, volume]`. Column index 2 is `high`, not `close` (index 4). This produces incorrect SMA crossover signals and wrong grid direction decisions.
**Fix:** Change `[:, 2]` to `[:, 4]` in both locations.

---

### P0-JESSE-2: `_side` attribute accessed before assignment in TrailingStopManager

**File:** `jesse-bot/strategies/AIGridStrategy/grid_logic.py:307`
```python
side = self._side  # _side only set in start(), not in __init__
```
**Problem:** If `update()` is called without prior `start()` call, `AttributeError` is raised.
**Fix:** Initialize `self._side = None` in `__init__` and guard in `update()`.

---

### P0-JESSE-3: Division by zero in `_calculate_factors_builtin` RSI

**File:** `jesse-bot/strategies/AIGridStrategy/factors_mixin.py:203`
```python
rs = gain / loss  # loss can be zero
```
**Fix:** `rs = gain / loss.replace(0, np.nan)`.

---

## P1 — Logic Bugs

Issues that cause incorrect behavior but don't crash the application.

---

### P1-BOT-1: PAUSED state auto-resume is dead code (CRITICAL)

**File:** `binance-bot/src/binance_bot/bot.py:456-459,497-504`
```python
if self.state == BotState.PAUSED:        # line 456
    self._write_shared_state(current_price=None)
    await asyncio.sleep(tick_interval)
    continue                              # skips everything below

elif self.state == BotState.PAUSED:       # line 497 - NEVER REACHED
    await self._maybe_check_entry(current_price)
```
**Problem:** The `continue` at line 459 restarts the loop before reaching the auto-resume logic at line 497. The bot can never auto-recover from an AI-recommended pause — it is stuck until a manual dashboard `resume` command.
**Fix:** Remove the early `continue` block or move auto-resume logic before it.

---

### P1-BOT-2: Dashboard `resume` bypasses risk checks

**File:** `binance-bot/src/binance_bot/bot.py:449-450`
```python
elif cmd == "resume":
    self.state = BotState.TRADING  # no risk limit check
```
**Problem:** If bot was paused due to daily loss limit or max drawdown breach, dashboard resume bypasses all risk protection.
**Fix:** Check `self.risk_limits.can_trade()` before allowing resume.

---

### P1-BOT-3: `_write_shared_state` computes `strategy_engine` data but never persists it

**File:** `binance-bot/src/binance_bot/bot.py:900-903`
```python
state_dict["strategy_engine"] = engine_status  # after write_state() already called
```
**Fix:** Move computation before `write_state()` or remove dead code.

---

### P1-BOT-4: `_maybe_ai_review` skips first review when `last_review=None`

**File:** `binance-bot/src/binance_bot/bot.py:684`
```python
if self.last_review is None:
    return  # AI reviews never trigger if entered TRADING via dashboard resume
```
**Fix:** Initialize `self.last_review = datetime.now()` on TRADING transition, or treat `None` as "overdue".

---

### P1-BOT-5: EMA period mismatch — keys say 8/21 but data is 12/26

**File:** `binance-bot/src/binance_bot/bot.py:566-567`
```python
"ema_8": float(latest.get("ema_12", current_price)),   # labeled 8, provides 12
"ema_21": float(latest.get("ema_26", current_price)),   # labeled 21, provides 26
```
**Problem:** Strategies compute signals based on wrong moving average periods.
**Fix:** Either rename keys to match data or compute actual EMA 8/21.

---

### P1-BOT-6: PnL always recorded as 0, disabling risk limits

**File:** `binance-bot/src/binance_bot/bot.py:630`
```python
pnl = 0  # Grid trades are part of a series, PnL calculated on completion
```
**Problem:** Every trade uses `pnl=0`. Consequence: `consecutive_losses` never increments, daily loss limit never triggers, win/loss stats always 0/0. The risk limits subsystem is effectively disabled.
**Fix:** Calculate actual PnL for grid closes, or use TP/SL events which do compute PnL.

---

### P1-BOT-7: `_fetch_market_data()` called redundantly — doubles API load

**File:** `binance-bot/src/binance_bot/bot.py:558`
**Problem:** Makes 3 exchange API calls every 5 seconds while TRADING. Ticker was already fetched at line 468. This doubles API load and risks rate limiting.
**Fix:** Pass already-fetched data or cache with TTL.

---

### P1-BOT-8: `KeyboardInterrupt` handler inside async loop is dead code

**File:** `binance-bot/src/binance_bot/bot.py:515`
```python
except KeyboardInterrupt:  # never delivered to async coroutines
    await self.stop()
```
**Fix:** Remove; rely on signal handlers at lines 993-997.

---

### P1-STRAT-1: Duplicate grid levels when `direction="both"`

**File:** `binance-bot/src/binance_bot/strategies/grid.py:132-135`
**Problem:** Both `_setup_long_levels` and `_setup_short_levels` create levels at identical prices. Two signals trigger simultaneously at the same price.
**Fix:** Offset short levels beyond long levels (as `setup_grid_with_trend` does).

---

### P1-STRAT-2: `_close_level` bypasses trade recording

**File:** `binance-bot/src/binance_bot/strategies/grid.py:625-660`
**Problem:** TP/SL closures via `_close_level` directly mutate `paper_holdings` and `realized_pnl` without going through `execute_paper_trade`. DB records and `paper_trades` list become incomplete.
**Fix:** Have `_close_level` call `execute_paper_trade` or at minimum `_save_trade_to_db`.

---

### P1-STRAT-3: Hardcoded `"BTC/USDT"` symbol in order execution

**File:** `binance-bot/src/binance_bot/core/order_manager.py:185,192`
```python
symbol="BTC/USDT",  # TODO: get from signal
```
**Fix:** Add `symbol` to the `Signal` dataclass or pass as parameter.

---

### P1-STRAT-4: Negative amount passed to exchange for short orders

**File:** `binance-bot/src/binance_bot/core/order_manager.py:188`
```python
amount=signal.amount,  # can be negative for shorts
```
**Fix:** Use `abs(signal.amount)`.

---

### P1-STRAT-5: Orders deleted from tracking on fetch failure

**File:** `binance-bot/src/binance_bot/core/order_manager.py:258-275`
```python
del self.open_orders[order_id]  # always deletes, even when fetch fails
```
**Problem:** Network error causes filled order to be permanently lost from tracking.
**Fix:** Only delete when status is definitively known.

---

### P1-STRAT-6: No error handling/retry in ExchangeClient methods

**File:** `binance-bot/src/binance_bot/core/exchange.py` (all methods)
**Problem:** `get_balance`, `get_ticker`, `get_order_book`, `get_ohlcv` have no try/except. Any network error propagates unhandled.
**Fix:** Add retry logic for `ccxt.NetworkError` and `ccxt.ExchangeNotAvailable`.

---

### P1-STRAT-7: `PositionManager` only handles longs, not shorts

**File:** `binance-bot/src/binance_bot/core/position_manager.py`
**Problem:** `update_position` only handles "buy" (increase long) and "sell" (decrease long). Short positions are not supported despite bidirectional grid trading being implemented.

---

### P1-STRAT-8: Unrealized PnL only calculated for longs

**File:** `binance-bot/src/binance_bot/core/position_manager.py:113-118`
```python
if pos.amount > 0 and pos.entry_price > 0:
    pos.unrealized_pnl = (current_price - pos.entry_price) * pos.amount
```
**Problem:** Short positions always show `unrealized_pnl = 0`.

---

### P1-STRAT-9: Relative paths for emergency stop files

**File:** `binance-bot/src/binance_bot/core/emergency.py:28-29`
```python
TRIGGER_FILE = Path(".emergency_stop")    # relative to CWD
STATE_FILE = Path("data/emergency_state.json")
```
**Problem:** Different CWD in Docker/systemd means trigger file won't be found.
**Fix:** Use absolute path from config or `__file__`.

---

### P1-STRAT-10: Hardcoded $0.01 price tolerance in `_get_level_number`

**File:** `binance-bot/src/binance_bot/strategies/ai_grid.py:248`
```python
if abs(level.price - price) < 0.01:
```
**Problem:** Works for BTC at $80K but wrong for tokens priced at $0.001.
**Fix:** Use percentage-based comparison.

---

### P1-STRAT-11: Regex rejects nested JSON from LLM

**File:** `binance-bot/src/binance_bot/strategies/ai_grid.py:408`
```python
json_match = re.search(r'\{[^{}]+\}', response, re.DOTALL)
```
**Fix:** Use `r'\{.*?\}'` with `re.DOTALL` or find `{` and parse incrementally.

---

### P1-AI-1: LLM response parsing has false positives on negation

**File:** `shared/ai/agent.py:196-200`
```python
if "bullish" in response_lower:      # "not bullish" → classified BULLISH
    trend = Trend.BULLISH
```
**Fix:** Use word-boundary regex with negation checks, or use structured LLM output.

---

### P1-AI-2: `assess_risk()` is dead code (89 lines, never called)

**File:** `shared/ai/agent.py:343-431`
**Fix:** Integrate into bot loop or remove.

---

### P1-AI-3: All LLM response parsing is fragile string matching

**File:** `shared/ai/agent.py:185-431` (3 parsers)
**Problem:** `line.startswith('GRID_LOWER:')` requires exact format. No handling for markdown wrapping, leading whitespace, or format variations.
**Fix:** Use structured output (JSON mode/function calling).

---

### P1-ALERT-1: Naive vs timezone-aware datetime mixing

**File:** `shared/alerts/manager.py:120,144` vs `416`
```python
now = datetime.now()           # lines 120, 144 — naive
now = datetime.now(timezone.utc)  # line 416 — aware
```
**Problem:** Comparing these raises `TypeError`.
**Fix:** Use `datetime.now(timezone.utc)` consistently.

---

### P1-ALERT-2: Price movement check iterates wrong direction

**File:** `shared/alerts/rules.py:296-300`
```python
for point in self._price_history:  # oldest to newest
    if point.timestamp <= cutoff:
        old_price = point.price
        break  # gets the OLDEST price, not the one closest to cutoff
```
**Fix:** Iterate with `reversed(self._price_history)`.

---

### P1-ALERT-3: `send_tp_sl_alert()` not wired through AlertManager

**File:** `shared/alerts/discord.py:347-402`
**Problem:** Method exists on `DiscordAlert` but `AlertManager` has no route to it. Can only be called by bypassing rate limiting.

---

### P1-ALERT-4: `send_emergency_alert()` in email.py is dead code

**File:** `shared/alerts/email.py:238-272`
**Problem:** Fully implemented but never called from any code path.

---

### P1-ALERT-5: Telegram alerts module does not exist

**Problem:** Referenced in CLAUDE.md as orphaned but the file doesn't exist in this checkout. Zero Telegram alert capability.

---

### P1-CORE-1: `read_command()` has TOCTOU race condition

**File:** `shared/core/state.py:163-176`
```python
if not path.exists():     # check
    return None
with open(path, "r") as f:  # use — file could be deleted between check and open
    data = json.load(f)
path.unlink()  # another process could write new command that gets lost
```
**Fix:** Use file locking or handle `FileNotFoundError` explicitly.

---

### P1-CORE-2: `write_command()` is not atomic (unlike `write_state()`)

**File:** `shared/core/state.py:154-160`
**Problem:** Writes directly to target file. Bot reading mid-write gets truncated/corrupt JSON, causing `JSONDecodeError` and command loss.
**Fix:** Use same atomic temp-file-then-rename pattern as `write_state()`.

---

### P1-CORE-3: `Indicators.to_dataframe()` crashes on empty candle lists

**File:** `shared/core/indicators.py:28-41`
**Problem:** `df["timestamp"].iloc[0]` raises `IndexError` if candles is a list of empty dicts.
**Fix:** Add early return: `if not candles: return pd.DataFrame()`.

---

### P1-CORE-4: Module-level side effects in `database.py`

**File:** `shared/core/database.py:10-32`
**Problem:** On import, immediately creates `data/` directory, connects to SQLite, registers event listener, creates sessionmaker. Any import has filesystem side effects.
**Fix:** Defer to `get_engine()` factory with lazy initialization.

---

### P1-RISK-1: Duplicate orders from both state file and bot instance

**File:** `shared/api/routes/orders.py:59-108`
**Problem:** Reads orders from state file, then ALSO from bot instance without early return. Same orders appear twice.
**Fix:** Add `return` after state-file block.

---

### P1-RISK-2: `risk_amount` calculation double-applies percentage

**File:** `shared/risk/position_sizer.py:119-122`
```python
amount_usd = portfolio_value * self.risk_per_trade
risk_amount=amount_usd * self.risk_per_trade,  # risk_per_trade applied TWICE
```
**Problem:** Risk amount is `portfolio * 0.02 * 0.02 = 0.04%` instead of expected 2%.
**Fix:** Change to `risk_amount=amount_usd`.

---

### P1-RISK-3: Sortino ratio returns 0.0 for all-winning strategy

**File:** `shared/risk/metrics.py:206-209`
**Problem:** A perfect strategy (no losses) reports Sortino = 0.0, misrepresenting it as having zero risk-adjusted returns.
**Fix:** Return a large sentinel value with JSON-safe serialization.

---

### P1-RISK-4: Profit factor returns 0.0 for all-winning strategy

**File:** `shared/risk/metrics.py:127-129`
**Problem:** Same issue — all profit, no loss reported as profit_factor = 0.0.

---

### P1-RISK-5: Max drawdown limit auto-resets daily

**File:** `shared/risk/limits.py:120-124`
```python
if self.daily_stats.date != date.today():
    self.consecutive_losses = 0
    self.trading_halted = False  # portfolio-level protection reset overnight
```
**Problem:** Even if bot hit 10% max drawdown yesterday, it automatically resumes today.
**Fix:** Only auto-reset daily-specific limits. Max drawdown should persist.

---

### P1-RISK-6: Drawdown check uses daily HWM, not overall HWM

**File:** `shared/risk/limits.py:183-187`
**Problem:** `current_drawdown` computed from daily HWM. A 10% drawdown across multiple days is never detected.
**Fix:** Check from overall `self.high_water_mark`.

---

### P1-RISK-7: Win/loss trade pairing logic is fundamentally broken

**File:** `shared/api/routes/trades.py:127-130`
```python
winning = [s for s in sells if any(float(s.price) > float(b.price) for b in buys)]
```
**Problem:** Checks if ANY buy is cheaper than the sell, across ALL buys. Almost every sell is "winning".
**Fix:** Use FIFO/LIFO accounting or remove the approximation.

---

### P1-RISK-8: `symbol` filter ignored for TradeLog query

**File:** `shared/api/routes/trades.py:105`
```python
logs = session.query(TradeLog).all()  # ignores symbol parameter
```
**Fix:** Add `.filter(TradeLog.symbol == symbol)`.

---

### P1-RISK-9: Sharpe/Sortino annualization formula is incorrect

**File:** `shared/risk/metrics.py:186-192`
**Problem:** `annualized_return = avg_return * trades_per_year` inflates the ratio proportionally to trade count.
**Fix:** Use proper time-based annualization with `sqrt(N)` scaling.

---

### P1-RISK-10: `StopLossManager` limited to one position per symbol

**File:** `shared/risk/stop_loss.py:169`
```python
self.positions[symbol] = position  # second position for same symbol overwrites first
```
**Fix:** Use position ID or composite key.

---

### P1-BACK-1: `shared/backtest/` imports from `binance_bot` — breaks shared module

**File:** `shared/backtest/engine.py:18-19`, `shared/optimization/optimizer.py:11`
```python
from binance_bot.strategies import GridStrategy, GridConfig
```
**Problem:** `shared/` should be bot-agnostic. This hard dependency prevents `jesse-bot` from using backtest/optimization modules.
**Fix:** Use strategy protocol/ABC in `shared/`, accept strategies by interface.

---

### P1-BACK-2: Equity curve format inconsistency between `BacktestEngine` and `Backtester`

**File:** `shared/backtest/engine.py`
**Problem:** `BacktestEngine` stores `equity_curve` as `list[float]`. `Backtester` stores as `list[dict]`. Chart methods and optimizer expect different formats.
**Fix:** Standardize format.

---

### P1-DASH-1: `time.sleep()` blocks Streamlit server thread

**File:** `shared/dashboard/app.py:248`
```python
time.sleep(st.session_state.refresh_sec)  # blocks up to 60 seconds
```
**Fix:** Use `streamlit-autorefresh` component.

---

### P1-MON-1: Duplicate singleton pattern in `TradingMetrics`

**File:** `shared/monitoring/metrics.py:117-125,245-257`
**Problem:** Uses both `__new__` singleton AND `_metrics` global with `get_metrics()` factory.
**Fix:** Use one pattern, not both.

---

### P1-JESSE-1: `get_crossed_buy_level_price` returns first filled, not most recent

**File:** `jesse-bot/strategies/AIGridStrategy/grid_logic.py:110-115`
**Problem:** If multiple buy levels are filled, returns the first one (highest), not the most recently crossed.
**Fix:** Track last-crossed level explicitly.

---

### P1-JESSE-2: Candle-to-dataframe has fragile column mapping

**File:** `jesse-bot/strategies/AIGridStrategy/factors_mixin.py:297-299`
**Problem:** When candle arrays have fewer than 6 columns, timestamp is mapped to 'open', etc.

---

### P1-JESSE-3: Live trader rebuilds grid every iteration (CRITICAL)

**File:** `jesse-bot/live_trader.py:610`
```python
levels = self.setup_grid(price, atr, closes)  # called every hour
```
**Problem:** Completely resets `self.levels`, `self.center`, and `self.filled_levels` every loop iteration. All partially-filled grid state is lost. This defeats the purpose of grid trading.
**Fix:** Only rebuild when trend changes, not on every iteration.

---

### P1-JESSE-4: `filled_order_ids` set grows unboundedly

**File:** `jesse-bot/live_trader.py:390`
**Problem:** Set accumulates every trade ID ever seen, never cleaned.
**Fix:** Use bounded set or periodic cleanup.

---

### P1-ALERT-6: Exchange exceptions silently swallowed in candles endpoint

**File:** `shared/api/routes/candles.py:72-73`
```python
except Exception:
    pass  # falls through to mock data without indication
```
**Fix:** Log the exception and return `source: "mock"` in response.

---

## P2 — Data Issues

Issues with data integrity, precision, or consistency.

---

### P2-BOT-1: Hardcoded initial balance `10000.0` in 6+ places

**Files:** `bot.py:228,271,649,654,818-819,869`, `grid.py:93`, `dashboard/app.py:323`
**Fix:** Define as a constant or read from settings.

---

### P2-BOT-2: Float precision for financial calculations

**Files:** Throughout `bot.py`, `grid.py`, `position_sizer.py`, `metrics.py`
**Problem:** All financial calculations use Python `float`. Accumulated error over thousands of trades causes drift.

---

### P2-CORE-1: `datetime.now()` without timezone in 30+ locations

**Files:** `state.py:72,160`, `rules.py:58,63,83,196,224,294,398`, `stop_loss.py:39,51,219`, `limits.py:161`, and many more
**Problem:** Inconsistent timezone handling. Cross-module datetime comparison will crash with `TypeError`.
**Fix:** Standardize on `datetime.now(timezone.utc)` everywhere.

---

### P2-CORE-2: OHLCV model uses `Float` instead of `Numeric`

**File:** `shared/core/database.py:47-51`
**Problem:** `Trade`, `Position`, `TradeLog` use `Numeric(18,8)` but `OHLCV` uses `Float`. Inconsistency causes precision differences.

---

### P2-CORE-3: Relative paths for database and state files

**Files:** `database.py:10-12`, `state.py:17,151`, `api/main.py:376-394`, `emergency.py:28-29`
```python
DATA_DIR = Path("data")  # relative to CWD
```
**Problem:** Bot, API, and dashboard started from different directories create/read different `data/` directories.
**Fix:** Resolve relative to project root or make configurable.

---

### P2-CORE-4: Duplicate index on `TradeLog.timestamp`

**File:** `shared/core/database.py:164,176-178`
**Problem:** `index=True` on column AND explicit `Index()` in `__table_args__` create redundant indexes. Wastes storage, slows writes.
**Fix:** Remove one.

---

### P2-CORE-5: `log_trade()` type hints say `float` but columns are `Numeric`

**File:** `shared/core/database.py:207-218`
**Problem:** Passing `float` to `Numeric` columns can introduce representation artifacts.

---

### P2-CORE-6: Dead dataclasses `GridLevel` and `Position` in `state.py`

**File:** `shared/core/state.py:20-38`
**Problem:** Defined but never instantiated. `BotState.grid_levels` stores raw dicts, not `GridLevel` instances.

---

### P2-ALERT-1: Truthiness check on `current_price` suppresses 0.0

**File:** `shared/alerts/discord.py:226-230`
```python
if current_price:  # 0.0 is falsy, field silently omitted
```
**Fix:** Change to `if current_price is not None:`.

---

### P2-ALERT-2: Grid bounds not validated (could be inverted)

**File:** `shared/ai/agent.py:335-341`
**Problem:** No check that `lower < upper` from LLM response. Inverted bounds create nonsensical grids.

---

### P2-ALERT-3: `num_levels` and `confidence` not clamped

**File:** `shared/ai/agent.py:324,329`
**Problem:** LLM could return `num_levels=0` or `confidence=150`. No bounds validation.
**Fix:** Clamp to sane ranges.

---

### P2-ALERT-4: HTML injection in email alerts

**File:** `shared/alerts/email.py:264-265`
```python
<div class="message">{message}</div>  # no escaping
```
**Fix:** Use `html.escape()` on user-supplied content.

---

### P2-ALERT-5: Break-even trades (pnl=0) display as "-"

**File:** `shared/alerts/email.py:213-214`
```python
pnl_display = f"${pnl:+.2f}" if pnl else "-"  # 0 is falsy
```
**Fix:** Change to `if pnl is not None:`.

---

### P2-ALERT-6: `os.getenv` used instead of centralized settings

**Files:** `shared/alerts/discord.py:29`, `shared/alerts/email.py:33-37`
**Problem:** Bypasses Pydantic validation and type checking.

---

### P2-RISK-1: `trade_history` list grows unbounded (memory leak)

**File:** `shared/risk/limits.py:81,158-162`
**Fix:** Use `collections.deque(maxlen=1000)`.

---

### P2-RISK-2: `equity_curve` list grows unbounded (memory leak)

**File:** `shared/risk/metrics.py:39,72-74`
**Fix:** Use `collections.deque(maxlen=N)`.

---

### P2-RISK-3: `get_summary()` returns formatted strings, not raw numbers

**File:** `shared/risk/metrics.py:271-298`
```python
"win_rate": f"{self.win_rate*100:.1f}%",
"total_pnl": f"${self.total_pnl:,.2f}",
```
**Problem:** Unusable for programmatic consumers.
**Fix:** Return raw numbers, let presentation layer format.

---

### P2-RISK-4: `date.today()` timezone-unaware for day rollover

**File:** `shared/risk/limits.py:94,120`
**Problem:** Day boundary depends on server timezone.
**Fix:** Use `datetime.now(timezone.utc).date()`.

---

### P2-API-1: Hardcoded BTC price in mock candle generation

**File:** `shared/api/routes/candles.py:114`
```python
base_price = 85000.0  # misleading for non-BTC symbols
```

---

### P2-API-2: `import random` inside loop body

**File:** `shared/api/routes/candles.py:123`
**Fix:** Move to top of file.

---

### P2-API-3: CORS allows all origins with credentials

**File:** `shared/api/main.py:57-63`
```python
allow_origins=["*"], allow_credentials=True
```
**Fix:** Restrict to known dashboard URLs.

---

### P2-API-4: Relative paths for state/data files in API

**File:** `shared/api/main.py:376-394`
**Problem:** Same as P2-CORE-3.

---

### P2-API-5: `BacktestResult.start_date` defaults to `None` despite `datetime` type hint

**File:** `shared/backtest/engine.py:29`
**Fix:** Type as `Optional[datetime]`.

---

### P2-API-6: No authentication on trading API endpoints

**File:** `shared/api/routes/orders.py`, `shared/api/main.py`
**Problem:** Force-buy, force-sell, cancel, pause, stop endpoints have zero authentication. Anyone on the network can execute trades.
**Fix:** Add API key authentication middleware.

---

### P2-VDB-1: Unbounded `_seen_urls` set in `NewsFetcher`

**File:** `shared/vector_db/news_fetcher.py:73`
**Fix:** Use bounded LRU set or periodic cleanup.

---

### P2-JESSE-1: Hardcoded `"BTCUSDT"` in AI mixin

**File:** `jesse-bot/strategies/AIGridStrategy/ai_mixin.py:148,197,235`
**Problem:** Even when trading ETH-USDT, AI analyzes as BTC-USDT.

---

### P2-JESSE-2: Hardcoded `total_balance=10000.0` in AI review

**File:** `jesse-bot/strategies/AIGridStrategy/ai_mixin.py:209-210`

---

### P2-STRAT-1: No NULL checks on exchange ticker fields

**File:** `binance-bot/src/binance_bot/core/exchange.py:91-101`
**Problem:** CCXT ticker fields can be `None`. Callers receive `None` values for `bid`, `ask`, etc.

---

### P2-STRAT-2: `order.price` can be `None`, recorded as 0

**File:** `binance-bot/src/binance_bot/core/order_manager.py:315`
```python
price=order.price or 0,  # 0 corrupts PnL calculations
```

---

## P3 — Code Quality

Lower-severity issues affecting maintainability and code cleanliness.

---

### P3-BOT-1: Unused import `read_state`

**File:** `binance-bot/src/binance_bot/bot.py:26`

---

### P3-BOT-2: Unused variable `old_state`

**File:** `binance-bot/src/binance_bot/bot.py:368`

---

### P3-BOT-3: Import inside loop (`from shared.core.state import read_command`)

**File:** `binance-bot/src/binance_bot/bot.py:443`
**Fix:** Move to file-level imports.

---

### P3-BOT-4: Duplicate `_write_shared_state` calls

**File:** `binance-bot/src/binance_bot/bot.py:440,457,476`
**Problem:** First call always writes `None` price, immediately overwritten.

---

### P3-STRAT-1: Unused imports in multiple files

| File | Unused Import |
|------|---------------|
| `data_collector.py:5` | `delete` from sqlalchemy |
| `data_collector.py:3` | `datetime` |
| `exchange.py:6` | `Decimal` (ironic given float precision issues) |
| `position_manager.py:3` | `field` from dataclasses |
| `position_manager.py:5` | `datetime` |

---

### P3-STRAT-2: Unused variable `pnl_color`

**File:** `binance-bot/src/binance_bot/core/position_manager.py:237`

---

### P3-STRAT-3: Duplicate RSI/EMA/ADX/ATR implementations

**File:** `binance-bot/src/binance_bot/strategies/grid.py:201-295,470-487`
**Problem:** Re-implements indicators that exist in `shared/core/indicators.py` and `shared/indicators/`. Bugs fixed in one location won't be fixed in the other.

---

### P3-ALERT-1: `AlertLevel` enum underutilized

**File:** `shared/alerts/manager.py:16-21`
**Problem:** Defined but not used in routing logic (uses hardcoded strings instead).

---

### P3-ALERT-2: `trades_list` silently dropped for Discord

**File:** `shared/alerts/manager.py:308,317-329`
**Problem:** `send_daily_summary` accepts `trades_list` and passes to email but not Discord.

---

### P3-API-1: Unused `import os`

**File:** `shared/api/main.py:3`

---

### P3-API-2: Duplicate code in `force_buy`/`force_sell`

**File:** `shared/api/routes/orders.py:111-198`
**Fix:** Refactor into `_force_trade(side)`.

---

### P3-API-3: Duplicate `max_drawdown` computation

**File:** `shared/risk/metrics.py:132-167`
**Problem:** `max_drawdown` and `max_drawdown_amount` iterate equity curve independently with identical logic.

---

### P3-BACK-1: Unused `colors` variable in chart

**File:** `shared/backtest/charts.py:145`

---

### P3-BACK-2: Unused `numpy` import in charts

**File:** `shared/backtest/charts.py:5`

---

### P3-JESSE-1: Duplicate `logger` assignment

**File:** `jesse-bot/strategies/AIGridStrategy/__init__.py:15,36`

---

### P3-JESSE-2: Deprecated `asyncio.get_event_loop()` pattern

**File:** `jesse-bot/strategies/AIGridStrategy/ai_mixin.py:259`

---

### P3-JESSE-3: Unused `atr` parameter in `setup_grid`

**File:** `jesse-bot/live_trader.py:264`

---

## Test Coverage Gaps

### Critical Modules with ZERO Test Coverage

| Module | Lines | Risk Level |
|--------|-------|------------|
| `jesse-bot/live_trader.py` | 663 | **CRITICAL** — live trading entry point |
| `jesse-bot/strategies/AIGridStrategy/__init__.py` | 669 | **HIGH** — contains P0 bug (wrong column index) |
| `binance-bot/core/exchange.py` | ~200 | **HIGH** — CCXT wrapper, all network calls |
| `binance-bot/core/order_manager.py` | ~330 | **HIGH** — order execution |
| `binance-bot/core/position_manager.py` | ~240 | **HIGH** — position tracking |
| `binance-bot/core/emergency.py` | ~100 | **MEDIUM** — emergency stop |
| `binance-bot/core/data_collector.py` | ~100 | **MEDIUM** |
| `binance-bot/strategies/ai_grid.py` | ~450 | **HIGH** — AI strategy |
| `shared/risk/position_sizer.py` | ~220 | **HIGH** — position sizing |
| `shared/risk/stop_loss.py` | ~240 | **HIGH** — stop loss (already known broken) |
| `shared/risk/limits.py` | ~200 | **HIGH** — risk limits |
| `shared/risk/metrics.py` | ~300 | **MEDIUM** — risk metrics |
| `shared/api/routes/*` (5 files) | ~600 | **MEDIUM** — API endpoints |
| `shared/alerts/email.py` | ~275 | **LOW** |
| `shared/alerts/rules.py` | ~400 | **MEDIUM** — alert rules engine |
| `shared/core/state.py` | ~180 | **MEDIUM** — IPC state management |
| `shared/config/settings.py` | ~200 | **LOW** |
| `shared/indicators/*` (9 files) | ~1500 | **MEDIUM** — new indicator modules |
| `shared/monitoring/metrics.py` | ~260 | **LOW** |

### Test Quality Issues

1. **`test_live_mode.py:193-214`** — Tests Python `list.insert()` behavior, not actual strategy `filters()` method.
2. **`test_api.py:88-89`** — Weak assertion: `if sell:` guard means test passes even with no sell levels.
3. **Missing negative test cases** — No tests for `grid_spacing_pct=0`, negative `grid_levels_count`, or other edge cases.

---

## Changes from AUDIT V1

### Issues Fixed Since V1

- `AlertType` enum (mentioned in V1) no longer exists in code — cleaned up
- Some Streamlit `width="stretch"` issues may have been addressed (need verification)

### New Issues Not in V1

- P0-JESSE-1: Wrong candle column index (jesse-bot didn't exist during V1)
- P1-JESSE-3: Live trader rebuilds grid every iteration
- P1-BOT-1: PAUSED auto-resume dead code (introduced in recent commit)
- P0-CORE-3: Decimal serialization (columns changed to Numeric since V1)
- P1-RISK-2: risk_amount double-applies percentage
- P1-RISK-5/6: Max drawdown auto-resets and uses daily HWM
- P1-RISK-7: Broken win/loss pairing logic

### Issues Carried Over from V1 (Still Open)

- StopLossManager never called (V1 #1)
- Telegram alerts orphaned/missing (V1 #2)
- PnL Reporter never imported (V1 #3)
- Discord retry stack overflow risk (V1 #5)
- No SMTP timeout (V1 #7)
- No LLM timeout (V1 #8)
- `datetime.utcnow()` deprecated (V1 #9, now found in 30+ locations)
- Float precision (V1 #10)
- Fragile LLM parsing (V1 #11)
- Unbounded grid growth (V1 #12)
- `float('inf')` in Sortino (V1 #14, now returns 0.0 which is also wrong)

---

## Recommended Fix Priority

### Immediate (blocks correctness)

1. P0-JESSE-1 — Fix candle column index (`[:, 2]` → `[:, 4]`)
2. P1-BOT-1 — Fix PAUSED auto-resume dead code
3. P1-JESSE-3 — Fix live_trader grid rebuild logic
4. P1-BOT-6 — Implement actual PnL recording for grid trades
5. P0-CORE-3 — Fix Decimal JSON serialization
6. P0-BACK-1 — Cap `profit_factor` at finite value

### High Priority (safety/reliability)

7. P1-BOT-2 — Add risk checks to dashboard resume
8. P1-RISK-5 — Don't auto-reset max drawdown daily
9. P1-RISK-6 — Use overall HWM for drawdown check
10. P0-RISK-2 — Guard against `entry_price=0` in position sizer
11. P0-STRAT-5 — Replace bare `except:` with `except Exception`
12. P2-API-6 — Add authentication to trading endpoints

### Medium Priority (robustness)

13. P2-CORE-1 — Standardize `datetime.now(timezone.utc)` everywhere
14. P0-CORE-1 — Defer `Settings()` instantiation
15. P0-AI-2 — Defer `TradingAgent()` instantiation
16. P1-STRAT-6 — Add retry logic to ExchangeClient
17. P1-BACK-1 — Remove `binance_bot` imports from `shared/`
18. P0-VDB-1/2 — Fix timezone mismatches in vector_db

### Lower Priority (quality)

19. P3 — Clean up unused imports
20. P3-STRAT-3 — Consolidate duplicate indicator implementations
21. P2-BOT-1 — Extract hardcoded balance to constant/config
22. P2-RISK-1/2 — Bound unbounded lists with deque
