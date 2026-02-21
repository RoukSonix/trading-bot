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

### Sprint 7: Risk Management ⬜ PLANNED
**Goal:** Защита капитала и управление рисками
**Priority:** HIGH — критично перед live trading

**Задачи:**
- [ ] Position sizing (Kelly criterion / fixed %)
- [ ] Stop-loss / take-profit per position
- [ ] Daily loss limit (stop trading if exceeded)
- [ ] Max drawdown protection
- [ ] Correlation risk (multi-pair)
- [ ] Risk metrics dashboard (console)

**Почему важно:** Без risk management даже прибыльная стратегия может обнулить счёт на одном плохом дне.

---

### Sprint 8: Live Trading Preparation ⬜ PLANNED
**Goal:** Подготовка к торговле на реальные деньги
**Priority:** HIGH

**Задачи:**
- [ ] Mainnet connection (Binance production API)
- [ ] API key security (encrypted storage)
- [ ] Минимальный капитал test ($50-100)
- [ ] Emergency stop mechanism
- [ ] Trade logging to file/DB
- [ ] PnL reporting

---

### Sprint 9: Web Dashboard ⬜ PLANNED
**Goal:** Веб-интерфейс для мониторинга и управления
**Priority:** MEDIUM

**Tech:** Streamlit (reference: QuantMuse dashboard) + FastAPI backend

**Reference:** `/Users/a.lazarev/CentricVoid/QuantMuse/data_service/dashboard/`

**Задачи:**
- [ ] Streamlit dashboard (из QuantMuse)
- [ ] FastAPI backend for API
- [ ] Real-time grid visualization
- [ ] Position & PnL display
- [ ] Trade history table
- [ ] AI decisions log
- [ ] Manual controls (pause/resume/adjust grid)
- [ ] K-line charts with indicators
- [ ] Authentication (basic)

---

### Sprint 10: Infrastructure & DevOps ⬜ PLANNED
**Goal:** Production-ready deployment
**Priority:** MEDIUM

**Задачи:**
- [ ] Docker production setup
- [ ] VPS deployment (DigitalOcean/Hetzner)
- [ ] 24/7 operation с auto-restart
- [ ] Health monitoring (uptime, errors)
- [ ] Backup system (DB, configs)
- [ ] Alerting (Telegram on errors/stops)

---

### Sprint 11: Optimization & Tuning ⬜ PLANNED
**Goal:** Улучшение производительности и прибыльности
**Priority:** LOW (после стабилизации)

**Задачи:**
- [ ] AI prompt optimization (A/B testing)
- [ ] Fee optimization (maker vs taker)
- [ ] Grid parameter tuning (spacing, levels)
- [ ] Backtesting improvements
- [ ] Performance profiling
- [ ] Multi-timeframe analysis

---

### Sprint 12: Monorepo Restructure ⬜ PLANNED
**Goal:** Переделать репозиторий под multi-bot архитектуру
**Priority:** LOW — после стабилизации текущего бота

**Зачем:**
- Polymarket бот (prediction markets)
- Stocks бот (акции)
- Общий код (AI, alerts, config, factors)
- C++ backend для high-perf execution (позже)

**Целевая структура:**
```
trading-bots/
├── shared/                    # Общий код для всех ботов
│   ├── ai/                    # LLM integration, prompts
│   ├── alerts/                # Telegram, Discord notifications
│   ├── config/                # Settings, env management
│   ├── factors/               # Factor analysis (из QuantMuse)
│   ├── api_gateway/           # Rate limiting, caching
│   ├── vector_db/             # News embeddings, semantic search
│   └── utils/                 # Logging, helpers
├── binance-bot/               # Crypto Grid Trading
├── polymarket-bot/            # Prediction Markets
├── stocks-bot/                # Stocks (Yahoo, Alpha Vantage)
└── cpp-engine/                # C++ high-perf backend (future)
```

**Задачи:**
- [ ] Создать монорепо `trading-bots`
- [ ] Вынести shared код
- [ ] Перенести binance-bot
- [ ] Настроить imports
- [ ] Создать scaffolds для всех ботов

---

### Sprint 13: Factor Analysis Integration ⬜ FUTURE
**Goal:** Добавить factor analysis из QuantMuse
**Priority:** FUTURE
**Reference:** `/Users/a.lazarev/CentricVoid/QuantMuse/data_service/factors/`

**Factors:**
- Momentum (60d, 20d returns)
- Value (P/E, P/B ratios)
- Quality (ROE, debt ratio)
- Volatility (ATR, std dev)
- Size (market cap)

