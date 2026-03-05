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

### Sprint 7: Risk Management ✅ DONE
**Goal:** Защита капитала и управление рисками
**Priority:** HIGH — критично перед live trading
**Completed:** 2026-02-28

**Задачи:**
- [x] Position sizing (Kelly criterion / fixed % / ATR-based)
- [x] Stop-loss / take-profit per position
- [x] Daily loss limit (stop trading if exceeded)
- [x] Max drawdown protection
- [x] Risk metrics dashboard (Sharpe, Sortino, Calmar, Profit Factor)
- [ ] Correlation risk (multi-pair) — deferred to multi-pair trading

**Модули:**
- `risk/position_sizer.py` — PositionSizer (Kelly, fixed %, ATR)
- `risk/stop_loss.py` — StopLossManager (SL/TP, trailing)
- `risk/limits.py` — RiskLimits (daily loss, max DD)
- `risk/metrics.py` — RiskMetrics (Sharpe, Sortino, etc.)

---

### Sprint 8: Live Trading Preparation ✅ DONE
**Goal:** Подготовка к торговле на реальные деньги
**Completed:** 2026-03-01

**Задачи:**
- [x] Emergency stop mechanism
- [x] Trade logging to file/DB
- [x] PnL reporting (reports/)
- [ ] Mainnet connection — deferred to after testing
- [ ] API key security (encrypted storage) — deferred
- [ ] Минимальный капитал test ($50-100) — ready when needed

---

### Sprint 9: Web Dashboard ✅ DONE
**Goal:** Веб-интерфейс для мониторинга и управления
**Completed:** 2026-03-02

**Tech:** Streamlit + FastAPI backend

**Задачи:**
- [x] Streamlit dashboard (`dashboard/app.py`)
- [x] FastAPI backend (`api/main.py`)
- [x] Real-time grid visualization
- [x] Position & PnL display
- [x] Trade history table
- [x] AI decisions log
- [x] Manual controls (pause/resume/adjust grid)
- [x] Docker support with hot reload
- [ ] K-line charts with indicators — future
- [ ] Authentication (basic) — future

**URLs:**
- Dashboard: http://localhost:8501
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs

---

### Sprint 10: UI/UX Improvements ✅ DONE
**Goal:** Улучшение интерфейса дашборда
**Completed:** 2026-03-03

**Задачи:**
- [x] Responsive layout fixes
- [x] Widget width improvements
- [x] Configurable API_URL via env
- [x] Shared state for Docker containers

---

### Sprint 11: Alerts & Monitoring ✅ DONE
**Goal:** Multi-channel alerting system
**Completed:** 2026-03-04

**Задачи:**
- [x] Discord webhook alerts
- [x] Telegram notifications
- [x] Email alerts (SMTP)
- [x] Alert on trade execution
- [x] Alert on errors
- [x] Daily summary reports
- [x] Configurable alert channels

**Config (.env):**
- `DISCORD_WEBHOOK_URL` — Discord integration
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` — Telegram
- `SMTP_*` — Email alerts

---

### Sprint 12: Production Hardening ✅ DONE
**Goal:** Production-ready infrastructure
**Completed:** 2026-03-05

**Задачи:**
- [x] Health checks for containers
- [x] Prometheus metrics (`monitoring/metrics.py`)
- [x] Structured logging
- [x] Docker compose production config
- [x] Docker compose monitoring stack
- [ ] VPS deployment — next step
- [ ] 24/7 operation с auto-restart — next step

**Docker Configs:**
- `docker-compose.yml` — base
- `docker-compose.dev.yml` — development with hot reload
- `docker-compose.prod.yml` — production
- `docker-compose.monitoring.yml` — Prometheus/Grafana stack

---

### Sprint 13: VPS Deployment ✅ DONE
**Goal:** Deploy на production сервер
**Completed:** 2026-03-05

**Задачи:**
- [x] Server setup (ts1-rnd-llm01 / 10.48.14.85)
- [x] Docker containers running 24/7
- [x] Discord alerts configured
- [x] Dashboard accessible via VPN

**URLs:**
- Dashboard: http://10.48.14.85:8501
- API: http://10.48.14.85:8000

---

### Sprint 14: Monorepo Restructure ✅ DONE
**Goal:** Переделать репозиторий под multi-bot архитектуру
**Completed:** 2026-03-05

**Структура:**
```
trading-bots/
├── shared/              # Общие модули для всех ботов
│   ├── ai/              # LLM integration
│   ├── alerts/          # Discord, Telegram, Email
│   ├── api/             # FastAPI backend
│   ├── backtest/        # Backtesting engine
│   ├── config/          # Settings management
│   ├── core/            # Exchange, database
│   ├── dashboard/       # Streamlit frontend
│   ├── monitoring/      # Prometheus metrics
│   ├── reports/         # PnL reports
│   ├── risk/            # Risk management
│   └── utils/           # Helpers, logging
├── binance-bot/         # Grid Trading (active)
├── polymarket-bot/      # Prediction Markets (scaffold)
└── README.md
```

**Репозиторий:** https://github.com/RoukSonix/trading-bot (переименовать в trading-bots)

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

---

## 🚀 NautilusTrader Migration (Priority Path)

> **Решение:** Используем NautilusTrader как основную платформу для всех ботов.
> Это production-grade решение с Rust core, готовыми адаптерами для Binance, Polymarket, Interactive Brokers.

### Sprint 17: NautilusTrader Study & Setup ⬜ PLANNED
**Goal:** Изучить NautilusTrader, настроить окружение
**Priority:** HIGH
**Reference:** `/Users/a.lazarev/CentricVoid/nautilus_trader`

**Задачи:**
- [ ] Изучить архитектуру NautilusTrader (docs, examples)
- [ ] Установить nautilus_trader (`pip install nautilus_trader`)
- [ ] Запустить example стратегии (EMA cross, etc.)
- [ ] Понять Strategy class и event handlers
- [ ] Изучить Binance adapter (spot, futures)
- [ ] Запустить backtest на исторических данных

**Документация:**
- https://nautilustrader.io/docs/
- `examples/backtest/` — примеры бэктестов
- `examples/live/binance/` — live trading примеры

---

### Sprint 18: Grid Strategy on NautilusTrader ⬜ PLANNED
**Goal:** Переписать нашу Grid стратегию на NautilusTrader
**Priority:** HIGH

**Задачи:**
- [ ] Создать `GridStrategy(Strategy)` class
- [ ] Реализовать on_start (setup grid levels)
- [ ] Реализовать on_bar (update grid)
- [ ] Реализовать on_order_filled (opposite orders)
- [ ] Добавить dynamic grid bounds
- [ ] Backtest на SOL/USDT или BTC/USDT
- [ ] Сравнить результаты с нашим текущим ботом

**Reference:** Medium tutorial "NautilusTrader Grid Trading Strategy"

---

### Sprint 19: AI Integration with NautilusTrader ⬜ PLANNED
**Goal:** Интегрировать наш AI layer в NautilusTrader стратегии
**Priority:** HIGH

**Архитектура:**
```
NautilusTrader Strategy
    ↓ on_bar()
