# Trading Bot

AI-assisted automated trading bot for cryptocurrency markets.

## Features

- Grid Trading strategy
- AI-powered decision making (LangChain + OpenRouter)
- Freqtrade core for order execution
- Binance exchange support
- Risk management
- Telegram notifications
- Web Dashboard (FastAPI + Streamlit)

## Setup

### Local Development

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .

# Copy config
cp .env.example .env
# Edit .env with your API keys

# Run bot
python -m trading_bot.main

# Run dashboard (API + Streamlit)
python scripts/run_dashboard.py
```

## Docker

### Quick Start

```bash
# Start API + Dashboard
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### Services

| Service   | Port | Description               |
|-----------|------|---------------------------|
| api       | 8000 | FastAPI backend           |
| dashboard | 8501 | Streamlit web interface   |
| bot       | -    | Trading engine (optional) |

### Commands

```bash
# Start all (API + Dashboard)
docker-compose up -d

# Start only dashboard
docker-compose up dashboard -d

# Start with trading bot
docker-compose --profile bot up -d

# View logs
docker-compose logs -f
docker-compose logs -f api
docker-compose logs -f dashboard

# Rebuild after code changes
docker-compose build
docker-compose up -d

# Stop all services
docker-compose down

# Stop and remove volumes
docker-compose down -v
```

### Development Mode

Hot reload enabled for faster development:

```bash
# Start in dev mode (with hot reload)
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up

# Or use alias
alias dc-dev='docker-compose -f docker-compose.yml -f docker-compose.dev.yml'
dc-dev up
dc-dev logs -f
```

### URLs

- **Dashboard:** http://localhost:8501
- **API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs (Swagger UI)

### Environment Variables

Create `.env` from `.env.example`:

```bash
cp .env.example .env
```

Key variables:
- `BINANCE_API_KEY` / `BINANCE_API_SECRET` - Exchange credentials
- `OPENROUTER_API_KEY` - AI model access
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` - Notifications
- `LOG_LEVEL` - Logging verbosity (DEBUG/INFO/WARNING)
- `TRADING_MODE` - paper/live trading mode

## Project Structure

```
src/trading_bot/
├── main.py       # Entry point
├── bot.py        # Trading bot engine
├── config.py     # Configuration
├── api/          # FastAPI backend
├── dashboard/    # Streamlit frontend
├── core/         # Core trading logic
├── strategies/   # Grid + AI strategies
├── ai/           # LLM decision making
├── risk/         # Risk management
├── backtest/     # Backtesting engine
├── alerts/       # Telegram notifications
└── reports/      # Report generation
```

## Status

🚧 In development
