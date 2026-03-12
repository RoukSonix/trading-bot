# Project Status

**Last updated:** 2026-03-12

## Current State

**Phase:** Paper Trading (Binance Testnet)
**Bot status:** Running, auto-managed (AI pause/resume)
**Dashboard:** http://10.48.14.85:8501

### Metrics
- Total trades: 89 (paper)
- Strategies: Grid, Momentum, MeanReversion, Breakout (auto-selected by regime)
- Indicators: 50+ (trend, momentum, volatility, volume, support/resistance, patterns)
- Tests: 417+
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

### Current Sprint Plan (24-31)
Based on Audit V2 (118 issues found):
- **Sprint 24:** P0 runtime crash fixes ✅
- **Sprint 25:** Jesse bot fixes
- **Sprint 26:** Bot logic & state machine
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
