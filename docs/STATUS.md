# Project Status

**Last updated:** 2026-03-15

## Current State

**Phase:** Paper Trading (Binance Testnet)
**Bot status:** Running, auto-managed (AI pause/resume)
**Dashboard:** http://10.48.14.85:8501

### Metrics
- Total trades: 89 (paper)
- Strategies: Grid, Momentum, MeanReversion, Breakout (auto-selected by regime)
- Indicators: 50+ (trend, momentum, volatility, volume, support/resistance, patterns)
- Tests: 473+
- Total commits: 120+
- Codebase: ~14,500 lines Python

### Infrastructure
- **Server:** ts1-rnd-llm01 (Docker)
- **Containers:** centric-void-01-app-service, centric-void-01-app-api, centric-void-01-app-dashboard
- **Exchange:** Binance Testnet (BTC/USDT)
- **AI Model:** MiniMax M2.5 via OpenRouter
- **Database:** SQLite (WAL mode)

### Completed Sprints (1-23)
1-14: Core bot, grid trading, monorepo structure
15: Market factors analysis
16: Vector DB for news sentiment
17: Testing infrastructure + CI/CD
18: Hyperparameter optimization (Optuna)
19: Advanced backtesting engine
20: Bi-directional grid (long + short)
21: TP/SL per grid level + trailing stop
22: Multi-strategy engine + regime detection
23: 50+ indicators + multi-timeframe

### Sprint 24 — P0 Runtime Crash Fixes (COMPLETED)
**Date:** 2026-03-12
**Branch:** `feature/sprint-24-p0-fixes`
**Issues fixed:** 26 P0 issues across 5 phases

| Phase | Focus | Issues |
|-------|-------|--------|
| 1 | Foundation (config, DB, state) | P0-CORE-1, P0-CORE-2, P0-CORE-3 |
| 2 | Indicators + factors (div/zero) | P0-CORE-4, P0-STRAT-1, P0-STRAT-2, P0-FACTORS-1 |
| 3 | Services (AI, alerts, risk, backtest, vector_db) | P0-AI-1, P0-AI-2, P0-ALERT-1, P0-ALERT-2, P0-RISK-1, P0-RISK-2, P0-BACK-1, P0-VDB-1, P0-VDB-2 |
| 4 | Bot & strategies | P0-BOT-1..4, P0-STRAT-3..6 |
| 5 | Jesse bot | P0-JESSE-1..3 |

Key changes:
- Settings: empty defaults for API keys + runtime validation
- 9 division-by-zero fixes across indicators (`.replace(0, np.nan)` + `fillna`)
- Lazy TradingAgent proxy (no import-time crash)
- DB session leak fix (try/except/finally)
- `float('inf')` → `9999.99` for JSON safety
- `asyncio.get_event_loop()` → `asyncio.get_running_loop()`
- Jesse candle column index 2 → 4 (high → close)
- 40+ new tests in `tests/unit/test_sprint24_p0.py`

### Sprint 25 — Jesse Bot Fixes (COMPLETED)
**Date:** 2026-03-12
**Branch:** `feature/sprint-25-jesse-fixes`
**Issues fixed:** 6 issues (4 P1, 2 P2)

| Phase | Issue | Severity | File | Fix |
|-------|-------|----------|------|-----|
| 1 | P1-JESSE-3 | P1 (CRITICAL) | `live_trader.py` | Only rebuild grid on direction change, not every iteration |
| 2 | P1-JESSE-4 | P1 | `live_trader.py` | Bounded `filled_order_ids` with deque(maxlen=500) |
| 3 | P1-JESSE-1 | P1 | `grid_logic.py` | `get_crossed_buy_level_price` now returns most recent fill |
| 4 | P1-JESSE-2 | P1 | `factors_mixin.py` | Fixed candle-to-dataframe column mapping for 5-col arrays |
| 5 | P2-JESSE-1 | P2 | `ai_mixin.py` | Parameterized hardcoded "BTCUSDT" symbol |
| 6 | P2-JESSE-2 | P2 | `ai_mixin.py` | Parameterized hardcoded total_balance=10000 |

Key changes:
- Grid state now persists across loop iterations (only rebuilds on trend change)
- `level_order_map` cleared on rebuild to prevent stale order matching
- `_last_filled_buy/sell` tracking in GridManager with serialization support
- `base_currency` derived from symbol instead of hardcoded "BTC"
- Symbol format conversion in callers: `"ETH-USDT"` → `"ETHUSDT"`
- 28 new tests in `tests/test_sprint25.py`

### Sprint 26 — Bot Logic & State Machine (COMPLETED)
**Date:** 2026-03-15
**Branch:** `feature/sprint-26-bot-logic`
**Issues fixed:** 13 (7 P1-BOT + 6 P1-STRAT)

| File | Issues | Changes |
|------|--------|---------|
| `bot.py` | P1-BOT-1,2,4,5,6,7,8 | PAUSED auto-resume fix, risk-gated dashboard resume, first AI review trigger, EMA 8/21 key match, actual PnL recording, ticker reuse, KeyboardInterrupt removal |
| `grid.py` | P1-STRAT-1,2 | Offset short levels in direction=both, _close_level trade recording |
| `order_manager.py` | P1-STRAT-4,5 | abs(amount) for short orders, order preservation on fetch failure |
| `position_manager.py` | P1-STRAT-7,8 | Short position tracking + unrealized PnL for shorts |

Key changes:
- PAUSED state now runs auto-resume logic (entry check + AI review)
- Dashboard resume blocked when risk limits breached
- PnL correctly calculated for sell/cover trades (risk limits now functional)
- Grid direction=both produces unique price levels (no duplicates)
- Short positions fully tracked in PositionManager with PnL
- 28 new tests in `tests/unit/test_sprint26_bot_logic.py`

### Current Sprint Plan (24-31)
Based on Audit V2 (118 issues found):
- **Sprint 24:** P0 runtime crash fixes ✅
- **Sprint 25:** Jesse bot fixes ✅
- **Sprint 26:** Bot logic & state machine ✅
- **Sprint 27:** Risk management fixes
- **Sprint 28:** Alerts, API & data consistency
- **Sprint 29:** Architecture & decoupling
- **Sprint 30:** Code quality & cleanup
- **Sprint 31:** Simplification + full regression

See `docs/SPRINT_PLAN.md` for details.

### Known Issues
See `docs/AUDIT_V2.md` for full list (118 items, P0-P3).

### Next Milestones
1. Complete Sprints 24-31 (fix all audit issues)
2. Achieve >80% test coverage
3. Live trading with small capital ($50-100)