AI Agent (LangChain)
    ↓ analyze_market()
Grid Optimization
    ↓ 
Order Management (NautilusTrader)
```

**Задачи:**
- [ ] Создать AIGridStrategy с LLM integration
- [ ] Periodic AI review (каждые N баров)
- [ ] AI-based grid optimization
- [ ] Sentiment analysis integration
- [ ] Compare AI vs non-AI performance

---

### Sprint 20: Binance Live Trading (NautilusTrader) ⬜ PLANNED
**Goal:** Live trading на Binance через NautilusTrader
**Priority:** HIGH

**Задачи:**
- [ ] Настроить Binance credentials
- [ ] Testnet → Mainnet migration
- [ ] Paper trading validation
- [ ] Small capital live test ($50-100)
- [ ] Monitoring & alerts
- [ ] Emergency stop mechanism

---

### Sprint 21: Polymarket Bot (NautilusTrader) ⬜ PLANNED
**Goal:** Бот для Polymarket используя готовый adapter
**Priority:** MEDIUM
**Reference:** `/Users/a.lazarev/CentricVoid/nautilus_trader/docs/integrations/polymarket.md`

**Преимущества NautilusTrader:**
- ✅ Готовый PolymarketDataClient
- ✅ Готовый PolymarketExecutionClient
- ✅ USDC.e Polygon integration
- ✅ Signature types (EOA, Magic, Browser)

**Стратегии:**
- Market Making (bid/ask spread)
- Sum-to-One Arbitrage
- AI Probability mispricing

**Задачи:**
- [ ] Настроить Polygon wallet
- [ ] Set allowances для Polymarket contracts
- [ ] Создать PolymarketMarketMaker strategy
- [ ] Backtest на исторических данных
- [ ] Paper trading → Live

---

### Sprint 22: Stocks Bot (Interactive Brokers) ⬜ FUTURE
**Goal:** Бот для торговли акциями через IB
**Priority:** FUTURE
**Reference:** `/Users/a.lazarev/CentricVoid/nautilus_trader/docs/integrations/ib.md`

**Преимущества NautilusTrader:**
- ✅ Готовый IB adapter
- ✅ Stocks, Options, Futures support
- ✅ Multi-venue routing

**Стратегии:**
- Multi-factor stock selection
- Momentum trading
- Sector rotation

**Задачи:**
- [ ] IB account setup
- [ ] Factor-based screening
- [ ] Portfolio optimization
- [ ] Rebalancing logic

---

### Sprint 23: Rust Core Performance ⬜ FUTURE
**Goal:** Максимальная производительность через Rust
**Priority:** FUTURE — когда нужен HFT

**NautilusTrader уже имеет:**
- Rust core (<1ms latency)
- tokio async networking
- Redis state persistence
- Nanosecond resolution

**Задачи:**
- [ ] Profile current performance
- [ ] Optimize hot paths
- [ ] Custom Rust components (если нужно)
- [ ] Benchmark vs competitors

---

## Reference Projects

### NautilusTrader (PRIMARY)
**Location:** `/Users/a.lazarev/CentricVoid/nautilus_trader`
**GitHub:** https://github.com/nautechsystems/nautilus_trader
**Docs:** https://nautilustrader.io/docs/

**Готовые адаптеры:**
- ✅ Binance (Spot, USDT-M Futures, Coin-M)
- ✅ Polymarket (prediction markets)
- ✅ Interactive Brokers (stocks, options)
- ✅ Bybit, OKX, Kraken, dYdX
- ✅ Betfair (sports betting)

**Ключевые модули:**
- `nautilus_trader/adapters/binance/` — Binance integration
- `nautilus_trader/adapters/polymarket/` — Polymarket integration
- `nautilus_trader/adapters/interactive_brokers/` — IB integration
- `nautilus_trader/trading/strategy.py` — Strategy base class
- `examples/` — Примеры стратегий

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