**Задачи:**
- [ ] Портировать FactorCalculator из QuantMuse
- [ ] Интегрировать с нашим AI agent
- [ ] Multi-factor scoring для grid optimization
- [ ] Factor-based stock/crypto screening

---

### Sprint 14: Strategy Framework Expansion ⬜ FUTURE
**Goal:** Добавить 8 стратегий из QuantMuse
**Priority:** FUTURE
**Reference:** `/Users/a.lazarev/CentricVoid/QuantMuse/data_service/strategies/`

**Стратегии для добавления:**
1. Momentum Strategy
2. Value Strategy
3. Quality Growth Strategy
4. Multi-Factor Strategy
5. Mean Reversion Strategy
6. Low Volatility Strategy
7. Sector Rotation Strategy
8. Risk Parity Strategy

**Задачи:**
- [ ] Адаптировать стратегии под crypto
- [ ] Strategy registry pattern
- [ ] Parameter optimization framework
- [ ] A/B testing между стратегиями

---

### Sprint 15: API Gateway & Caching ⬜ FUTURE
**Goal:** Production-grade API management
**Priority:** FUTURE
**Reference:** `/Users/a.lazarev/CentricVoid/QuantMuse/data_service/api/`

**Компоненты:**
- Rate limiting per endpoint
- Response caching (Redis)
- API monitoring & metrics
- Automatic retries with backoff

**Задачи:**
- [ ] Портировать api_manager из QuantMuse
- [ ] Redis integration
- [ ] Metrics dashboard
- [ ] API documentation (OpenAPI)

---

### Sprint 16: Vector DB for News ⬜ FUTURE
**Goal:** Semantic search по новостям для AI analysis
**Priority:** FUTURE
**Reference:** `/Users/a.lazarev/CentricVoid/QuantMuse/data_service/vector_db/`

**Компоненты:**
- Embedding generation (sentence-transformers)
- Vector storage (ChromaDB / Pinecone)
- Semantic search
- News sentiment correlation

**Задачи:**
- [ ] Портировать vector_store из QuantMuse
- [ ] News fetching pipeline
- [ ] Sentiment → trading signal correlation
- [ ] Integration с AI agent

---

### Sprint 17: Polymarket Bot ⬜ FUTURE
**Goal:** Бот для prediction markets
**Priority:** FUTURE — после monorepo

**Стратегии:**
- Market Making (bid/ask spread, 1-3% monthly)
- Sum-to-One Arbitrage (YES + NO < $1)
- Weather Arbitrage (NOAA vs market)
- AI Probability (news → probability mispricing)

**Задачи:**
- [ ] Polymarket CLOB API integration
- [ ] Market making strategy
- [ ] Arbitrage detection engine
- [ ] Polygon blockchain integration

---

### Sprint 18: Stocks Bot ⬜ FUTURE
**Goal:** Бот для торговли акциями
**Priority:** FUTURE — после стабилизации crypto

**Data Sources:**
- Yahoo Finance (free)
- Alpha Vantage (free tier)
- IEX Cloud (paid)

**Стратегии:**
- Multi-factor stock selection
- Momentum trading
- Value investing
- Sector rotation

**Задачи:**
- [ ] Yahoo Finance integration
- [ ] Factor-based stock screening
- [ ] Portfolio optimization
- [ ] Rebalancing logic

---

### Sprint 19: C++ High-Performance Engine ⬜ FUTURE
**Goal:** Low-latency execution engine
**Priority:** FUTURE — когда понадобится HFT
**Reference:** `/Users/a.lazarev/CentricVoid/QuantMuse/backend/`

**Компоненты:**
- Order execution (<1ms latency)
- Risk management engine
- Portfolio calculations
- Data loading & caching

**Задачи:**
- [ ] Study QuantMuse C++ backend
- [ ] CMake build system
- [ ] Python bindings (pybind11)
- [ ] Benchmark vs pure Python

---

## Reference Projects

### QuantMuse
**Location:** `/Users/a.lazarev/CentricVoid/QuantMuse`
**GitHub:** https://github.com/0xemmkty/QuantMuse

**Useful modules:**
- `data_service/factors/` — Factor analysis
- `data_service/strategies/` — 8 quant strategies
- `data_service/dashboard/` — Streamlit UI
- `data_service/api/` — API gateway
- `data_service/vector_db/` — Vector embeddings
- `backend/` — C++ execution engine

---

## Immediate Next Steps

---

## Notes

- Start simple, iterate
- Never risk more than willing to lose
- Paper trade before live
- Document everything
