# Sprint 26: Bot Logic & State Machine — Implementation Plan

**Date:** 2026-03-13
**Branch:** `sprint-26-bot-logic`
**Issues:** 13 (P1-BOT + P1-STRAT)
**Files:** 4 (`bot.py`, `grid.py`, `order_manager.py`, `position_manager.py`)
**Test file:** `tests/unit/test_sprint26_bot_logic.py`

---

## Issue 1: P1-BOT-1 — PAUSED auto-resume is dead code (CRITICAL)

**File:** `binance-bot/src/binance_bot/bot.py`
**Lines:** 462–465 (early continue), 507–514 (unreachable PAUSED block)

**Problem:** The `continue` at line 465 restarts the loop before reaching the auto-resume logic at lines 507–514. The bot can never auto-recover from an AI-recommended pause.

**Current code (lines 462–465):**
```python
if self.state == BotState.PAUSED:
    self._write_shared_state(current_price=None)
    await asyncio.sleep(tick_interval)
    continue
```

**Current code (lines 507–514) — NEVER REACHED:**
```python
elif self.state == BotState.PAUSED:
    # Auto-resume: re-check entry conditions
    await self._maybe_check_entry(current_price)
    # Also run AI review to override previous PAUSE decision
    if self.state == BotState.PAUSED:
        await self._maybe_ai_review(current_price)
```

**Fix:** Remove the early-continue block (lines 462–465). The PAUSED branch at line 507 already handles the state correctly — it re-checks entry conditions and runs AI review. The early continue was preventing all of that. With the early-continue removed, the PAUSED state will:
1. Still fetch the current price (line 474)
2. Update rules engine (lines 482–483)
3. Fall through to the `elif self.state == BotState.PAUSED:` branch (line 507)
4. Run `_maybe_check_entry` which can transition back to TRADING
5. Run `_maybe_ai_review` which can also resume

**Tests:**
- `test_paused_state_runs_auto_resume_logic`: Verify PAUSED state calls `_maybe_check_entry`
- `test_paused_state_runs_ai_review`: Verify PAUSED state calls `_maybe_ai_review`
- `test_paused_state_can_transition_to_trading`: Verify PAUSED → TRADING via entry check

---

## Issue 2: P1-BOT-2 — Dashboard resume bypasses risk checks

**File:** `binance-bot/src/binance_bot/bot.py`
**Lines:** 454–456

**Problem:** Dashboard `resume` command sets `self.state = BotState.TRADING` without checking risk limits. If bot was paused due to daily loss limit or max drawdown, resume bypasses all risk protection.

**Current code:**
```python
elif cmd == "resume":
    logger.info("Received RESUME command from dashboard")
    self.state = BotState.TRADING
```

**Fix:** Check `self.risk_limits.can_trade()` before allowing resume. If risk limits are breached, log a warning and stay PAUSED.

```python
elif cmd == "resume":
    can_trade, reason = self.risk_limits.can_trade()
    if can_trade:
        logger.info("Received RESUME command from dashboard")
        self.state = BotState.TRADING
    else:
        logger.warning(f"Dashboard resume blocked by risk limits: {reason}")
```

**Tests:**
- `test_dashboard_resume_checks_risk_limits`: Verify resume blocked when risk limits breached
- `test_dashboard_resume_allowed_when_risk_ok`: Verify resume works when limits not breached

---

## Issue 3: P1-BOT-4 — `_maybe_ai_review` skips first review

**File:** `binance-bot/src/binance_bot/bot.py`
**Lines:** 694–695

