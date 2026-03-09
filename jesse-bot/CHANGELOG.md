# Changelog — jesse-bot

All notable changes to the Jesse trading bot.

## Sprint M7 — Cleanup + Optimization (2026-03-09)

- Updated AGENTS.md with all sprint statuses marked Done
- Created CHANGELOG.md covering full sprint history
- Documented optimization results (ETH-USDT 1h Trial 2861)
- Optimized strategy hyperparameters for live deployment

## Sprint M6 — Live Trading Setup (2026-03-08)

- Configured testnet-only live trading via Jesse dashboard
- Added `live_config.py` with exchange credentials and risk settings
- Created `state_provider.py` for live state management
- Set up `scripts/` for deployment automation
- Corrected position size calculation in `test_within_limit`

## Sprint M5 — Alerts + Dashboard Adaptation (2026-03-08)

- Integrated Discord webhook alerts for trade notifications
- Adapted Streamlit dashboard components for Jesse data model
- Added real-time PnL tracking and grid visualization

## Sprint M4 — Sentiment + Factors Integration (2026-03-08)

- Integrated news sentiment analysis (CryptoCompare/CoinGecko)
- Added multi-factor scoring (momentum, volatility, RSI, volume)
- Factor signals feed into grid placement and sizing decisions

## Sprint M3 — AI Integration (2026-03-08)

- Added LLM agent as strategy mixin (OpenRouter/Claude)
- AI-driven market analysis for grid parameter adjustment
- Periodic AI review cycle (continue/pause/adjust/stop)
- Removed unsupported bool hyperparameters from Jesse optimizer

## Sprint M2 — Grid Logic Refinement (2026-03-08)

- Implemented bidirectional grid trading (long + short)
- Added take-profit and stop-loss with ATR-based multipliers
- Trailing stop activation and distance parameters
- Multi-timeframe trend detection (fast/slow SMA)
- 28 unit tests for grid logic (all passing)

## Sprint M1 — Jesse Foundation (2026-03-07)

- Initial Jesse framework setup (Jesse 1.13.7)
- Docker environment: jesse + postgres + redis
- Basic AIGridStrategy as Jesse Strategy subclass
- Pure Python grid logic in `grid_logic.py` (testable without Redis)
- First backtest infrastructure and routes configuration
