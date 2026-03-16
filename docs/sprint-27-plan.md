# Sprint 27: Risk Management Fixes — Implementation Plan

**Date:** 2026-03-16
**Branch:** `sprint-27-risk`
**Worktree:** `~/projects/CentricVoid/trading-bots-sprint-27-risk/`
**Issues:** 10 (9x P1-RISK + 1x P1-BOT)
**Files to modify:** 5 source files, 1 new test file

---

## Issue 1: P1-RISK-2 — `risk_amount` double-applies percentage

**File:** `shared/risk/position_sizer.py:127`
**Bug:** In `_fixed_percent()`, `amount_usd` is already `portfolio_value * risk_per_trade` (line 115). Then line 127 sets `risk_amount=amount_usd * self.risk_per_trade`, applying the percentage a second time. Result: risk_amount = portfolio * 0.02 * 0.02 = 0.04% instead of 2%.

```python
# Line 127 (current)
risk_amount=amount_usd * self.risk_per_trade,

# Fix
risk_amount=amount_usd,
```

**Test:**
- `test_risk_amount_not_double_applied`: portfolio=$10,000, risk_per_trade=0.02 → risk_amount should be $200, not $4.
- `test_risk_amount_fixed_percent_matches_value`: risk_amount == value when under max_position_pct cap.

---

## Issue 2: P1-RISK-3 — Sortino ratio returns 0.0 for all-winning strategy

**File:** `shared/risk/metrics.py:208-209`
**Bug:** When all trades are profitable, `negative_returns` is empty → returns 0.0. A perfect strategy appears to have zero risk-adjusted return.

```python
# Lines 208-209 (current)
if not negative_returns:
    return 0.0

# Fix: return a large positive sentinel (no downside risk = excellent)
if not negative_returns:
    avg_return = statistics.mean(returns)
    if avg_return > 0:
        return 99.99  # Capped sentinel — no downside risk
    return 0.0
```

**Test:**
- `test_sortino_all_winning`: all positive pnl_pct → Sortino > 0 (sentinel value).
- `test_sortino_all_losing`: all negative → normal negative ratio.
- `test_sortino_mixed`: mixed trades → standard calculation.
- `test_sortino_insufficient_trades`: < 2 trades → 0.0.

---

## Issue 3: P1-RISK-4 — Profit factor returns 0.0 for all-winning strategy

**File:** `shared/risk/metrics.py:127-128`
**Bug:** When `gross_loss == 0` (no losing trades), profit_factor returns 0.0. A strategy with only wins appears to have zero profitability.

```python
# Lines 127-128 (current)
if gross_loss == 0:
    return 0.0

# Fix: return sentinel when there are actual profits
if gross_loss == 0:
    return 99.99 if gross_profit > 0 else 0.0
```

**Test:**
- `test_profit_factor_all_winning`: gross_profit > 0, no losses → large positive value.
- `test_profit_factor_all_losing`: no wins → 0.0.
- `test_profit_factor_mixed`: normal ratio.
- `test_profit_factor_no_trades`: empty → 0.0.

---

## Issue 4: P1-RISK-5 — Max drawdown auto-resets daily

**File:** `shared/risk/limits.py:120-124`
**Bug:** On new day detection, `trading_halted` is unconditionally reset to `False`. If the bot hit max drawdown (a portfolio-level limit) yesterday, it automatically resumes today — defeating the protection.

```python
# Lines 120-124 (current)
if self.daily_stats.date != date.today():
    self._reset_daily_stats()
    self.consecutive_losses = 0  # Reset streak on new day
    self.trading_halted = False  # ← WRONG: resets portfolio-level halt
    self.halt_reason = ""

# Fix: only reset daily-specific limits, preserve portfolio-level halts
if self.daily_stats.date != date.today():
    self._reset_daily_stats()
    self.consecutive_losses = 0

    # Only auto-resume if halt was daily-scoped (not max drawdown)
    if self.trading_halted and "drawdown" not in self.halt_reason.lower():
        self.trading_halted = False
        self.halt_reason = ""
```

**Test:**
- `test_daily_loss_resets_next_day`: daily loss halt → resumes next day.
- `test_max_drawdown_persists_next_day`: max drawdown halt → stays halted next day.
- `test_consecutive_losses_resets_next_day`: losing streak → resets on new day.
- `test_max_trades_resets_next_day`: trade count limit → resets on new day.

---

## Issue 5: P1-RISK-6 — Drawdown check uses daily HWM, not overall HWM

**File:** `shared/risk/limits.py:184`
**Bug:** `check_limits()` uses `self.daily_stats.current_drawdown` (line 184), which computes drawdown from the daily HWM (`DailyStats.high_water_mark`, line 46-50). A 10% drawdown spread across multiple days is never detected.

