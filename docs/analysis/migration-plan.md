# Migration Plan: Hybrid Architecture (Jesse + Our AI Layer)

**Date:** 2026-03-07  
**Updated:** 2026-03-07 — Changed approach: parallel bot, not replacement  
**Decision:** Option C — Jesse as trading framework foundation, our AI/sentiment/factors as enhancement layer  
**Goal:** Lаconic, cohesive system that leverages Jesse's battle-tested trading engine while preserving our unique AI-powered grid trading

## Approach: Parallel Development

**We do NOT replace the existing binance-bot.** Instead, we build a new Jesse-based bot (`jesse-bot/`) side by side in the monorepo. Both bots run simultaneously on the same market — we compare results and decide which one stays.

```
trading-bots/
├── binance-bot/       # EXISTING — keeps running, no changes
├── jesse-bot/         # NEW — Jesse-based bot with our AI layer
├── polymarket-bot/    # FUTURE — scaffold
└── shared/            # Shared modules (both bots can use enhancements/)
```

**Why:**
- Zero risk to current bot
- Side-by-side performance comparison (same market, same period)
- If Jesse bot wins → gradually sunset binance-bot
- If binance-bot wins → we still learned from Jesse, keep useful parts
- Shared enhancements (AI, sentiment, factors) work for both

---

## New Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR LAYER                     │
│        (Our code: bot runner, config, deployment)        │
└────────────┬──────────────────────────┬──────────────────┘
             │                          │
