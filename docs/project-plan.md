# Trading Bot Project Plan

## Project Overview
- **Name:** Trading Bot
- **Type:** AI-assisted trading bot
- **Goal:** Automated trading with AI decision making
- **Status:** Research completed, planning phase

---

## Phase 1: Foundation (Week 1-2)

### 1.1 Tech Stack Selection
- [x] **Language:** Python 3.14+
- [x] **Trading Core:** Freqtrade (as library)
- [x] **Exchange API:** CCXT (via Freqtrade)
- [x] **AI Layer:** LangChain + OpenRouter
- [ ] **Data Storage:** SQLite / PostgreSQL
- [ ] **Deployment:** Docker

### 1.2 Architecture Design
```
┌─────────────────────────────────────────────────────────────┐
│                      TRADING BOT                             │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    │
│  │   Inputs    │    │   Brain     │    │   Freqtrade │    │
│  │             │───▶│   (AI)      │───▶│   (Core)    │    │
│  │ - Market    │    │ - LLM       │    │ - Orders    │    │
│  │ - News      │    │ - Strategy  │    │ - Positions │    │
│  │ - Signals   │    │ - Risk      │    │ - CCXT      │    │
│  └─────────────┘    └─────────────┘    └─────────────┘    │
│                           │                   │             │
│                    ┌──────▼──────┐            │             │
│                    │   Storage   │◀───────────┘             │
│                    │ - SQLite    │                         │
│                    │ - Logs      │                         │
│                    └─────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

**Stack:**
- **Freqtrade Core:** Order execution, position management, exchange connectivity
- **AI Agent:** LLM decision making (OpenRouter)
- **Custom Strategy:** Grid with AI enhancements

### 1.3 Core Components
1. **Data Collector** — Market data, news, signals
2. **AI Agent** — Decision making (LLM-based via LangChain)
3. **Strategy Engine** — Grid with AI enhancements
4. **Risk Manager** — Position sizing, stop-loss
5. **Freqtrade Core** — Order execution, position management
6. **Portfolio Tracker** — PnL, positions

---

## Phase 2: Core Development (Week 3-6)

### 2.1 Basic Infrastructure
- [ ] Project structure (Python package)
- [ ] Docker setup
- [ ] Config management (.env)
- [ ] Logging system
- [ ] Database schema

### 2.2 Exchange Integration
- [ ] Setup Freqtrade as library
- [ ] API key management
- [ ] Testnet connection (Binance Testnet)
- [ ] Basic order execution (market/limit)
- [ ] Position tracking

### 2.3 Data Pipeline
- [ ] Price data fetching
- [ ] Indicator calculation (pandas-ta)
- [ ] News/sentiment fetching
- [ ] Data storage

### 2.4 AI Agent
- [ ] LangChain setup
- [ ] Prompt templates
- [ ] Decision flow
- [ ] Error handling

---

## Phase 3: AI Implementation (Week 7-10)

### 3.1 Strategy Layer
- [ ] Strategy definitions (from docs/strategies.md)
- [ ] Strategy selection logic
- [ ] Parameter optimization

### 3.2 Risk Management
- [ ] Position sizing algorithms
- [ ] Stop-loss / take-profit
- [ ] Daily loss limits
- [ ] Portfolio diversification

### 3.3 AI Decision Making
- [ ] Market analysis prompts
- [ ] Signal generation
- [ ] Confidence scoring
- [ ] Human-in-the-loop option

---

## Phase 4: Testing (Week 11-12)

### 4.1 Backtesting
- [ ] Historical data setup
- [ ] Backtest engine
- [ ] Strategy validation
- [ ] Performance metrics

### 4.2 Paper Trading
- [ ] Paper trading mode
- [ ] Mock execution
- [ ] Real-time monitoring
- [ ] Performance tracking

### 4.3 Live Trading (Small)
- [ ] Live connection
- [ ] Small capital deployment
- [ ] Monitoring dashboard
- [ ] Alerting system

---

## Phase 5: Production (Week 13+)

### 5.1 Infrastructure
- [ ] VPS/Server setup
- [ ] 24/7 operation
- [ ] Monitoring & alerts
- [ ] Backup system

### 5.2 Optimization
- [ ] Performance tuning
- [ ] Strategy refinement
- [ ] AI prompt optimization
- [ ] Fee optimization

### 5.3 Web Dashboard
- [ ] Real-time grid visualization
- [ ] Position & PnL display
- [ ] Trade history
- [ ] AI decisions log
- [ ] Manual controls (pause/resume/adjust)
- [ ] Tech: FastAPI + React/Next.js or HTMX

---

## Technical Decisions to Make

### 1. AI Approach
- [x] **Full AI** (autonomous) - Selected

### 2. Trading Style
- [x] **Crypto only** - Selected (+ Stocks later)

### 3. Strategy Type
- [x] **Grid Trading** - Selected by Andrey (2026-02-16)
- [ ] DCA
- [ ] Momentum
- [ ] Mean Reversion

**Rationale:**
- Simple to understand
- Proven to work in research (+9-21% in downtrends)
- Works well in volatile crypto markets
- Easy to automate

### 4. Implementation
- [x] **Freqtrade as core + custom AI** - Selected by Andrey (2026-02-16)

### 4. Initial Exchange
- [x] **Binance** - Selected

### 5. AI Provider
- [x] **OpenRouter** (unified API to multiple LLMs)
  - Models: GPT-4, Claude, Llama, Mistral, etc.
  - Cost-effective
  - Unified interface

---

## Development Sprints

### Sprint 1: Exchange Connection ✅ DONE
**Goal:** Подключиться к Binance testnet и получить данные
**Time:** ~30 min
**Completed:** 2025-02-19

- [x] Config module (pydantic-settings)
- [x] Exchange client (CCXT → Binance testnet)
- [x] Базовые операции:
  - [x] Получить баланс
  - [x] Получить текущую цену
  - [x] Получить order book
  - [x] Получить OHLCV (свечи)
- [x] Тест: запустить и увидеть данные в консоли

### Sprint 2: Data Layer ✅ DONE
**Goal:** Сбор и хранение рыночных данных
**Time:** ~20 min
**Completed:** 2025-02-19

- [x] Database models (OHLCV, Trade, Position)
- [x] Fetch OHLCV данные (свечи)
- [x] Сохранение истории в SQLite
- [x] Индикаторы (SMA, EMA, RSI, BB, MACD, ATR)
- [x] Market analysis output

### Sprint 3: Grid Strategy ✅ DONE
**Goal:** Реализовать Grid Trading логику
**Time:** ~15 min
**Completed:** 2025-02-19

- [x] Strategy base class (BaseStrategy, Signal, GridLevel)
- [x] Grid logic:
  - [x] Расчёт уровней сетки (price levels)
  - [x] Buy/Sell сигналы
  - [x] Auto-create opposite levels after fills
- [x] Paper trading mode (симуляция)
- [x] Visual grid status display

### Sprint 4: Order Execution ✅ DONE
**Goal:** Реальное исполнение ордеров
**Time:** ~15 min
**Completed:** 2025-02-19

- [x] Order manager (limit/market orders)
- [x] Limit orders (buy/sell) — tested on testnet
- [x] Market orders — executed real trade!
- [x] Position tracking (entry price, amount)
- [x] PnL расчёт (unrealized + realized)

### Sprint 5: AI Layer ✅ DONE
**Goal:** AI-enhanced decision making
**Completed:** 2026-02-20

- [x] LangChain setup + OpenRouter
- [x] Market analysis prompts
- [x] AI-enhanced signals (AIGridStrategy)
- [x] Risk assessment
- [x] Periodic AI review

### Sprint 6: Integration & Testing ✅ DONE
**Goal:** Собрать всё вместе
**Completed:** 2026-02-20

- [x] End-to-end pipeline (bot.py)
- [x] Backtesting engine (backtest/)
- [x] Telegram alerts (alerts/)
- [ ] Paper trading 24h test (ready to run)

---

## Immediate Next Steps

---

## Notes

- Start simple, iterate
- Never risk more than willing to lose
- Paper trade before live
- Document everything