```python
# Line 184 (current)
current_dd = self.daily_stats.current_drawdown

# Fix: compute drawdown from overall HWM
current_dd = (
    (self.high_water_mark - self.daily_stats.current_balance) / self.high_water_mark
    if self.high_water_mark > 0 else 0.0
)
```

**Test:**
- `test_drawdown_detected_across_days`: balance drops 3% day 1, 4% day 2, 4% day 3 → total 11% > 10% limit → breached.
- `test_drawdown_from_overall_hwm`: overall HWM = $11,000, current = $9,500 → 13.6% drawdown detected.

---

## Issue 6: P1-RISK-7 — Win/loss trade pairing logic broken

**File:** `shared/api/routes/trades.py:135-136`
**Bug:** Win/loss classification compares each sell against ALL buys with `any()`. If ANY previous buy was cheaper than the sell, the sell is marked as "winning" — which is almost always true with multiple buys at different prices.

```python
# Lines 135-136 (current)
winning = [s for s in sells if any(float(s.price) > float(b.price) for b in buys)]
losing = [s for s in sells if all(float(s.price) <= float(b.price) for b in buys)]

# Fix: FIFO pairing — match sells to buys in chronological order
winning = []
losing = []
buy_queue = list(buys)  # Copy for FIFO consumption
for sell in sells:
    if buy_queue:
        paired_buy = buy_queue.pop(0)
        if float(sell.price) > float(paired_buy.price):
            winning.append(sell)
        else:
            losing.append(sell)
    else:
        losing.append(sell)  # No matching buy → loss
```

**Test:**
- `test_pnl_fifo_pairing`: buy@$100, buy@$200, sell@$150 → FIFO: first sell paired with first buy ($100) → win.
- `test_pnl_all_sells_losing`: all sells below all buys → all losing.
- `test_pnl_no_buys`: sells with no buys → all losing.
- `test_pnl_more_sells_than_buys`: excess sells treated as losses.

---

## Issue 7: P1-RISK-8 — Symbol filter ignored for TradeLog query

**File:** `shared/api/routes/trades.py:105`
**Bug:** `get_pnl_summary()` queries `session.query(TradeLog).all()` without applying the `symbol` filter parameter. The `symbol` query param is accepted but ignored when TradeLog records exist.

```python
# Line 105 (current)
logs = session.query(TradeLog).all()

# Fix: apply symbol filter
query = session.query(TradeLog)
if symbol:
    query = query.filter(TradeLog.symbol == symbol)
logs = query.all()
```

Also fix in `get_pnl_history()` at line 174:
```python
# Line 174 (current)
logs = session.query(TradeLog).order_by(TradeLog.timestamp.asc()).all()

# Fix:
query = session.query(TradeLog)
if symbol:
    query = query.filter(TradeLog.symbol == symbol)
logs = query.order_by(TradeLog.timestamp.asc()).all()
```

**Test:**
- `test_pnl_summary_filters_by_symbol`: insert logs for BTC and ETH → query with symbol="BTC" → only BTC results.
- `test_pnl_summary_no_filter_returns_all`: query without symbol → all records.
- `test_pnl_history_filters_by_symbol`: same filter test for `/history` endpoint.

---

## Issue 8: P1-RISK-9 — Sharpe/Sortino annualization formula incorrect

**File:** `shared/risk/metrics.py:188-192` (Sharpe) and `218-220` (Sortino)
**Bug:** Annualization uses `trades_per_year = len(trades) * (365 / period_days)`. This inflates the ratio proportionally to trade count — 100 trades in 30 days → trades_per_year = 1217, making annualized_return absurdly large.

The correct approach: scale by `sqrt(N)` where N = trading periods per year.

```python
# Sharpe fix (lines 188-192):
# Estimate trading frequency from the period
trades_per_day = len(self.trades) / period_days if period_days > 0 else 1
trading_periods_per_year = 252  # Standard trading days
annualized_return = avg_return * trading_periods_per_year * trades_per_day
annualized_std = std_return * ((trading_periods_per_year * trades_per_day) ** 0.5)

# Sortino fix (lines 218-220): same pattern
annualized_return = avg_return * trading_periods_per_year * trades_per_day
annualized_downside = downside_std * ((trading_periods_per_year * trades_per_day) ** 0.5)
```

**Test:**
- `test_sharpe_annualization_reasonable`: 100 trades over 365 days → Sharpe in [-5, 5] range, not ±50.
- `test_sortino_annualization_reasonable`: same bounds check.
- `test_sharpe_identical_returns`: all same return → std=0 → 0.0.
- `test_sharpe_negative_returns`: all losses → negative Sharpe.

---

## Issue 9: P1-RISK-10 — StopLossManager limited to one position per symbol

**File:** `shared/risk/stop_loss.py:169`
**Bug:** `self.positions[symbol] = position` uses symbol as dict key. If the bot opens a second position for the same symbol (e.g., grid adds at different levels), the first position's stop-loss data is silently overwritten.