┌────────────▼──────────┐  ┌────────────▼──────────────────┐
│   JESSE FRAMEWORK     │  │   OUR ENHANCEMENT LAYER       │
│                       │  │                               │
│ • Strategy lifecycle  │  │ • AI Agent (LangChain/LLM)    │
│ • 170+ indicators     │  │ • News Sentiment (ChromaDB)   │
│ • Backtesting engine  │  │ • Factor Analysis             │
│ • Optimization (Optuna│  │ • Alert Manager (Discord/etc) │
│ • Exchange adapters   │  │ • Custom Dashboard (Streamlit) │
│ • Position/Order mgmt │  │ • Emergency Stop              │
│ • Risk (TP/SL/sizing) │  │                               │
│ • Metrics (30+)       │  │                               │
│ • Live trading        │  │                               │
└───────────────────────┘  └───────────────────────────────┘
```

### Key Principle

**Jesse handles WHAT to trade and HOW to execute. Our AI layer handles WHEN and WHY.**

Jesse's Strategy class has lifecycle hooks (`before()`, `after()`, `update_position()`, `should_long()`, `go_long()`, filters, hyperparameters) that are perfect injection points for our AI layer.

---

## New Repository Structure

```
trading-bots/
├── binance-bot/                     # EXISTING — unchanged, keeps running
│   └── ...                          # (all current code stays as-is)
│
├── jesse-bot/                       # NEW — Jesse-based bot
│   ├── strategies/                  # Jesse strategy plugins
│   │   ├── AIGridStrategy/          # Our grid strategy as Jesse plugin
│   │   │   ├── __init__.py          # Strategy class (extends jesse.Strategy)
│   │   │   └── ai_mixin.py          # AI enhancement mixin
│   │   ├── AIGridShort/             # Short-only variant
│   │   │   └── __init__.py
│   │   └── AIMomentum/              # Future: momentum strategy
│   │       └── __init__.py
│   ├── config.py                    # Jesse config (exchanges, DB, logging)
│   ├── routes.py                    # Trading routes (symbol + timeframe + strategy)
│   ├── live-config.py               # Live trading config
│   ├── enhancements/                # OUR unique modules
│   │   ├── ai/                      # LLM integration (ported from shared/ai)
│   │   │   ├── agent.py
│   │   │   ├── prompts.py
│   │   │   └── config.py
│   │   ├── sentiment/               # News pipeline (ported from shared/vector_db)
│   │   │   ├── news_fetcher.py
│   │   │   ├── vector_store.py
│   │   │   ├── embeddings.py
│   │   │   └── analyzer.py
│   │   ├── factors/                 # Factor analysis (ported from shared/factors)
│   │   │   ├── calculator.py
│   │   │   └── regime.py
│   │   ├── alerts/                  # Enhanced alerting (ported from shared/alerts)
│   │   │   ├── manager.py
│   │   │   ├── discord.py
│   │   │   ├── email.py
│   │   │   └── rules.py
│   │   └── emergency/
│   │       └── stop.py
│   ├── dashboard/                   # Streamlit frontend (adapted for Jesse)
│   │   ├── app.py
│   │   └── components/
│   ├── scripts/                     # Entry points
│   │   ├── run_backtest.py
│   │   ├── run_live.py
│   │   └── run_compare.py           # Compare jesse-bot vs binance-bot results
│   ├── tests/
│   │   ├── test_strategy.py
│   │   ├── test_ai_integration.py
│   │   └── conftest.py
│   ├── docker-compose.yml           # Jesse + PostgreSQL
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
│
├── polymarket-bot/                  # FUTURE — scaffold
│   └── ...
│
├── shared/                          # EXISTING — shared modules (both bots can use)
│   └── ...
│
├── docs/
│   └── analysis/                    # This folder
│
├── AGENTS.md
└── README.md
```

### Comparison Mode

Both bots trade the same pair (BTC/USDT) on the same timeframe. `scripts/run_compare.py` fetches metrics from both and outputs a side-by-side report:

```
==========================================
   BOT COMPARISON: 2026-03-07 → 2026-03-14
==========================================
                 binance-bot    jesse-bot
Return:          +1.23%         +1.87%
Sharpe:          0.42           0.61
Max DD:          -3.1%          -2.4%
Win Rate:        58%            63%
Trades:          47             39
AI Reviews:      12             12
==========================================
```

---

## Sprint Plan

### Sprint M1: Jesse Foundation (3-4 days)

**Goal:** Jesse installed, configured, running backtest with a simple strategy

**Tasks:**

1. **Install Jesse framework**
   ```bash
   pip install jesse
   ```
   Jesse requires PostgreSQL for candle storage (live mode) or can use in-memory for backtests.

2. **Create `jesse-config/` project structure**
   - `config.py` — exchange config (Binance, futures, leverage)
   - `routes.py` — BTC/USDT on 1h timeframe
   - `.env` — API keys (reuse existing)

3. **Write a minimal grid strategy as Jesse Strategy subclass**
   ```python
   # jesse-config/strategies/AIGridStrategy/__init__.py

   from jesse.strategies import Strategy
   import jesse.indicators as ta
   from jesse import utils

   class AIGridStrategy(Strategy):
       def __init__(self):
           super().__init__()
           # Grid state
           self.vars['grid_levels'] = []
           self.vars['grid_center'] = None
           self.vars['grid_direction'] = 'both'
           self.vars['last_review_index'] = 0

       def hyperparameters(self):
           return [
               {'name': 'grid_levels', 'type': int, 'min': 3, 'max': 30, 'default': 10},
               {'name': 'grid_spacing_pct', 'type': float, 'min': 0.3, 'max': 5.0, 'default': 1.5},
               {'name': 'amount_pct', 'type': float, 'min': 1.0, 'max': 10.0, 'default': 5.0},
               {'name': 'review_interval', 'type': int, 'min': 5, 'max': 60, 'default': 15},
           ]

       def should_long(self) -> bool:
           # Grid logic: should we open a long position?
           return self._check_grid_buy_signal()

       def should_short(self) -> bool:
           return self._check_grid_sell_signal()

       def go_long(self):
           qty = utils.size_to_qty(
               self.balance * (self.hp['amount_pct'] / 100),
               self.price
           )
           self.buy = qty, self.price  # market order
           self.stop_loss = qty, self._calculate_stop_loss('long')
           self.take_profit = qty, self._calculate_take_profit('long')

       def go_short(self):
           qty = utils.size_to_qty(
               self.balance * (self.hp['amount_pct'] / 100),
               self.price
           )
           self.sell = qty, self.price
           self.stop_loss = qty, self._calculate_stop_loss('short')
           self.take_profit = qty, self._calculate_take_profit('short')

       def before(self):
           """Called BEFORE strategy logic each candle — perfect for AI/factors."""
           # This is where our AI layer hooks in (Sprint M3)
           pass

       def after(self):
           """Called AFTER strategy logic each candle."""
           pass

       def update_position(self):
           """Called when position is open — manage trailing, grid adjust."""
           pass

       def filters(self):
           """Pre-trade filters — AI confidence check goes here."""
           return [
               self._filter_volatility,
               self._filter_trend,
           ]

       # --- Grid Logic ---

       def _setup_grid(self):
           """Initialize grid levels around current price."""
           center = self.price
           spacing = self.hp['grid_spacing_pct'] / 100
           n_levels = self.hp['grid_levels']

           levels = []
           for i in range(1, n_levels + 1):
               levels.append({
                   'price': center * (1 + spacing * i),
                   'side': 'sell',
                   'filled': False,
               })
               levels.append({
                   'price': center * (1 - spacing * i),
                   'side': 'buy',
                   'filled': False,
               })

           self.vars['grid_levels'] = levels
           self.vars['grid_center'] = center

       def _check_grid_buy_signal(self) -> bool:
           """Check if price crossed below any buy grid level."""
           if not self.vars['grid_levels']:
               self._setup_grid()

           for level in self.vars['grid_levels']:
               if level['side'] == 'buy' and not level['filled']:
                   if self.price <= level['price']:
                       level['filled'] = True
                       return True
           return False

       def _check_grid_sell_signal(self) -> bool:
           """Check if price crossed above any sell grid level."""
           if not self.vars['grid_levels']:
               return False

           for level in self.vars['grid_levels']:
               if level['side'] == 'sell' and not level['filled']:
                   if self.price >= level['price']:
                       level['filled'] = True
                       return True
           return False

       def _calculate_stop_loss(self, side: str) -> float:
           atr = ta.atr(self.candles, 14)
           if side == 'long':
               return self.price - atr * 1.5
           return self.price + atr * 1.5

       def _calculate_take_profit(self, side: str) -> float:
           atr = ta.atr(self.candles, 14)
           if side == 'long':
               return self.price + atr * 2.0
           return self.price - atr * 2.0

       def _filter_volatility(self) -> bool:
           """Reject trades in extreme volatility."""
           atr = ta.atr(self.candles, 14)
           return atr / self.price < 0.05  # ATR < 5% of price

       def _filter_trend(self) -> bool:
           """Don't trade against strong trends."""
           return True  # Will be enhanced by AI in Sprint M3
   ```

4. **Run Jesse backtest to validate**
   ```bash
   jesse backtest 2025-01-01 2025-06-01
   ```

5. **Import candle data for BTC/USDT**
   ```bash
   jesse import-candles 'Binance Perpetual Futures' 'BTC-USDT' '2024-01-01'
   ```

**Deliverable:** Jesse running with basic grid strategy, backtest producing metrics

**Note:** binance-bot stays untouched. All new code goes into `jesse-bot/`.

---

### Sprint M2: Grid Logic Refinement (2-3 days)

**Goal:** Full grid trading logic working within Jesse's Strategy lifecycle

**Tasks:**

1. **Implement complete grid state machine in Jesse**
   - Grid initialization with dynamic bounds
   - Level fill → opposite level creation
   - Maximum grid levels cap (fix existing bug)
   - Bidirectional grid (long + short) with trend detection

2. **Per-level TP/SL using Jesse's native system**
   ```python
   def go_long(self):
       qty = utils.size_to_qty(...)
       self.buy = qty, level_price  # limit order below market
       # ATR-based TP/SL — Jesse handles execution automatically
       atr = ta.atr(self.candles, 14)
       self.take_profit = qty, level_price + atr * self.hp['tp_atr_mult']
       self.stop_loss = qty, level_price - atr * self.hp['sl_atr_mult']
   ```

3. **Trailing stop via `update_position()`**
   ```python
   def update_position(self):
       # Jesse calls this every candle when position is open
       if self.position.pnl_percentage > self.hp['trailing_activation_pct']:
           new_sl = self.price - ta.atr(self.candles, 14) * self.hp['trail_mult']
           # Only tighten, never loosen
           if self.is_long and new_sl > self.stop_loss[0][1]:
               self.stop_loss = self.position.qty, new_sl
   ```

4. **Multi-timeframe data access**
   ```python
   def should_long(self):
       # Use 4h timeframe for trend, 1h for entry
       sma_4h = ta.sma(self.get_candles(self.exchange, self.symbol, '4h'), 50)
       sma_1h = ta.sma(self.candles, 20)
       # Only long when 4h trend is up
       if sma_1h > sma_4h:
           return self._check_grid_buy_signal()
       return False
   ```
   Requires adding `('Binance Perpetual Futures', 'BTC-USDT', '4h')` to `routes.py` as data route.

5. **Comprehensive backtest validation**
   - Compare results with our current backtest engine (same data, same parameters)
   - Verify trade count, PnL, drawdown are comparable
   - Document any differences

**Deliverable:** Grid strategy fully functional in Jesse with TP/SL/trailing/multi-TF

**What dies:**
- `shared/risk/tp_sl.py` (Jesse handles TP/SL natively)
- `shared/risk/trailing_stop.py` (Jesse `update_position()`)
- `shared/risk/break_even.py` (Jesse `update_position()`)
- `shared/risk/stop_loss.py` (Jesse `self.stop_loss`)
- `binance-bot/src/binance_bot/strategies/grid.py` (rewritten as Jesse strategy)
- `binance-bot/src/binance_bot/strategies/base.py` (replaced by Jesse Strategy)

---

### Sprint M3: AI Layer Integration (3-4 days)

**Goal:** Our AI agent (LangChain + LLM) integrated into Jesse strategy lifecycle

**Tasks:**

1. **Create AI mixin for Jesse strategies**
   ```python
   # enhancements/ai/strategy_mixin.py

   import asyncio
   from enhancements.ai.agent import TradingAgent
   from enhancements.sentiment.analyzer import SentimentAnalyzer
   from enhancements.factors.calculator import FactorCalculator

   class AIStrategyMixin:
       """Mixin that adds AI capabilities to any Jesse Strategy."""

       def _init_ai(self):
           """Call from strategy __init__ or first before()."""
           self._ai_agent = TradingAgent()
           self._sentiment = SentimentAnalyzer()
           self._factors = FactorCalculator()
           self._ai_context = {}
           self._last_ai_review = 0
           self._ai_decision = 'CONTINUE'  # CONTINUE/PAUSE/ADJUST/STOP

       def _ai_before(self):
           """Call from strategy.before() — runs every candle."""
           # Factor analysis (cheap, runs every candle)
           self._ai_context['factors'] = self._factors.calculate(
               prices=self.candles[:, 2],  # close prices
               volumes=self.candles[:, 5],
           )

           # AI review (expensive, runs periodically)
           review_interval = self.hp.get('review_interval', 15)
           candles_since_review = self.index - self._last_ai_review
           if candles_since_review >= review_interval:
               self._run_ai_review()
               self._last_ai_review = self.index

       def _run_ai_review(self):
           """Periodic AI analysis via LLM."""
           indicators = {
               'rsi': ta.rsi(self.candles, 14),
               'sma_20': ta.sma(self.candles, 20),
               'ema_50': ta.ema(self.candles, 50),
               'macd': ta.macd(self.candles),
               'bb': ta.bollinger_bands(self.candles, 20),
               'atr': ta.atr(self.candles, 14),
               'adx': ta.adx(self.candles, 14),
           }

           # Sync wrapper for async LLM call
           review = asyncio.get_event_loop().run_until_complete(
               self._ai_agent.periodic_review(
                   current_price=self.price,
                   indicators=indicators,
                   factors=self._ai_context.get('factors'),
                   sentiment=self._ai_context.get('sentiment'),
                   position=self.position.to_dict if self.position.is_open else None,
               )
           )

           self._ai_decision = review.get('action', 'CONTINUE')

           # If AI says ADJUST, update grid parameters
           if self._ai_decision == 'ADJUST' and 'params' in review:
               for key, value in review['params'].items():
                   if key in self.hp:
                       self.hp[key] = value

       def _ai_should_trade(self) -> bool:
           """Filter: only trade if AI allows."""
           return self._ai_decision in ('CONTINUE', 'ADJUST')

       def _ai_confidence_filter(self) -> bool:
           """Filter: check AI confidence score."""
           return self._ai_context.get('confidence', 100) >= self.hp.get('min_confidence', 50)
   ```

2. **Integrate mixin into grid strategy**
   ```python
   class AIGridStrategy(Strategy, AIStrategyMixin):
       def before(self):
           if not hasattr(self, '_ai_agent'):
               self._init_ai()
           self._ai_before()

       def filters(self):
           return [
               self._filter_volatility,
               self._ai_should_trade,        # AI gate
               self._ai_confidence_filter,    # Confidence gate
           ]
   ```

3. **Port `shared/ai/agent.py` → `enhancements/ai/agent.py`**
   - Preserve all prompt templates
   - Adapt input format (Jesse indicators → our prompt format)
   - Add timeout (30s) for LLM calls
   - Use structured output (JSON mode) instead of string parsing

4. **Port `shared/ai/prompts.py` → `enhancements/ai/prompts.py`**
   - Update prompts to match Jesse's indicator names

5. **Test AI integration**
   - Backtest with AI enabled vs disabled
   - Verify AI review doesn't block backtest speed
   - For backtesting, mock LLM calls with recorded responses

**Deliverable:** AI agent making real-time trading decisions within Jesse strategy lifecycle

**What dies:**
- `binance-bot/src/binance_bot/strategies/ai_grid.py` (logic merged into Jesse strategy + mixin)
- `shared/ai/agent.py` (moved to `enhancements/ai/agent.py`)
- `shared/ai/prompts.py` (moved to `enhancements/ai/prompts.py`)

---

### Sprint M4: Sentiment + Factors Integration (2-3 days)

**Goal:** News sentiment and factor analysis feeding into AI decisions

**Tasks:**

1. **Port sentiment pipeline to `enhancements/sentiment/`**
   - `news_fetcher.py` — keep as-is (CryptoCompare + CoinGecko)
   - `vector_store.py` — keep as-is (ChromaDB)
   - `embeddings.py` — keep as-is (Ollama)
   - `analyzer.py` — refactor to work standalone (no dependency on bot.py)

2. **Port factor analysis to `enhancements/factors/`**
   - `calculator.py` — adapt to work with Jesse's candle arrays (numpy, not pandas)
   - `regime.py` — market regime detection → feeds into strategy's `should_long()`

3. **Add sentiment to AI mixin's `before()` hook**
   ```python
   def _ai_before(self):
       # Sentiment fetch (every 15 candles to avoid spam)
       if self.index % 15 == 0:
           articles = asyncio.run(self._news_fetcher.fetch_all())
           if articles:
               self._ai_context['sentiment'] = self._sentiment.analyze(articles)

       # Factor analysis (every candle, it's fast)
       self._ai_context['factors'] = self._factors.calculate(self.candles)
   ```

4. **Add factor-based filters**
   ```python
   def filters(self):
       return [
           self._filter_volatility,
           self._filter_market_regime,  # NEW: factor-based
           self._ai_should_trade,
       ]

   def _filter_market_regime(self) -> bool:
       """Only trade in grid-suitable regimes (ranging/mild trending)."""
       regime = self._ai_context.get('factors', {}).get('regime', 'unknown')
       return regime in ('ranging', 'mild_uptrend', 'mild_downtrend')
   ```

5. **Test sentiment pipeline end-to-end**
   - Verify Ollama embeddings work
   - Verify ChromaDB persistence
   - Verify sentiment scores feed into AI prompts

**Deliverable:** Complete data pipeline: Market Data → Factors + Sentiment → AI → Trading Decision

**What dies:**
- `shared/vector_db/` (moved to `enhancements/sentiment/`)
- `shared/factors/` (moved to `enhancements/factors/`)

---

### Sprint M5: Alerts + Dashboard Adaptation (2-3 days)

**Goal:** Our AlertManager and Streamlit dashboard working with Jesse data

**Tasks:**

1. **Keep AlertManager (ours is better)**
   - Move to `enhancements/alerts/`
   - Fix Discord retry recursion → loop with max 3 retries
   - Fix f-string crash when price=None
   - Add SMTP timeout (30s)
   - Wire Telegram (or delete it)

2. **Hook alerts into Jesse strategy**
   ```python
   def on_open_position(self, order):
       """Jesse calls this when position opens."""
       asyncio.run(self.alert_manager.send_trade_alert(
           symbol=self.symbol,
           side=order.side,
           price=order.price,
           amount=order.qty,
       ))

   def on_close_position(self, order, closed_trade):
       """Jesse calls this when position closes."""
       asyncio.run(self.alert_manager.send_trade_alert(
           symbol=self.symbol,
           side=order.side,
           price=order.price,
           amount=order.qty,
           pnl=closed_trade.pnl,
       ))
   ```

3. **Adapt Streamlit dashboard**
   - Read from Jesse's database (PostgreSQL) instead of our JSON state
   - Jesse stores trades, orders, positions in DB
   - Keep our custom charts (equity curve, grid view)
   - Add Jesse metrics display (30+ metrics)

4. **Alert rules engine**
   - Keep our rules engine for custom alerts (price spikes, volume, drawdown)
   - Feed with Jesse's position data

**Deliverable:** Alerts + Dashboard working with Jesse backend

**What dies:**
- `shared/alerts/` (moved to `enhancements/alerts/`, cleaned up)
- `shared/api/` (replaced by Jesse's built-in API or simplified)
- `shared/core/state.py` (Jesse manages state)
- `shared/monitoring/metrics.py` (Jesse provides metrics)

---

### Sprint M6: Live Trading Setup (2-3 days)

**Goal:** Ready for live trading on Binance with real money

**Tasks:**

1. **Configure Jesse live trading**
   ```python
   # jesse-config/live-config.py
   config = {
       'exchange': 'Binance Perpetual Futures',
       'symbol': 'BTC-USDT',
       'timeframe': '1h',
       'strategy': 'AIGridStrategy',
   }
   ```

2. **Binance API integration**
   - Jesse has built-in Binance adapter
   - Configure API keys in `.env`
   - Test with paper trading mode first (Jesse has native paper trading via exchange API)

3. **Emergency stop mechanism**
   - Port our emergency stop to work with Jesse
   - Hook into Jesse's `on_error()` or exception handlers
   - File-based kill switch (same as now)

4. **Docker deployment**
   - Jesse + PostgreSQL + our enhancements in Docker
   - Hot reload for strategy code
   - Prometheus metrics endpoint

5. **Paper trading validation (1-2 days)**
   - Run on Binance paper trading
   - Verify all alerts fire correctly
   - Verify AI reviews work in live mode
   - Monitor resource usage (memory, CPU)

6. **Go live with $50-100**
   - Switch to mainnet
   - Conservative parameters (small grid, low amounts)
   - 24/7 monitoring via alerts

**Deliverable:** Bot live on Binance mainnet with real money

**What dies:**
- `binance-bot/src/binance_bot/core/exchange.py` (Jesse handles exchange)
- `binance-bot/src/binance_bot/core/order_manager.py` (Jesse handles orders)
- `binance-bot/src/binance_bot/core/position_manager.py` (Jesse handles positions)
- `binance-bot/src/binance_bot/bot.py` (replaced by Jesse live mode + runner/bot.py)

---

### Sprint M7: Cleanup + Optimization (2-3 days)

**Goal:** Remove dead code, optimize, document

**Tasks:**

1. **Delete all replaced modules**
   - Remove `binance-bot/src/` entirely (replaced by Jesse strategy)
   - Remove `shared/` entirely (replaced by Jesse + enhancements/)
   - Remove old Docker configs
   - Remove unused dependencies

2. **Update AGENTS.md**
   - New structure documentation
   - New bug list (should be much shorter)
   - New sprint history

3. **Walk-forward optimization**
   - Adapt our walk-forward concept to Jesse's optimization mode
   - Or implement as a wrapper around `jesse optimize`

4. **Performance testing**
   - Backtest speed comparison (our engine vs Jesse)
   - Memory usage in live mode
   - LLM call latency impact

5. **Create CHANGELOG.md** with complete migration history

**Deliverable:** Clean, documented, optimized codebase

---

## Migration Map: Old Module → New Location

| Old Path | New Path | Action |
|----------|----------|--------|
| `binance-bot/src/binance_bot/bot.py` | `runner/bot.py` | Rewrite as Jesse orchestrator |
| `binance-bot/src/binance_bot/strategies/grid.py` | `jesse-config/strategies/AIGridStrategy/__init__.py` | Rewrite as Jesse Strategy |
| `binance-bot/src/binance_bot/strategies/ai_grid.py` | `enhancements/ai/strategy_mixin.py` | Refactor into mixin |
| `binance-bot/src/binance_bot/strategies/base.py` | — | **DELETE** (Jesse provides) |
| `binance-bot/src/binance_bot/core/exchange.py` | — | **DELETE** (Jesse provides) |
| `binance-bot/src/binance_bot/core/order_manager.py` | — | **DELETE** (Jesse provides) |
| `binance-bot/src/binance_bot/core/position_manager.py` | — | **DELETE** (Jesse provides) |
| `binance-bot/src/binance_bot/core/emergency.py` | `enhancements/emergency/stop.py` | Move |
| `binance-bot/src/binance_bot/core/data_collector.py` | — | **DELETE** (Jesse handles) |
| `shared/ai/agent.py` | `enhancements/ai/agent.py` | Move + refactor |
| `shared/ai/prompts.py` | `enhancements/ai/prompts.py` | Move |
| `shared/alerts/manager.py` | `enhancements/alerts/manager.py` | Move + fix bugs |
| `shared/alerts/discord.py` | `enhancements/alerts/discord.py` | Move + fix recursion |
| `shared/alerts/email.py` | `enhancements/alerts/email.py` | Move + add timeout |
| `shared/alerts/telegram.py` | `enhancements/alerts/telegram.py` | Move + wire in (or delete) |
| `shared/alerts/rules.py` | `enhancements/alerts/rules.py` | Move |
| `shared/backtest/engine.py` | — | **DELETE** (Jesse provides) |
| `shared/backtest/benchmark.py` | — | **DELETE** (Jesse provides) |
| `shared/backtest/charts.py` | — | **DELETE** (Jesse provides) |
| `shared/core/indicators.py` | — | **DELETE** (Jesse provides 170+) |
| `shared/core/database.py` | — | **DELETE** (Jesse uses PostgreSQL) |
| `shared/core/state.py` | — | **DELETE** (Jesse manages state) |
| `shared/config/settings.py` | `jesse-config/config.py` + `.env` | Merge into Jesse config |
| `shared/risk/position_sizer.py` | — | **DELETE** (Jesse `utils.size_to_qty`) |
| `shared/risk/limits.py` | `enhancements/alerts/rules.py` | Merge into alert rules |
| `shared/risk/metrics.py` | — | **DELETE** (Jesse metrics) |
| `shared/risk/stop_loss.py` | — | **DELETE** (Jesse `self.stop_loss`) |
| `shared/risk/tp_sl.py` | — | **DELETE** (Jesse native) |
| `shared/risk/trailing_stop.py` | — | **DELETE** (Jesse `update_position`) |
| `shared/risk/break_even.py` | — | **DELETE** (Jesse `update_position`) |
| `shared/optimization/optimizer.py` | — | **DELETE** (Jesse `optimize` mode) |
| `shared/optimization/walk_forward.py` | `enhancements/optimization/walk_forward.py` | Keep concept, adapt |
| `shared/optimization/metrics.py` | — | **DELETE** (Jesse metrics) |
| `shared/factors/factor_calculator.py` | `enhancements/factors/calculator.py` | Move |
| `shared/factors/factor_strategy.py` | `enhancements/factors/regime.py` | Move + rename |
| `shared/vector_db/news_fetcher.py` | `enhancements/sentiment/news_fetcher.py` | Move |
| `shared/vector_db/vector_store.py` | `enhancements/sentiment/vector_store.py` | Move |
| `shared/vector_db/embeddings.py` | `enhancements/sentiment/embeddings.py` | Move |
| `shared/vector_db/sentiment.py` | `enhancements/sentiment/analyzer.py` | Move + rename |
| `shared/monitoring/metrics.py` | — | **DELETE** (Jesse metrics) |
| `shared/api/main.py` | — | **DELETE** (Jesse API or simplified) |
| `shared/api/routes/` | — | **DELETE** |
| `shared/dashboard/app.py` | `dashboard/app.py` | Adapt for Jesse data |
| `shared/dashboard/components/` | `dashboard/components/` | Adapt |
| `shared/reports/pnl.py` | — | **DELETE** (dead code) |
| `shared/utils/logging_config.py` | — | **DELETE** (dead code) |

---

## LOC Impact Estimate

| Category | Current LOC | After Migration | Change |
|----------|-------------|-----------------|--------|
| Strategy + Bot | ~2,500 | ~500 | -2,000 |
| Backtesting | ~700 | 0 | -700 |
| Indicators | ~200 | 0 | -200 |
| Optimization | ~400 | ~100 | -300 |
| Risk Management | ~800 | ~50 | -750 |
| Exchange/Orders | ~600 | 0 | -600 |
| AI Layer | ~500 | ~500 | 0 |
| Sentiment | ~400 | ~400 | 0 |
| Factors | ~300 | ~300 | 0 |
| Alerts | ~600 | ~600 | 0 |
| Dashboard | ~500 | ~400 | -100 |
| API | ~400 | 0 | -400 |
| Config/Utils | ~300 | ~100 | -200 |
| Runner/Docker | ~200 | ~300 | +100 |
| **Total** | **~8,400** (active) | **~3,250** | **-5,150 (-61%)** |

We go from 14,270 total LOC (with dead code) to ~3,250 LOC of OUR code + Jesse framework underneath. **61% reduction** in code we maintain.

---

## Timeline

| Sprint | Duration | Cumulative |
|--------|----------|------------|
| M1: Jesse Foundation | 3-4 days | Week 1 |
| M2: Grid Logic | 2-3 days | Week 1-2 |
| M3: AI Integration | 3-4 days | Week 2 |
| M4: Sentiment + Factors | 2-3 days | Week 2-3 |
| M5: Alerts + Dashboard | 2-3 days | Week 3 |
| M6: Live Trading | 2-3 days | Week 3-4 |
| M7: Cleanup | 2-3 days | Week 4 |

**Total: ~4 weeks to complete migration + go live with real money.**

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Jesse doesn't support our grid pattern well | HIGH | Sprint M1 validates this early. Grid is unconventional for Jesse (which expects should_long/short one-position patterns). May need creative use of `update_position()` for multi-level grid. |
| Jesse's live mode requires PostgreSQL | MEDIUM | Add PostgreSQL to Docker stack. Jesse can use SQLite for backtests. |
| Async AI calls in Jesse's sync strategy loop | MEDIUM | Use `asyncio.run()` wrapper or run AI in background thread with result queue. |
| Jesse version updates break our strategy | LOW | Pin Jesse version. Test before upgrading. |
| Performance: AI calls slow down backtest | MEDIUM | Mock LLM calls during backtest (cached responses or skip AI). |
| Migration breaks existing tests | MEDIUM | Rewrite tests against Jesse strategy. Our AI/sentiment tests stay as-is. |

### Critical Risk: Grid Strategy Fit

Jesse's Strategy pattern assumes one position at a time (long OR short). Grid trading opens MULTIPLE positions across price levels. This is the **biggest technical challenge** of the migration.

**Potential solutions:**
1. **Multiple routes:** Run N instances of the strategy at different price levels
2. **Custom position management:** Use `update_position()` to manage grid as a single macro-position
3. **Hybrid:** Use Jesse for entry/exit decisions but manage individual grid levels ourselves via `self.vars`
4. **jesse-live plugin:** Jesse's live mode allows more flexible order management

**Recommendation:** Option 3 (hybrid) — use Jesse for lifecycle/exchange/metrics but manage grid levels in `self.vars`. This preserves Jesse's benefits without fighting its one-position pattern.

---

## Dependencies

**New:**
- `jesse>=1.13.0`
- `psycopg2-binary` (PostgreSQL for Jesse live mode)

**Keep:**
- `langchain`, `langchain-openai` (AI layer)
- `chromadb` (vector store)
- `aiohttp` (news fetching)
- `loguru` (logging — Jesse also uses it)
- `streamlit` (dashboard)
- `plotly` (charts)
- `python-dotenv` (env vars)
- `aiosmtplib` (email alerts)

**Remove:**
- `ccxt` (Jesse handles exchange)
- `sqlalchemy` (Jesse uses its own ORM)
- `ta` (already unused)
- `aiosqlite` (already unused)
- `prometheus-client` (Jesse has metrics)
- `fastapi`, `uvicorn` (replaced by Jesse API or simplified)

---

*Plan created by Karax — 2026-03-07*
*To be executed incrementally, sprint by sprint, with validation at each step.*
