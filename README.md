# Trading Bot

AI-assisted automated trading bot for cryptocurrency markets.

## Features

- Grid Trading strategy
- AI-powered decision making (LangChain + OpenRouter)
- Freqtrade core for order execution
- Binance exchange support
- Risk management
- Telegram notifications

## Setup

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .

# Copy config
cp .env.example .env
# Edit .env with your API keys

# Run
python -m trading_bot.main
```

## Project Structure

```
src/trading_bot/
├── main.py       # Entry point
├── core/         # Freqtrade integration
├── strategies/   # Grid + AI strategies
└── ai/           # LLM decision making
```

## Status

🚧 In development