```python
# Line 102 (current)
self.positions: Dict[str, Position] = {}

# Fix: use a composite key (symbol + position_id)
self.positions: Dict[str, Position] = {}
self._position_counter: int = 0

# Line 169 (current)
self.positions[symbol] = position

# Fix: use auto-incrementing position ID
self._position_counter += 1
position_id = f"{symbol}_{self._position_counter}"
self.positions[position_id] = position
```

Update `check_position()` to iterate all positions for a symbol:
```python
def check_positions_for_symbol(self, symbol: str, current_price: float) -> List[Dict]:
    results = []
    for pid, pos in list(self.positions.items()):
        if pos.symbol == symbol:
            result = self._check_single_position(pid, pos, current_price)
            if result["action"]:
                results.append(result)
    return results
```

Keep `check_position()` as a backward-compatible wrapper.

**Test:**
- `test_multiple_positions_same_symbol`: add 3 BTC positions → all 3 tracked.
- `test_stop_loss_triggers_correct_position`: different entry prices → only the correct one triggers.
- `test_remove_position_by_id`: remove one, others remain.

---

## Issue 10: P1-BOT-3 — `strategy_engine` data computed but never persisted

**File:** `binance-bot/src/binance_bot/bot.py:911-917`
**Bug:** `write_state(state)` is called at line 911. Then lines 914-916 compute `engine_status` and assign it to `state_dict["strategy_engine"]`, but this is AFTER `write_state()` already serialized and wrote the state. The strategy engine data is computed and discarded every cycle.

```python
# Lines 911-917 (current)
write_state(state)

# Write strategy engine status alongside shared state
engine_status = self.strategy_engine.get_status()
state_dict = state.__dict__ if hasattr(state, '__dict__') else {}
state_dict["strategy_engine"] = engine_status  # dead code — already written

# Fix option A: Add strategy_engine field to BotState and set before write
# In shared/core/state.py — add field to BotState:
#   strategy_engine: dict = field(default_factory=dict)
#
# In bot.py — set before write_state():
state = SharedBotState(
    ...existing fields...,
)
# Add engine status before writing
engine_status = self.strategy_engine.get_status()
state.strategy_engine = engine_status  # ← BEFORE write_state
write_state(state)
```

Requires adding `strategy_engine: dict = field(default_factory=dict)` to `BotState` in `shared/core/state.py:42`.

**Test:**
- `test_strategy_engine_data_persisted`: call `_write_shared_state()`, read back state file → `strategy_engine` key present with expected fields.
- `test_state_roundtrip_with_engine`: `BotState.to_dict()` → `BotState.from_dict()` preserves strategy_engine.

---

## Implementation Order

| Step | Issue | Risk | Dependencies |
|------|-------|------|-------------|
| 1 | P1-RISK-2 | Low | None |
| 2 | P1-RISK-4 | Low | None |
| 3 | P1-RISK-3 | Low | None |
| 4 | P1-RISK-9 | Medium | None |
| 5 | P1-RISK-5 | Medium | None |
| 6 | P1-RISK-6 | Medium | P1-RISK-5 (same file) |
| 7 | P1-RISK-8 | Low | None |
| 8 | P1-RISK-7 | Medium | P1-RISK-8 (same file) |
| 9 | P1-RISK-10 | High | Callers in bot.py |
| 10 | P1-BOT-3 | Medium | state.py change |

---

## Files Modified

| File | Issues | Changes |
|------|--------|---------|
| `shared/risk/position_sizer.py` | P1-RISK-2 | 1 line fix |
| `shared/risk/metrics.py` | P1-RISK-3, P1-RISK-4, P1-RISK-9 | ~15 lines |
| `shared/risk/limits.py` | P1-RISK-5, P1-RISK-6 | ~10 lines |
| `shared/api/routes/trades.py` | P1-RISK-7, P1-RISK-8 | ~15 lines |
| `shared/risk/stop_loss.py` | P1-RISK-10 | ~30 lines (new methods) |
| `shared/core/state.py` | P1-BOT-3 | 1 field added |
| `binance-bot/src/binance_bot/bot.py` | P1-BOT-3, P1-RISK-10 (caller) | ~10 lines |

## Test File

`tests/unit/test_sprint27_risk.py` — ~250 lines covering all 10 issues.

Test classes:
- `TestP1Risk2PositionSizerDoublePercent`
- `TestP1Risk3SortinoAllWinning`
- `TestP1Risk4ProfitFactorAllWinning`
- `TestP1Risk5DrawdownAutoReset`
- `TestP1Risk6DrawdownDailyHWM`
- `TestP1Risk7WinLossPairing`
- `TestP1Risk8SymbolFilter`
- `TestP1Risk9Annualization`
- `TestP1Risk10MultiPosition`
- `TestP1Bot3StrategyEnginePersist`