**Problem:** When `last_review is None` (initial state), the method returns early. If the bot enters TRADING via a dashboard resume (which doesn't call `_check_entry_conditions`), `last_review` stays `None` and AI reviews never trigger.

**Current code:**
```python
if self.last_review is None:
    return
```

**Fix:** Treat `None` as "overdue" — trigger an immediate review instead of returning.

```python
if self.last_review is None:
    # First review: trigger immediately
    pass  # Fall through to run the review
else:
    interval = timedelta(minutes=self.config.review_interval_minutes)
    if datetime.now() - self.last_review < interval:
        return
```

This replaces lines 694–699 (the current None check + interval check).

**Tests:**
- `test_ai_review_triggers_when_last_review_none`: Verify first review runs immediately
- `test_ai_review_respects_interval_after_first`: Verify subsequent reviews obey interval

---

## Issue 4: P1-BOT-5 — EMA period mismatch (8/21 vs 12/26)

**File:** `binance-bot/src/binance_bot/bot.py`
**Lines:** 576–577

**Problem:** Dictionary keys say `ema_8` and `ema_21` but actual data comes from `ema_12` and `ema_26`. Strategies compute signals based on wrong moving average periods.

**Current code:**
```python
"ema_8": float(latest.get("ema_12", current_price)),
"ema_21": float(latest.get("ema_26", current_price)),
```

**Fix:** Compute actual EMA 8 and EMA 21 from the indicators DataFrame, since downstream consumers (`momentum_strategy.py:20-27`, `regime.py:129-130`) expect those periods. The regime detector even computes its own EMA 8/21 internally (`regime.py:239-240`), so passing EMA 12/26 under those keys gives wrong crossover signals.

```python
# Compute actual EMA 8/21 from close prices
close = data["indicators_df"]["close"]
"ema_8": float(close.ewm(span=8, adjust=False).mean().iloc[-1]),
"ema_21": float(close.ewm(span=21, adjust=False).mean().iloc[-1]),
```

**Consumer files that read `ema_8`/`ema_21`:**
- `shared/strategies/momentum_strategy.py:20-21,26-27`
- `shared/strategies/regime.py:129-130` (also computes own at `239-240`)

No changes needed in consumers — only fix the producer (bot.py).

**Tests:**
- `test_engine_indicators_ema_keys_match_data`: Verify `ema_8` and `ema_21` contain correct EMA values

---

## Issue 5: P1-BOT-6 — PnL always 0, risk limits disabled (CRITICAL)

**File:** `binance-bot/src/binance_bot/bot.py`
**Lines:** 639–648

**Problem:** Every grid trade records `pnl = 0`. Consequence: `consecutive_losses` never increments, daily loss limit never triggers, win/loss stats always 0/0. The entire risk limits subsystem is effectively disabled.

**Current code (line 640):**
```python
pnl = 0  # Grid trades are part of a series, PnL calculated on completion
```

**Fix:** Calculate actual PnL for sell signals (closing trades). For BUY signals, PnL is 0 (opening position). For SELL signals, compute PnL from the strategy's realized trades.

```python
pnl = 0.0
if signal.type == SignalType.SELL and hasattr(self.strategy, 'long_entry_price'):
    # Closing a long: PnL = (sell_price - entry_price) * amount
    if signal.amount > 0 and self.strategy.long_entry_price > 0:
        pnl = (signal.price - self.strategy.long_entry_price) * signal.amount
    elif signal.amount < 0 and self.strategy.short_entry_price > 0:
        # Opening a short: no realized PnL yet
        pnl = 0.0
elif signal.type == SignalType.BUY and signal.amount < 0:
    # Covering a short: PnL = (entry_price - cover_price) * amount
    if self.strategy.short_entry_price > 0:
        pnl = (self.strategy.short_entry_price - signal.price) * abs(signal.amount)
```

**Tests:**
- `test_sell_trade_records_nonzero_pnl`: Verify sell trades calculate actual PnL
- `test_risk_limits_triggered_on_losses`: Verify consecutive losses actually increment
- `test_short_cover_records_pnl`: Verify short cover PnL calculation

---

## Issue 6: P1-BOT-7 — `_fetch_market_data` called redundantly

**File:** `binance-bot/src/binance_bot/bot.py`
**Lines:** 568 (redundant call), 474 (first fetch)

**Problem:** `_execute_trading` at line 568 calls `_fetch_market_data()` which makes 3 API calls (ticker, order_book, OHLCV). But ticker was already fetched at line 474. This doubles API load every 5 seconds and risks rate limiting.

**Fix:** Pass the ticker data already fetched to `_execute_trading`, and have `_fetch_market_data` accept an optional pre-fetched ticker.

Modify `_execute_trading` signature to accept `ticker`:
```python
async def _execute_trading(self, current_price: float, ticker: dict):
```

Modify `_fetch_market_data` to accept optional ticker:
```python
async def _fetch_market_data(self, ticker: Optional[dict] = None) -> dict:
    if ticker is None:
        ticker = exchange_client.get_ticker(self.symbol)
    ...
```

Update the call at line 502:
```python
await self._execute_trading(current_price, ticker)
```

And inside `_execute_trading`, pass ticker:
```python
data = await self._fetch_market_data(ticker=ticker)
```

**Tests:**
- `test_execute_trading_reuses_ticker`: Verify ticker not fetched twice per tick

---

## Issue 7: P1-BOT-8 — KeyboardInterrupt dead code in async

**File:** `binance-bot/src/binance_bot/bot.py`
**Lines:** 525–527

**Problem:** `KeyboardInterrupt` is never delivered to async coroutines in Python. The signal handlers at lines 1003–1007 already handle SIGINT correctly.

**Current code:**
```python
except KeyboardInterrupt:
    await self.stop()
    break
```

**Fix:** Remove the `except KeyboardInterrupt` block entirely. The `except Exception` block at line 528 handles other errors.

**Tests:**
- `test_signal_handlers_registered`: Verify SIGINT/SIGTERM handlers are set up

---

## Issue 8: P1-STRAT-1 — Duplicate grid levels with direction=both

**File:** `binance-bot/src/binance_bot/strategies/grid.py`
**Lines:** 132–135 (`setup_grid`), 147–169 (`_setup_long_levels`), 171–199 (`_setup_short_levels`)

**Problem:** When `direction="both"`, `_setup_long_levels` creates SELL levels at `center + spacing*i`, and `_setup_short_levels` also creates SELL levels at `center + spacing*i`. Similarly, both create BUY levels at `center - spacing*i`. Two signals trigger simultaneously at the same price.

**Fix:** Offset short levels beyond the long levels. Short SELL levels start after the last long SELL level, and short BUY levels start after the last long BUY level. This is how `setup_grid_with_trend` already handles it (line 354).

```python
def _setup_short_levels(self, center_price: float, offset: int = 0):
    spacing = center_price * (self.config.grid_spacing_pct / 100)

    # Short-sell levels above current price (offset beyond long sells)
    for i in range(1, self.config.grid_levels + 1):
        price = center_price + (spacing * (offset + i))
        level = GridLevel(
            price=price,
            side=SignalType.SELL,
            amount=-self.config.amount_per_level,
        )
        self.levels.append(level)

    # Buy-to-cover levels below current price (offset beyond long buys)
    for i in range(1, self.config.grid_levels + 1):
        price = center_price - (spacing * (offset + i))
        level = GridLevel(
            price=price,
            side=SignalType.BUY,
            amount=-self.config.amount_per_level,
        )
        self.levels.append(level)
```

In `setup_grid`, pass the offset when direction is "both":
```python
if direction in ("long", "both"):
    self._setup_long_levels(current_price)
if direction in ("short", "both"):
    offset = self.config.grid_levels if direction == "both" else 0
    self._setup_short_levels(current_price, offset=offset)
```

**Tests:**
- `test_grid_both_direction_no_duplicate_prices`: Verify all levels have unique prices
- `test_grid_both_direction_correct_count`: Verify level count = 4 × grid_levels
- `test_grid_long_only_no_offset`: Verify long-only grid unchanged

---

## Issue 9: P1-STRAT-2 — `_close_level` bypasses trade recording

**File:** `binance-bot/src/binance_bot/strategies/grid.py`
**Lines:** 628–663

**Problem:** TP/SL closures via `_close_level` directly mutate `paper_holdings` and `realized_pnl` without calling `execute_paper_trade` or `_save_trade_to_db`. Database records and `paper_trades` list become incomplete.

**Fix:** Have `_close_level` call `_save_trade_to_db` and append to `paper_trades` to keep records complete.

Add at the end of `_close_level`, before the logger.info call:
```python
# Record the closing trade
close_signal = Signal(
    type=SignalType.SELL if level.amount > 0 else SignalType.BUY,
    price=exit_price,
    amount=level.amount,
    reason=f"TP/SL close at ${exit_price:,.2f}",
)
is_short = level.amount < 0
self._save_trade_to_db(close_signal, is_short, abs_amount, cost)
self.paper_trades.append({
    "signal": close_signal,
    "status": "filled",
    "balance": self.paper_balance,
    "holdings": self.paper_holdings,
    "long_holdings": self.long_holdings,
    "short_holdings": self.short_holdings,
    "is_short": is_short,
    "pnl": level.pnl,
})
```

**Tests:**
- `test_close_level_records_trade_in_paper_trades`: Verify paper_trades list updated
- `test_close_level_saves_to_db`: Verify _save_trade_to_db called on TP/SL close

---

## Issue 10: P1-STRAT-4 — Negative amount for short orders

**File:** `binance-bot/src/binance_bot/core/order_manager.py`
**Lines:** 187–188 (`execute_signal`)

**Problem:** `signal.amount` can be negative for short-side grid levels. This negative amount is passed directly to exchange API calls, which will reject it or cause unexpected behavior.

**Current code (line 187):**
```python
amount=signal.amount,
```

**Fix:** Use `abs(signal.amount)` in both the market and limit order calls within `execute_signal`.

```python
abs_amount = abs(signal.amount)

if order_type == OrderType.MARKET:
    return self.create_market_order(
        symbol="BTC/USDT",
        side=side,
        amount=abs_amount,
    )
else:
    return self.create_limit_order(
        symbol="BTC/USDT",
        side=side,
        amount=abs_amount,
        price=signal.price,
    )
```

**Tests:**
- `test_execute_signal_uses_abs_amount`: Verify negative amount converted to positive
- `test_execute_signal_preserves_positive_amount`: Verify positive amounts unchanged

---

## Issue 11: P1-STRAT-5 — Orders deleted on fetch failure

**File:** `binance-bot/src/binance_bot/core/order_manager.py`
**Lines:** 258–275 (`sync_orders`)

**Problem:** In `sync_orders`, when an order is no longer in the exchange's open orders list, the code tries to fetch its status. If that fetch fails (network error), the order is still deleted from `self.open_orders` at line 275 — permanently lost from tracking.

**Current code:**
```python
try:
    status = exchange_client.exchange.fetch_order(order_id, symbol)
    ...
except Exception as e:
    logger.warning(f"Failed to fetch order status for {order_id}: {e}")

del self.open_orders[order_id]  # Always runs, even on fetch failure
```

**Fix:** Only delete the order when its status is definitively known. Move the `del` inside the `try` block, after status is confirmed.

```python
for order_id in list(self.open_orders.keys()):
    if order_id not in exchange_ids:
        order = self.open_orders[order_id]
        try:
            status = exchange_client.exchange.fetch_order(order_id, symbol)
            order.status = self._parse_status(status["status"])
            order.filled = status.get("filled", 0)
            order.cost = status.get("cost", 0)

            if order.status == OrderStatus.FILLED:
                self.filled_orders.append(order)
                self._save_trade(order)
                logger.info(f"Order filled: {order}")

            # Only delete after successful status fetch
            del self.open_orders[order_id]
        except Exception as e:
            logger.warning(f"Failed to fetch order status for {order_id}: {e}")
            # Keep order in tracking — will retry on next sync
```

**Tests:**
- `test_sync_orders_keeps_order_on_fetch_failure`: Verify order preserved after network error
- `test_sync_orders_removes_order_on_successful_fetch`: Verify order removed when status known

---

## Issue 12: P1-STRAT-7 — PositionManager only handles longs

**File:** `binance-bot/src/binance_bot/core/position_manager.py`
**Lines:** 37–90 (`update_position`)

**Problem:** `update_position` only handles "buy" (increase long) and "sell" (decrease long). Short positions are not supported despite bidirectional grid trading.

**Fix:** Add `short_amount` and `short_entry_price` fields to `PositionInfo`, then handle "sell_short" and "buy_cover" sides (or detect shorts via a flag).

Add fields to `PositionInfo` dataclass (after line 22):
```python
short_amount: float = 0.0
short_entry_price: float = 0.0
```

Extend `update_position` to handle shorts:
```python
def update_position(self, symbol, side, amount, price, is_short=False):
    ...
    if is_short:
        if side == "sell":
            # Open/increase short
            if pos.short_amount > 0:
                total_cost = (pos.short_entry_price * pos.short_amount) + (price * amount)
                pos.short_amount += amount
                pos.short_entry_price = total_cost / pos.short_amount
            else:
                pos.short_amount = amount
                pos.short_entry_price = price
            pos.side = "short" if pos.amount == 0 else "both"
        else:  # buy (cover short)
            if pos.short_amount >= amount:
                pnl = (pos.short_entry_price - price) * amount
                self.total_realized_pnl += pnl
                pos.realized_pnl += pnl
                pos.short_amount -= amount
                if pos.short_amount <= 0:
                    pos.short_amount = 0
                    pos.short_entry_price = 0
                pos.side = "long" if pos.amount > 0 else "flat"
    else:
        # existing long logic (unchanged)
        ...
```

**Tests:**
- `test_position_manager_open_short`: Verify short position tracked correctly
- `test_position_manager_cover_short_pnl`: Verify short PnL calculated correctly
- `test_position_manager_both_long_and_short`: Verify simultaneous positions

---

## Issue 13: P1-STRAT-8 — Unrealized PnL only for longs

**File:** `binance-bot/src/binance_bot/core/position_manager.py`
**Lines:** 113–118 (`calculate_unrealized_pnl`)

**Problem:** Short positions always show `unrealized_pnl = 0`.

**Current code:**
```python
if pos.amount > 0 and pos.entry_price > 0:
    pos.unrealized_pnl = (current_price - pos.entry_price) * pos.amount
    pos.unrealized_pnl_pct = ((current_price / pos.entry_price) - 1) * 100
else:
    pos.unrealized_pnl = 0.0
    pos.unrealized_pnl_pct = 0.0
```

**Fix:** Calculate unrealized PnL for both longs and shorts:

```python
long_pnl = 0.0
short_pnl = 0.0

if pos.amount > 0 and pos.entry_price > 0:
    long_pnl = (current_price - pos.entry_price) * pos.amount

if pos.short_amount > 0 and pos.short_entry_price > 0:
    short_pnl = (pos.short_entry_price - current_price) * pos.short_amount

pos.unrealized_pnl = long_pnl + short_pnl

total_cost = (pos.entry_price * pos.amount) + (pos.short_entry_price * pos.short_amount)
if total_cost > 0:
    pos.unrealized_pnl_pct = (pos.unrealized_pnl / total_cost) * 100
else:
    pos.unrealized_pnl_pct = 0.0
```

**Tests:**
- `test_unrealized_pnl_short_position`: Verify short PnL = (entry - current) × amount
- `test_unrealized_pnl_both_positions`: Verify combined long + short PnL
- `test_unrealized_pnl_no_position`: Verify 0 when flat

---

## Implementation Order

Execute in this order to minimize conflicts:

1. **P1-BOT-8** — Remove KeyboardInterrupt dead code (trivial, no dependencies)
2. **P1-BOT-1** — Fix PAUSED auto-resume (remove early continue block)
3. **P1-BOT-2** — Add risk checks to dashboard resume
4. **P1-BOT-4** — Fix first AI review skip
5. **P1-BOT-5** — Fix EMA key mismatch
6. **P1-BOT-7** — Reduce redundant API calls
7. **P1-BOT-6** — Implement actual PnL recording (depends on strategy state)
8. **P1-STRAT-1** — Fix duplicate grid levels
9. **P1-STRAT-2** — Fix _close_level trade recording
10. **P1-STRAT-4** — Fix negative amount in orders
11. **P1-STRAT-5** — Fix order deletion on fetch failure
12. **P1-STRAT-7** — Add short position support to PositionManager
13. **P1-STRAT-8** — Add short unrealized PnL (depends on #12)

---

## Test Plan

**File:** `tests/unit/test_sprint26_bot_logic.py`

### Test Classes

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestP1Bot1PausedAutoResume` | 3 | State machine PAUSED → TRADING transition |
| `TestP1Bot2DashboardResume` | 2 | Risk-gated resume |
| `TestP1Bot4FirstAiReview` | 2 | AI review with last_review=None |
| `TestP1Bot5EmaPeriodMatch` | 1 | EMA key/value consistency |
| `TestP1Bot6PnlRecording` | 3 | Non-zero PnL for sell/cover trades |
| `TestP1Bot7RedundantFetch` | 1 | Ticker reuse verification |
| `TestP1Bot8KeyboardInterrupt` | 1 | Signal handler setup |
| `TestP1Strat1DuplicateLevels` | 3 | Unique prices in both-direction grid |
| `TestP1Strat2CloseLevelRecording` | 2 | TP/SL trade recording |
| `TestP1Strat4NegativeAmount` | 2 | abs(amount) in execute_signal |
| `TestP1Strat5OrderDeletionOnFailure` | 2 | Order preservation on fetch error |
| `TestP1Strat7ShortPositions` | 3 | Short position tracking |
| `TestP1Strat8ShortUnrealizedPnl` | 3 | Short unrealized PnL calculation |
| **Total** | **28** | |

### EMA Key Consumer Check

**VALIDATION NOTE:** No consumer changes needed. The fix computes actual EMA 8/21 values for the `ema_8`/`ema_21` keys, so all consumers (`momentum_strategy.py:20-21,26-27`, `regime.py:129-130`) will receive correct data without modification. The previous note suggesting consumers update to `ema_12` was incorrect — the whole point is to fix the producer to match what consumers expect.

Consumers verified:
- `shared/strategies/momentum_strategy.py:20-21,26-27` — reads `ema_8`/`ema_21` ✅
- `shared/strategies/regime.py:129-130` — reads `ema_8`/`ema_21` ✅
- `shared/strategies/regime.py:239-240` — computes own EMA 8/21 internally ✅

### Risk for P1-BOT-6

The PnL fix changes risk subsystem behavior. After implementation, verify:
- Risk limits actually trigger on consecutive losses
- Daily loss limit halts trading as expected
- PnL values are reasonable (not wildly wrong due to entry price tracking)

---

## Files Modified Summary

| File | Issues | Changes |
|------|--------|---------|
| `binance-bot/src/binance_bot/bot.py` | P1-BOT-1,2,4,5,6,7,8 | 7 fixes |
| `binance-bot/src/binance_bot/strategies/grid.py` | P1-STRAT-1,2 | 2 fixes |
| `binance-bot/src/binance_bot/core/order_manager.py` | P1-STRAT-4,5 | 2 fixes |
| `binance-bot/src/binance_bot/core/position_manager.py` | P1-STRAT-7,8 | 2 fixes |
| `tests/unit/test_sprint26_bot_logic.py` | all | 28 tests |

---

## Validation Results (2026-03-13)

All 13 issues validated against source code. Line numbers and code snippets confirmed accurate.

| Issue | Lines | Code Match | Fix | Side Effects |
|-------|-------|-----------|-----|--------------|
| P1-BOT-1 | 462–465, 507–514 | ✅ | ✅ | Shared state now shows live price when PAUSED (was `None`) — beneficial |
| P1-BOT-2 | 454–456 | ✅ | ✅ | `can_trade()` returns `tuple[bool, str]` confirmed at `limits.py:219` |
| P1-BOT-4 | 694–699 | ✅ | ✅ | None |
| P1-BOT-5 | 576–577 | ✅ | ✅ | **VALIDATION NOTE**: EMA consumer check section was incorrect — fixed above |
| P1-BOT-6 | 639–648 | ✅ | ✅ | PnL uses avg entry price (approximate but far better than 0) |
| P1-BOT-7 | 568, 474 | ✅ | ✅ | Single caller at line 502 confirmed |
| P1-BOT-8 | 525–527, 1003–1007 | ✅ | ✅ | None |
| P1-STRAT-1 | 132–135, 147–199 | ✅ | ✅ | `_setup_short_levels` signature adds `offset=0` default — backward compatible |
| P1-STRAT-2 | 628–663 | ✅ | ✅ | `Signal` imported at grid.py:18, `_save_trade_to_db` at grid.py:753 — signatures match |
| P1-STRAT-4 | 187–188 | ✅ | ✅ | None |
| P1-STRAT-5 | 258–275 | ✅ | ✅ | `del` moves inside `try` — orders preserved on network error |
| P1-STRAT-7 | 37–90 | ✅ | ✅ | `PositionInfo` needs `short_amount`/`short_entry_price` fields added |
| P1-STRAT-8 | 113–118 | ✅ | ✅ | Depends on P1-STRAT-7 (new fields) |

**Status: VALIDATED — ready for implementation**
