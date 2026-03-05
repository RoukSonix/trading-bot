# Binance Grid Trading Bot

AI-assisted grid trading bot for Binance cryptocurrency markets.

Part of the [trading-bots monorepo](../README.md).

## Features

- Grid Trading strategy with configurable levels and spacing
- AI-enhanced grid optimization (LangChain + OpenRouter)
- Paper trading simulation
- Risk management (position sizing, stop-loss, daily limits)
- Multi-channel alerts (Telegram, Discord, Email)
- Web Dashboard (Streamlit + FastAPI)
- Prometheus monitoring + Grafana dashboards
- Docker multi-stage builds

## Setup

```bash
# From monorepo root
cd binance-bot

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dashboard,dev]"

# Configure
cp .env.example .env
# Edit .env with your Binance API keys

# Run paper trading
PYTHONPATH=../:.  python scripts/run_paper_trading.py

# Run dashboard
PYTHONPATH=../:.  python scripts/run_dashboard.py
```

## Docker

```bash
# Start API + Dashboard
docker compose up -d

# Start with trading bot
docker compose --profile bot up -d

# Development mode
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

## Project Structure

```
binance-bot/
├── src/binance_bot/
│   ├── bot.py              # Main bot orchestrator (24/7 async)
│   ├── main.py             # CLI entry point
│   ├── core/
│   │   ├── exchange.py     # CCXT Binance wrapper
│   │   ├── order_manager.py
│   │   ├── position_manager.py
│   │   ├── data_collector.py
│   │   └── emergency.py    # Emergency stop handler
│   └── strategies/
│       ├── base.py         # BaseStrategy abstract class
│       ├── grid.py         # Grid trading strategy
│       └── ai_grid.py      # AI-enhanced grid strategy
├── scripts/                # Run scripts
├── monitoring/             # Prometheus + Grafana configs
├── Dockerfile
├── docker-compose*.yml
└── .env.example
```

Uses shared modules from `../shared/` (ai, alerts, config, risk, api, dashboard, etc.)
