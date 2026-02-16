# Trading Bot Research

## Overview
Research on building a trading bot - technologies, frameworks, and approaches.

## Quick Links
- [Strategies](./docs/strategies.md) - Trading strategy descriptions
- [Instruments](./docs/instruments.md) - Asset classes comparison
- [Exchanges](./docs/exchanges.md) - Brokers & exchanges

---

## Top Open-Source Trading Bots

### 1. Freqtrade
**Language:** Python 3.11+  
**GitHub:** https://github.com/freqtrade/freqtrade  
**Stars:** 25k+

**Features:**
- Backtesting
- Strategy optimization with ML (FreqAI)
- Telegram + WebUI control
- SQLite persistence
- Dry-run mode
- Supports major exchanges: Binance, Bybit, OKX, Kraken, Gate.io, etc.

**Pros:**
- Mature, well-documented
- Large community
- Built-in ML optimization
- Active development

**Cons:**
- Crypto-focused (not stocks/forex)
- Requires Python knowledge

---

### 2. Hummingbot
**Language:** Python + Rust  
**GitHub:** https://github.com/hummingbot/hummingbot  
**Stars:** 9k+

**Features:**
- Market making & arbitrage
- Cross-exchange trading
- Paper trading
- CEX + DEX support

**Pros:**
- Institutional-grade
- High-frequency trading focus
- Good for market making

**Cons:**
- Steeper learning curve
- More complex architecture

---

### 3. Superalgos
**Language:** JavaScript/TypeScript  
**GitHub:** https://github.com/Superalgos/Superalgos

**Features:**
- Visual strategy builder
- Integrated charting
- Backtesting & paper trading
- Multi-server deployment

**Pros:**
- No-code option
- Visual design
- Comprehensive

**Cons:**
- JS-based (different paradigm)
- Heavier resource usage

---

### 4. NautilusTrader
**Language:** Python + Rust (performance)  
**GitHub:** https://github.com/nautechsystems/nautilus_trader

**Features:**
- High-frequency trading
- Backtesting engine
- Crypto & forex support
- C++ speed with Python API

**Pros:**
- Extremely fast (Rust core)
- Professional grade
- Multi-asset

**Cons:**
- Complex setup
- Less community resources

---

### 5. Wolfinch
**Language:** Python  
**GitHub:** https://github.com/wolfinch/wolfinch

**Features:**
- Modular architecture
- Easy to extend
- Equity + crypto support
- Custom indicators

**Pros:**
- Simple, clean code
- Easy to customize
- Lightweight

**Cons:**
- Smaller community
- Less features

---

## Decision Factors

### What to build?
- **Crypto only?** → Freqtrade, Hummingbot
- **Stocks/Forex + Crypto?** → NautilusTrader
- **No-code/Visual?** → Superalgos
- **Custom strategy from scratch?** → Python own implementation

### Tech Stack Recommendation

**Option A: Freqtrade-based**
- Use Freqtrade as foundation
- Customize strategies in Python
- Deploy with Docker

**Option B: Custom Python Bot**
- Full control
- Use CCXT for exchange integration
- Build own backtester

**Option C: Hybrid**
- NautilusTrader for execution
- Custom Python for strategies

---

## Research Documents

### Strategies
See [strategies.md](./docs/strategies.md) for detailed explanation of:
- Grid Trading
- DCA (Dollar-Cost Averaging)
- Momentum Trading
- Mean Reversion
- Scalping
- Swing Trading
- Trend Following
- Arbitrage
- Market Making

### Instruments
See [instruments.md](./docs/instruments.md) for:
- Cryptocurrency
- Stocks
- Forex
- Commodities
- Indices
- ETFs
- Options

### Exchanges
See [exchanges.md](./docs/exchanges.md) for:
- Crypto exchanges (Binance, Bybit, OKX, Kraken, Coinbase)
- Stock brokers (IBKR, Fidelity, Robinhood, eToro)
- Forex brokers (OANDA, IG, FOREX.com)
- API recommendations for bots

---

## Next Steps

1. [x] Define strategy types - see docs/strategies.md
2. [x] Define instruments - see docs/instruments.md  
3. [x] Define exchanges - see docs/exchanges.md
4. [ ] Choose trading pair/instrument
5. [ ] Choose strategy
6. [ ] Select tech stack
7. [ ] Set up development environment
8. [ ] Implement backtesting
9. [ ] Paper trade
10. [ ] Live trading (small funds)

---

## Resources
- CCXT library: https://github.com/ccxt/ccxt (exchange integration)
- TA-Lib: Technical analysis library
- Backtrader: Python backtesting framework
- QuantConnect: Alternative platform

---

## AI Agents for Trading

### Polymarket Agents (Recommended Reference)
**GitHub:** https://github.com/Polymarket/agents

Modern AI-driven trading bot architecture using LLMs:

**Architecture:**
```
Trader.one_best_trade():
  1. Get all events           → polymarket.get_all_tradeable_events()
  2. Filter via RAG           → agent.filter_events_with_rag()
  3. Map to markets           → agent.map_filtered_events_to_markets()
  4. Filter markets           → agent.filter_markets()
  5. Find best trade (LLM)   → agent.source_best_trade()
  6. Execute                  → polymarket.execute_market_order()
```

**Tech Stack:**
- **LLM:** GPT-3.5-turbo / GPT-4 (LangChain)
- **RAG:** Chroma (vector DB for semantic search)
- **API:** Polymarket Gamma API
- **Language:** Python 3.9+

**Key Components:**
- `executor.py` - AI decision engine (filters, prompts LLM)
- `polymarket.py` - Trade execution
- `gamma.py` - Market data fetching
- `chroma.py` - RAG for semantic search

**Why it's interesting:**
- AI makes trading decisions (not just rule-based)
- Uses RAG to filter relevant events/news
- LLM does "superforecasting" - analyzes probability
- Modular, extensible architecture

**Similar approach for your bot:**
1. Use CCXT instead of Polymarket API
2. Replace RAG with news sentiment analysis
3. Use same prompt engineering for strategy

---

### Related AI Trading Resources

**Prompt Engineering for Trading:**
- Analyze market conditions
- Generate trading signals
- Risk assessment
- Position sizing

**RAG Applications:**
- News sentiment aggregation
- Historical pattern matching
- Event correlation

---

## Implementation Approaches

### Approach 1: Rule-Based (Traditional)
- Predefined entry/exit rules
- Backtestable
- No AI

**Tools:** Freqtrade, Backtrader, custom Python

### Approach 2: AI-Assisted (Hybrid)
- AI suggests trades
- Human approves
- Semi-automated

**Tools:** Polymarket Agents pattern, LangChain + CCXT

### Approach 3: AI-Full (Autonomous)
- AI makes all decisions
- Fully automated
- Complex, requires monitoring

**Tools:** Custom LLM agent, reinforcement learning
