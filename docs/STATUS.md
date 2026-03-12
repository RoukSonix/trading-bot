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

### Current Sprint Plan (24-31)
Based on Audit V2 (118 issues found):
- **Sprint 24:** P0 runtime crash fixes
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
