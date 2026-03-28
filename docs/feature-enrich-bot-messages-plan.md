# Feature Plan: Enrich Bot Messages

**Branch:** `feature/feature-enrich-bot-messages`
**Date:** 2026-03-27
**Status:** APPROVED

---

## Objective

Enrich all bot alert messages (trade, TP/SL, status, daily summary) with strategy context, position details, and fix pre-existing wiring bugs that prevent information from reaching Discord/email.

---

## MVP Items

### A — Fix AlertManager.send_trade_alert() signature mismatch

**Problem:** `DiscordAlert.send_trade_alert()` accepts `direction` and `net_exposure` params (added Sprint 20), but `AlertManager.send_trade_alert()` does NOT pass them through. All trade alerts sent via AlertManager lose direction/exposure info.

**Fix:**
- Add `direction: Optional[str] = None` and `net_exposure: Optional[float] = None` to `AlertManager.send_trade_alert()`.
- Pass both through to `self.discord.send_trade_alert()`.
- Update bot.py callers to pass direction when available.

### B — Wire TP/SL alert dispatch in bot.py

**Problem:** `GridStrategy.check_tp_sl()` produces events stored in `self.tp_sl_alerts`, but bot.py never reads or dispatches them. `AlertManager.send_tp_sl_alert()` exists but is never called.

**Fix:**
- After `_process_signals()` in `_execute_trading()`, drain `strategy.tp_sl_alerts` and dispatch each via `alert_manager.send_tp_sl_alert()`.
- Also record PnL from TP/SL events to risk_limits and rules_engine.

### C — GridLevel.fill_time == 0 guard

**Problem:** `check_tp_sl()` in grid.py checks `level.fill_price == 0` as guard but not `fill_time == 0`. A level with `fill_price > 0` but `fill_time == 0` is invalid state.

**Fix:** Add `or level.fill_time == 0` to the guard in `check_tp_sl()`.

### D — Enrich trade alerts with strategy/regime context

**Problem:** Trade alerts show price/amount/direction but not which strategy generated the signal or current market regime. This context is available in bot.py but not passed to alerts.

**Fix:**
- Add `strategy_name: Optional[str] = None` and `regime: Optional[str] = None` to DiscordAlert and AlertManager `send_trade_alert()`.
- Add fields to Discord embed.
- Pass from bot.py where available.

---

## Files to Change

| File | Changes |
|------|---------|
| `shared/alerts/discord.py` | Add strategy_name/regime to send_trade_alert |
| `shared/alerts/manager.py` | Add direction/net_exposure/strategy_name/regime to send_trade_alert |
| `binance-bot/src/binance_bot/bot.py` | Wire TP/SL dispatch, pass enriched params to trade alerts |
| `binance-bot/src/binance_bot/strategies/grid.py` | fill_time guard in check_tp_sl |
| `tests/unit/test_alerts.py` | New tests for enriched fields |
| `tests/unit/test_bot_enrich.py` | Tests for TP/SL dispatch wiring |

---

## Tests

1. `test_trade_alert_direction_passthrough` — direction reaches Discord embed
2. `test_trade_alert_strategy_regime_fields` — strategy/regime in Discord embed
3. `test_manager_trade_alert_passes_direction` — AlertManager forwards direction
4. `test_manager_trade_alert_passes_strategy_regime` — AlertManager forwards strategy/regime
5. `test_tp_sl_dispatch_from_bot` — TP/SL events dispatched to alert_manager
6. `test_fill_time_zero_guard` — check_tp_sl skips fill_time==0 levels
7. `test_trade_alert_backward_compat` — existing calls without new params still work
