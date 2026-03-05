# Trading Bots Monorepo

AI-assisted automated trading bots for multiple markets.

## Architecture

```
trading-bots/
├── shared/                    # Shared code for all bots
│   ├── ai/                    # LLM integration (LangChain + OpenRouter)
│   ├── alerts/                # Telegram, Discord, Email notifications
│   ├── config/                # Settings, env management
│   ├── core/                  # Database, state, indicators
│   ├── risk/                  # Position sizing, stop-loss, limits
│   ├── api/                   # FastAPI backend
│   ├── dashboard/             # Streamlit UI
│   ├── backtest/              # Backtesting engine
│   ├── reports/               # PnL reports
│   ├── factors/               # Multi-factor analysis (Sprint 15)
│   ├── vector_db/             # Vector DB + news sentiment (Sprint 16)
│   ├── monitoring/            # Prometheus metrics
│   └── utils/                 # Logging, helpers
├── binance-bot/               # Binance Grid Trading Bot
│   ├── src/binance_bot/       # Bot-specific code
│   ├── scripts/               # Run scripts
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── ...
├── polymarket-bot/            # Prediction Markets Bot (scaffold)
│   ├── src/polymarket_bot/
│   ├── Dockerfile
│   └── ...
└── README.md
```

## Bots

| Bot | Market | Status | Description |
|-----|--------|--------|-------------|
| **binance-bot** | Binance (Crypto) | Production-ready | Grid trading + AI-enhanced decisions |
| **polymarket-bot** | Polymarket | Scaffold | Prediction markets (planned) |

## Quick Start

### Binance Bot

```bash
cd binance-bot

# Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Configure
cp .env.example .env
# Edit .env with your API keys

# Run (local)
PYTHONPATH=../:.  python scripts/run_paper_trading.py

# Run (Docker)
docker compose up -d
```

### Docker Commands

```bash
cd binance-bot

# Start API + Dashboard
docker compose up -d

# Start with trading bot
docker compose --profile bot up -d

# Development mode (hot reload)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up

# Production
docker compose -f docker-compose.prod.yml up -d

# Monitoring (Prometheus + Grafana)
docker compose -f docker-compose.monitoring.yml up -d
```

### URLs

- **Dashboard:** http://localhost:8501
- **API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs
- **Prometheus:** http://localhost:9090
- **Grafana:** http://localhost:3000

## Shared Modules

All bots share common infrastructure:

- **AI** - LLM-powered market analysis via OpenRouter
- **Alerts** - Multi-channel notifications (Telegram, Discord, Email)
- **Risk** - Position sizing (Kelly/fixed %), stop-loss, daily limits, drawdown protection
- **API** - FastAPI backend with trade/position/order endpoints
- **Dashboard** - Streamlit UI with charts, grid view, trade history
- **Backtest** - Historical data backtesting engine
- **Monitoring** - Prometheus metrics + Grafana dashboards
- **Factors** - Multi-factor analysis (momentum, volatility, RSI, volume) for grid optimization
- **Vector DB** - ChromaDB-based news storage with Ollama (nomic-embed-text) embeddings and sentiment analysis

### Factor Analysis (Sprint 15)

The `shared/factors/` module provides quantitative factor analysis:

```python
from shared.factors import factor_calculator, factor_strategy

# Calculate factors from OHLCV data
factors = factor_calculator.calculate(ohlcv_df, "BTC/USDT")
print(f"Momentum: {factors.momentum_score:+.3f}")
print(f"Volatility: {factors.volatility_score:.3f}")
print(f"RSI Signal: {factors.rsi_signal:+.2f}")

# Score factors for grid optimization
score = factor_strategy.score(factors)
print(f"Regime: {score.regime.value}")
print(f"Grid suitability: {score.grid_suitability:.0%}")
print(f"Action: {score.action.value}")

# Generate AI context
context = factor_strategy.to_ai_context(factors, score)
```

### Vector DB & News Sentiment (Sprint 16)

The `shared/vector_db/` module provides news-aware trading signals:

```python
from shared.vector_db import news_fetcher, news_store, sentiment_analyzer

# Fetch and store news
count = await news_fetcher.fetch_and_store(news_store, categories=["BTC"])

# Query similar news
results = news_store.query("bitcoin price prediction", n_results=5)

# Analyze sentiment
sentiment = sentiment_analyzer.analyze_articles(results)
signal = sentiment_analyzer.get_trading_signal(sentiment, current_rsi=45.0)
print(f"Signal: {signal['signal']}, Strength: {signal['strength']:.2f}")

# Generate AI context
context = sentiment_analyzer.to_ai_context(sentiment)
```

**Prerequisites** (Sprint 16):
```bash
# Install Ollama and pull the embedding model
ollama pull nomic-embed-text

# Install Python dependencies
pip install langchain-ollama chromadb
```

**Environment variables** (optional):
- `OLLAMA_BASE_URL` - Ollama server URL (default: `http://localhost:11434`)
- `OLLAMA_EMBED_MODEL` - Embedding model (default: `nomic-embed-text`)

## Development

```bash
# Install all dependencies
cd binance-bot && pip install -e ".[dev,dashboard]"

# Set PYTHONPATH for local development
export PYTHONPATH=/path/to/trading-bots:/path/to/trading-bots/binance-bot/src

# Run tests
pytest

# Lint
ruff check .
```

## Environment Variables

See `binance-bot/.env.example` for the full list. Key variables:

- `BINANCE_API_KEY` / `BINANCE_SECRET_KEY` - Exchange credentials
- `OPENROUTER_API_KEY` - AI model access
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` - Notifications
- `DISCORD_WEBHOOK_URL` - Discord alerts
- `LOG_LEVEL` - Logging verbosity (DEBUG/INFO/WARNING)
- `TRADING_MODE` - paper/live trading mode
