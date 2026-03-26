# Feature Plan: Daily Summary Balance/PnL + Trade Amount in Alerts

**Branch:** `feature/feature-daily-summary-trade-amount`
**Date:** 2026-03-26
**Status:** APPROVED
**Validated:** 2026-03-26

---

## Objective

1. **Daily summary** must show **current balance** and **today's trading result (today PnL)**.
2. **Each trade alert** must include **trade amount (cost)** = `price × amount` in USDT.

---

## Current State Analysis

### Daily Summary (`_get_daily_summary_data` → `send_daily_summary`)

| What exists | What's missing |
|---|---|
| `start_balance` — always `settings.paper_initial_balance` (initial, NOT today's start) | True **today's starting balance** (balance at 00:00 UTC) |
| `end_balance` — current portfolio value | Labelled as "current balance" explicitly |
| `total_pnl` — calculated as `end_balance - start_balance` (lifetime PnL, NOT today) | **Today PnL** — profit/loss for today only |

**Root problem:** `start_balance` uses the paper initial balance from config, so PnL reflects lifetime performance, not today's result.

### Trade Alert (`send_trade_alert`)

| What exists | What's missing |
|---|---|
| `price` — trade price | — |
| `amount` — asset quantity (e.g. 0.001 BTC) | **Trade cost/value** in USDT (`price × amount`) |

**Root problem:** Discord embed shows `Amount: 0.001000` with no USDT equivalent. User must mentally multiply.

---

## Files to Change

### 1. `shared/alerts/discord.py` — Discord formatter

**`send_trade_alert()` (line ~156–161):**
- Add new embed field **"Value"** showing `price × amount` in USDT.
- Insert after the existing "Amount" field.

```python
# After "Amount" field (line 160):
{"name": "Value", "value": f"💰 ${price * amount:,.2f}", "inline": True},
```

**`send_daily_summary()` (line ~284–349):**
- Add new parameter `current_balance: Optional[float] = None`.
- Add new parameter `today_pnl: Optional[float] = None`.
- Add embed field **"Current Balance"** — actual portfolio value right now.
- Add embed field **"Today PnL"** — today-only profit/loss with percentage.
- Keep existing `start_balance`/`end_balance`/`total_pnl` for backward compat but relabel:
  - "Start Balance" → "Initial Balance" (lifetime reference).
  - "Daily PnL" → "Lifetime PnL" (to avoid confusion with today PnL).

New fields to add (before the Win Rate section):
```python
if current_balance is not None:
    fields.append({"name": "💰 Current Balance", "value": f"${current_balance:,.2f}", "inline": True})

if today_pnl is not None:
    today_emoji = "📈" if today_pnl >= 0 else "📉"
    today_pnl_text = f"{today_emoji} ${today_pnl:+,.2f}"
    # VALIDATION NOTE: Use starting_balance (= current_balance - today_pnl) for percentage.
    # Original guard `current_balance > abs(today_pnl)` was too restrictive —
    # it hid percentage for losses exceeding half the starting balance.
    starting = current_balance - today_pnl if current_balance is not None else 0
    if starting > 0:
        today_pct = (today_pnl / starting) * 100
        today_pnl_text += f" ({today_pct:+.2f}%)"
    fields.append({"name": "Today PnL", "value": today_pnl_text, "inline": True})
```

### 2. `shared/alerts/manager.py` — Alert manager routing

**`send_trade_alert()` (line ~162–214):**
- No parameter changes needed — `price` and `amount` are already passed through.
- The value calculation (`price × amount`) is done in the Discord formatter.

**`send_daily_summary()` (line ~309–362):**
- Add `current_balance: Optional[float] = None` parameter.
- Add `today_pnl: Optional[float] = None` parameter.
- Pass both through to `self.discord.send_daily_summary()`.
- Pass both through to `self.email.send_daily_report()` (email body text).

> **VALIDATION NOTE:** `email.send_daily_report()` (`shared/alerts/email.py:104`) does NOT currently
> accept `current_balance` or `today_pnl` params. Passing them will raise `TypeError`.
> **Fix:** Add `current_balance: Optional[float] = None` and `today_pnl: Optional[float] = None`
> to `email.send_daily_report()` signature. The HTML template can optionally render them, or
> simply accept and ignore them for now. This must be done in the same PR — not deferred.

### 3. `binance-bot/src/binance_bot/bot.py` — Data builder

**`_get_daily_summary_data()` (line ~227–257):**
- Add `current_balance` = current portfolio total value (= `end_balance`, explicit key).
- Calculate **today PnL** safely:

```python
# Safe today PnL calculation:
# Use DailyStats from risk_limits if available (tracks today's starting balance).
# Fallback: query TradeLog for today's trades and sum their PnL.
# Last resort: use end_balance - start_balance (lifetime, not today).

today_pnl = 0.0
if hasattr(self, 'risk_limits') and self.risk_limits and hasattr(self.risk_limits, 'daily_stats'):
    ds = self.risk_limits.daily_stats
    if ds is not None:
        today_pnl = ds.current_balance - ds.starting_balance
else:
    today_pnl = end_balance - start_balance  # fallback to lifetime
```

- Add to returned dict:
  - `"current_balance": end_balance`
  - `"today_pnl": today_pnl`

---

## Safe Calculation Method for Today's Result

**Primary source:** `RiskLimits.daily_stats` (`shared/risk/limits.py:DailyStats`)
- `DailyStats.starting_balance` — set at midnight UTC reset, represents balance at day start.
- `DailyStats.current_balance` — updated on every `update_balance()` call.
- **Today PnL** = `current_balance - starting_balance`.
- This is the safest source because `RiskLimits.update_balance()` already resets daily stats at midnight UTC.

**Fallback:** If `risk_limits` is not available (e.g., paper trading without risk module):
- Use `end_balance - settings.paper_initial_balance` (lifetime PnL, clearly labelled).

**Today PnL percentage** = `today_pnl / starting_balance × 100` (avoid division by zero).

---

## Embed Layout (After Changes)

### Daily Summary Embed
```
📊 Daily Summary - 2026-03-26
┌─────────────────────────────────────────┐
│ Symbol:          BTC/USDT               │
│ Total Trades:    12                     │
│ Win Rate:        66.7%                  │
│ 💰 Current Balance: $10,350.00         │
│ Today PnL:       📈 $+150.00 (+1.47%)  │
│ Initial Balance: $10,000.00            │
│ End Balance:     $10,350.00            │
│ Lifetime PnL:    $+350.00 (+3.50%)     │
│ Winning:         🟢 8                   │
│ Losing:          🔴 4                   │
│ Max Drawdown:    2.10%                  │
│ Best Trade:      $+45.00               │
│ Worst Trade:     $-12.00               │
└─────────────────────────────────────────┘
```

### Trade Alert Embed
```
🟢 LONG BUY Trade Executed
┌─────────────────────────────────────────┐
│ Symbol:    BTC/USDT                     │
│ Side:      🟢 LONG BUY                 │
│ Price:     $67,500.00                   │
│ Amount:    0.001000                     │
│ Value:     💰 $67.50                    │
│ Direction: 📈 LONG                      │
│ Order ID:  abc123                       │
└─────────────────────────────────────────┘
```

---

## Tests to Add/Update

### File: `tests/unit/test_alerts.py`

1. **`test_trade_alert_value_field`** — Verify `send_trade_alert` embed includes "Value" field with `price × amount`.
2. **`test_daily_summary_current_balance_field`** — Verify `send_daily_summary` embed includes "Current Balance" when provided.
3. **`test_daily_summary_today_pnl_field`** — Verify `send_daily_summary` embed includes "Today PnL" when provided.
4. **`test_daily_summary_today_pnl_percentage`** — Verify percentage calculation is correct and handles zero balance.
5. **`test_daily_summary_backward_compat`** — Verify `send_daily_summary` works without new optional params (no breaking change).
6. **`test_trade_alert_value_zero_amount`** — Edge case: amount=0 should show $0.00 value.

### File: `tests/unit/test_bot_daily_summary.py` (new)

7. **`test_get_daily_summary_data_includes_current_balance`** — Verify `_get_daily_summary_data` returns `current_balance`.
8. **`test_get_daily_summary_data_today_pnl_from_risk_limits`** — Verify today PnL uses `DailyStats` when available.
9. **`test_get_daily_summary_data_today_pnl_fallback`** — Verify fallback when `risk_limits` not available.

---

## Rollout Notes

- **Backward compatible:** New parameters are `Optional` with `None` defaults. Existing callers (email, tests) continue to work.
- **No DB schema changes** — all data sourced from existing in-memory structures.
- **No config changes** — no new settings required.
- **Risk:** Minimal. Only adds new fields to Discord embeds. Existing fields unchanged (except label rename).
- **Label rename** ("Daily PnL" → "Lifetime PnL", "Start Balance" → "Initial Balance") may affect users who grep Discord channel history — document in changelog.
- **Email formatter** (`shared/alerts/email.py:send_daily_report`) MUST also receive `current_balance` and `today_pnl` as optional params in this PR to avoid `TypeError` when `manager.py` passes them through. HTML rendering of these values is optional/deferred.

---

## Validation Report (Step 2)

**Validated by:** Claude ACP (Step 2 agent)
**Date:** 2026-03-26

### File Targets — CONFIRMED

| File | Method | Plan lines | Actual lines | Status |
|---|---|---|---|---|
| `shared/alerts/discord.py` | `send_trade_alert` fields | ~156–161 | 156–161 | ✅ |
| `shared/alerts/discord.py` | `send_daily_summary` | ~284–349 | 284–349 | ✅ |
| `shared/alerts/manager.py` | `send_trade_alert` | ~162–214 | 162–214 | ✅ |
| `shared/alerts/manager.py` | `send_daily_summary` | ~309–362 | 309–362 | ✅ |
| `binance-bot/src/binance_bot/bot.py` | `_get_daily_summary_data` | ~227–257 | 227–257 | ✅ |
| `shared/risk/limits.py` | `DailyStats` | — | lines 20–53 | ✅ |
| `shared/alerts/email.py` | `send_daily_report` | — | lines 104–236 | ✅ (needs param update) |
| `tests/unit/test_alerts.py` | existing tests | — | exists, 245 lines | ✅ |

### Today PnL Safety — CONFIRMED

- `RiskLimits._reset_daily_stats()` (line 95) uses `current_balance` from previous day as `starting_balance` for the new day.
- `update_balance()` (line 117) triggers daily reset when `date.today()` changes.
- `DailyStats.starting_balance` genuinely represents "balance at start of today".
- `today_pnl = current_balance - starting_balance` is safe and correct.
- `self.risk_limits` is always initialized in `TradingBot.__init__` (line 119), so `hasattr` guard is defensive but harmless.

### Issues Found and Fixed

**Issue 1 — Today PnL percentage guard (FIXED in plan)**
Original code: `if current_balance and current_balance > abs(today_pnl)` — too restrictive, hid percentage for losses > 50% of starting balance. Changed to: `starting = current_balance - today_pnl; if starting > 0`.

**Issue 2 — Email `TypeError` (FIXED in plan)**
Plan originally said to pass `current_balance`/`today_pnl` to `email.send_daily_report()` which does NOT accept those params. Added validation note: must add optional params to `email.send_daily_report()` in same PR.

### Breaking Changes — NONE

- All new parameters are `Optional[float] = None`. Existing callers unaffected.
- Label renames ("Start Balance" → "Initial Balance", "Daily PnL" → "Lifetime PnL") are cosmetic, no functional impact.

### Test Coverage — SUFFICIENT

9 planned tests cover: new fields, percentage calculation, zero/edge cases, backward compat, bot data builder with and without risk_limits. No missing critical test cases identified.

### Verdict: **APPROVED** — ready for Step 3 implementation.
