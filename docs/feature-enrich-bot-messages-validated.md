# Validated Plan: Enrich Bot Messages

**Branch:** `feature/feature-enrich-bot-messages`
**Date:** 2026-03-27
**Validated by:** Claude ACP (Step 2 agent)

---

## Validation Summary

All 4 MVP items (A, B, C, D) validated against current codebase. Implementation order: bottom-up (grid.py → discord.py → manager.py → bot.py → tests).

---

## File Targets — CONFIRMED

| File | Method | Status |
|------|--------|--------|
| `shared/alerts/discord.py:103` | `send_trade_alert()` — already has direction/net_exposure | OK, add strategy_name/regime |
| `shared/alerts/manager.py:162` | `send_trade_alert()` — MISSING direction/net_exposure | BUG CONFIRMED |
| `binance-bot/src/binance_bot/strategies/grid.py:516` | `check_tp_sl()` — no fill_time guard | BUG CONFIRMED |
| `binance-bot/src/binance_bot/strategies/grid.py:129` | `tp_sl_alerts` — accumulated, never consumed | BUG CONFIRMED |
| `binance-bot/src/binance_bot/bot.py:562-570` | `_execute_trading()` — no TP/SL dispatch | BUG CONFIRMED |
| `binance-bot/src/binance_bot/bot.py:646,697` | `send_trade_alert()` calls — missing direction | BUG CONFIRMED |

## Pre-existing Bugs

### Bug 1: AlertManager.send_trade_alert() drops direction/net_exposure
- `discord.py:103-114` accepts direction, net_exposure
- `manager.py:162-171` only forwards: symbol, side, price, amount, pnl, pnl_pct, order_id
- **Fix:** Add direction, net_exposure to manager signature and forward to discord

### Bug 2: TP/SL alerts dead code
- `grid.py:373-375` stores events in `self.tp_sl_alerts`
- bot.py `_execute_trading()` calls `_process_signals()` which calls `strategy.calculate_signals()` which calls `check_tp_sl()` internally
- But bot.py never reads `strategy.tp_sl_alerts` or calls `alert_manager.send_tp_sl_alert()`
- **Fix:** After `_process_signals()`, drain `strategy.tp_sl_alerts` and dispatch

### Bug 3: GridLevel.fill_time == 0 guard
- `grid.py:530` checks `not level.filled or level.fill_price == 0`
- Should also check `level.fill_time == 0` as invalid state indicator
- **Fix:** Add `or level.fill_time == 0` to guard condition

### Bug 4: Email send_daily_report() params
- Already fixed in previous PR #25 — `email.py:104-117` already accepts current_balance/today_pnl
- **No action needed**

## Implementation Order (bottom-up)

1. `grid.py` — fill_time guard (Bug 3)
2. `discord.py` — add strategy_name/regime to send_trade_alert (MVP D)
3. `manager.py` — add direction/net_exposure/strategy_name/regime to send_trade_alert (Bug 1 + MVP D)
4. `bot.py` — wire TP/SL dispatch (Bug 2), pass enriched params (MVP A+D)
5. Tests — all new test cases
6. STATUS.md — update

## Backward Compatibility — CONFIRMED

All new parameters are Optional with None defaults. Existing callers unaffected.

## Verdict: **APPROVED** — ready for Step 3 implementation.
