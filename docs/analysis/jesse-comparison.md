# Jesse Framework vs Our Implementation — Deep Analysis

**Date:** 2026-03-07  
**Context:** Sprints 17-23 were inspired by Jesse framework patterns instead of the originally planned NautilusTrader migration.  
**Question:** Did we extract the right things from Jesse? Are we reinventing the wheel?

---

## 1. What We Took from Jesse (and How Well)

### 1.1 Strategy Architecture

**Jesse's approach:**
- Abstract base class `Strategy` with lifecycle hooks: `should_long()`, `go_long()`, `should_short()`, `go_short()`, `should_cancel_entry()`, `update_position()`
- Declarative order syntax: `self.buy = qty, price`, `self.take_profit = qty, price`, `self.stop_loss = qty, price`
- Internal broker handles order type selection (market/limit/stop) automatically
- Position model with built-in PnL, ROI, liquidation price calculation

**Our approach:**
- `BaseStrategy` → `GridStrategy` → `AIGridStrategy` inheritance
- Signal-based: `calculate_signals()` returns `Signal` objects
- Manual paper trade execution: `execute_paper_trade(signal)`
- Separate `GridLevel` dataclass for order tracking

**Assessment: 5/10 — Partially adopted**

We took the class hierarchy idea but not the elegant parts. Jesse's strategy pattern is declarative — you say *what* you want, the framework figures out *how*. Our strategy is imperative — we manually manage signals, fills, and order state. This means:
- More code in our strategies
- More bugs possible (we have the unbounded grid growth issue)
- Harder to write new strategies (no reusable lifecycle hooks)

**What we missed:**
- Declarative TP/SL/entry syntax (Jesse's `self.stop_loss = qty, price` is beautiful)
- Automatic order type selection (Broker class)
- Position lifecycle management (open/close/partial fill tracking)

We did add TP/SL calculation (Sprint 21: `tp_sl.py`, `trailing_stop.py`, `break_even.py`) — but these are *calculators* not an *execution framework*. They compute prices, they don't manage orders.

---

### 1.2 Backtesting Engine

**Jesse's approach:**
- Event-driven simulation with candle-by-candle replay
- Anti look-ahead bias by design (warmup candles separated from test data)
- Multi-timeframe + multi-symbol simultaneous backtesting
- Debug mode with detailed order/fill logs
- Automatic chart generation (TradingView format export)
- Benchmark mode for batch comparisons

**Our approach (Sprint 19):**
- `BacktestEngine` with chronological data access
- Anti look-ahead bias (strategy sees only data up to current candle)
- Orders fill at next candle open (not current close)
- Commission + slippage simulation
- `BacktestResult` dataclass with 20+ metrics
- `StrategyBenchmark` class for side-by-side comparison
- `BacktestCharts` with Plotly visualization (equity curve, drawdown, trade scatter, monthly heatmap)

**Assessment: 7/10 — Good adoption**

This is one of our stronger areas. The core mechanics are similar — candle-by-candle replay with proper fill simulation. We correctly:
- Fill at next candle open (not current close)
- Apply slippage and commission
- Calculate professional metrics (Sharpe, Sortino, profit factor, etc.)
- Prevent look-ahead bias

**What we missed:**
- Multi-timeframe/multi-symbol backtesting (Jesse can test strategies across multiple pairs simultaneously)
- Warmup candle handling (Jesse explicitly separates warmup data from test data to avoid indicator initialization bias)
- TradingView-compatible chart export
- Saved backtest sessions for later review (Jesse stores in DB)

---

### 1.3 Performance Metrics

**Jesse's approach:**
- 30+ metrics including: Sharpe, Sortino, Calmar, Omega ratio, Serenity Index, CAGR, max drawdown, max underwater period, win rate (long/short separate), expectancy, profit factor
- Daily return series as foundation
- Uses 365 periods for crypto (not 252 for stocks)
- Streak tracking (winning/losing streaks)
- Safe value conversion (handles NaN, inf gracefully)

**Our approach:**
- Sprint 19 `BacktestResult`: Sharpe, Sortino, max drawdown, win rate, profit factor, expectancy, avg win/loss, largest win/loss, avg holding period
- Sprint 18 `optimization/metrics.py`: Sharpe, Sortino, Calmar, max drawdown, CAGR, win rate
- `shared/risk/metrics.py`: Sharpe, Sortino, Calmar (runtime)

**Assessment: 6/10 — Adequate but scattered**

We have the essential metrics but they're implemented in THREE different places with different interfaces:
1. `BacktestResult` — backtest metrics
2. `optimization/metrics.py` — optimization objective metrics
3. `shared/risk/metrics.py` — runtime risk tracking

Jesse has ONE unified `metrics.py` service. Our duplication creates maintenance burden and inconsistency risk (e.g., our Sortino returns `float('inf')` — Jesse handles this with `np.inf`/`-np.inf` and wraps in `pd.Series`).

**What we missed:**
- Omega ratio, Serenity Index
- Separate long/short win rates
- Winning/losing streak tracking
- Max underwater period
- Unified metric service across backtest/live

---

### 1.4 Optimization (Hyperparameter Tuning)

**Jesse's approach:**
- Optuna-based optimization
- Simple `hyperparameters()` method on strategy: define name, type, min, max, default
- Cross-validation
- UI integration (dashboard shows results)

**Our approach (Sprint 18):**
- `GridOptimizer` with Optuna
- `WalkForwardOptimizer` for overfitting prevention
- Hardcoded search space in `define_search_space()` method
- Results saved to JSON
- Best params auto-loadable by bot

**Assessment: 7/10 — Good, with a notable advantage**

Walk-forward optimization is actually something we have that Jesse doesn't out of the box (Jesse has it in their paid dashboard, not in the open-source core). This is genuinely valuable for avoiding overfitting.

However, Jesse's approach to defining the search space is more elegant — it's part of the strategy class itself (`hyperparameters()` method), so any strategy automatically becomes optimizable. In our case, the search space is hardcoded in `GridOptimizer`, meaning adding a new strategy requires modifying the optimizer.

---

### 1.5 Indicators

**Jesse's approach:**
- **170+ indicators** as individual functions: `ta.ema(candles, period)`
- Each indicator is a separate file with clear interface
- Candle arrays as input (numpy)
- Computed values cached for performance

**Our approach:**
- 6 indicators in `shared/core/indicators.py`: RSI, SMA, EMA, Bollinger Bands, MACD, ATR
- Class-based `Indicators` with `add_all_indicators()` method
- DataFrame-based (pandas)
- No caching

**Assessment: 3/10 — Minimal**

This is our weakest area. 6 vs 170+ indicators. For a grid strategy this is *currently* sufficient (grid trading doesn't need 170 indicators), but it severely limits future strategy development. If we want to build strategies beyond grid trading, we'll need many more indicators.

We also removed the `ta` library dependency (it was unused), which could have provided ~130 indicators out of the box.

---

### 1.6 Alerts / Notifications

**Jesse's approach:**
- Telegram, Slack, Discord support
- Simple `notifier.notify()` API within strategies
- Error reporting to notification channels

**Our approach:**
- AlertManager with Discord (primary) + Email (secondary)
- Rate limiting, per-type dedup
- Daily summary scheduler
- Alert rules engine (price/volume/PnL thresholds)
- Trade, status, error alerts

**Assessment: 8/10 — Our advantage**

Our alert system is actually MORE sophisticated than Jesse's. The AlertManager with rate limiting, dedup, and a rules engine goes beyond what Jesse offers. The daily summary scheduler is a nice touch.

The irony: Telegram alerter is fully implemented but disconnected.

---

### 1.7 Risk Management

**Jesse's approach:**
- Built into strategy: `self.stop_loss`, `self.take_profit`, `self.position`
- Leverage and margin tracking (Position model)
- Liquidation price calculation
- `utils.size_to_qty()` for position sizing

**Our approach:**
- Separate risk modules: PositionSizer, RiskLimits, RiskMetrics, StopLossManager
- TP/SL calculator (fixed %, ATR-based, R:R ratio)
- Trailing stop manager
- Break-even manager
- Kelly criterion, fixed %, ATR-based sizing methods
- Daily loss limits, max drawdown, consecutive loss limits

**Assessment: 7/10 — Feature-rich but disconnected**

On paper, our risk management is comprehensive — arguably more granular than Jesse's. The problem (as noted in AUDIT.md): several components aren't wired in:
- StopLossManager: instantiated, never called
- Trailing stop and break-even: imported in grid.py but integration quality unverified

Jesse's approach wins on integration — risk is built INTO the strategy lifecycle, not bolted on. When you say `self.stop_loss = qty, price`, Jesse guarantees it executes. Our calculators require manual wiring.

---

### 1.8 Exchange Connectivity

**Jesse's approach:**
- Direct exchange adapters (Binance, Bybit, etc.)
- Spot + futures support with automatic position mode handling
- Paper trading + live trading seamless switch
- Exchange-specific precision handling (min qty, min notional)
- WebSocket-based live data

**Our approach:**
- CCXT wrapper (`exchange.py`)
- Binance testnet only
- Paper trading only (no real order submission)
- No precision handling
- REST polling (no WebSocket)

**Assessment: 4/10 — Minimal**

We're using CCXT which is fine as an abstraction, but we haven't built the precision layer (min order sizes, tick sizes, rounding) that's essential for live trading. Jesse handles all of this automatically.

Our paper trading is simulated within the bot — Jesse's paper trading goes through the actual exchange API in simulation mode, which is more realistic.

---

## 2. Sprint-by-Sprint Quality Assessment

### Sprints Inspired by Jesse (17-23)

| Sprint | Feature | Jesse Equivalent | Our Quality | Notes |
|--------|---------|-----------------|-------------|-------|
| 17 | Skipped (was NautilusTrader study) | — | — | Redirected to Jesse-inspired sprints |
| 18 | Optuna Optimization | `modes/optimization_mode.py` | **8/10** | Walk-forward is our advantage. Search space coupling is a weakness. |
| 19 | Advanced Backtesting | `modes/backtest_mode.py` | **7/10** | Solid core. Missing multi-timeframe and warmup handling. |
| 20 | Bidirectional Grid | Strategy `should_short()` | **7/10** | Direction detection + short grids work. Grid growth unbounded. |
| 21 | Per-level TP/SL | `self.stop_loss`, `self.take_profit` | **6/10** | Calculators exist but integration into grid loop needs verification. |
| 22 | Backtest Charts | Jesse's charts service | **7/10** | Plotly charts: equity, drawdown, trade scatter, monthly heatmap. Good. |
| 23 | Walk-Forward Benchmark | Jesse's benchmark mode | **7/10** | `StrategyBenchmark` + `WalkForwardOptimizer`. Functional. |

**Overall assessment of Jesse adoption: 6.5/10**

We extracted the right *ideas* but not always the right *patterns*. The features work individually but lack the cohesion that makes Jesse effective as a framework.

---

## 3. The Big Question: Are We Reinventing the Wheel?

### Short Answer: Yes, partially.

### Long Answer:

**What we've built (14,270 LOC):**
- Custom backtesting engine
- Custom optimization framework
- Custom risk management
- Custom indicator calculations
- Custom alert system
- Custom dashboard
- Custom API
- Custom AI integration (unique to us)
- Custom news sentiment pipeline (unique to us)

**What Jesse provides out-of-the-box:**
- Backtesting engine (battle-tested, ~5 years of community use)
- Optimization with Optuna integration
- 170+ indicators
- Risk management built into strategy lifecycle
- Multi-exchange support (Binance, Bybit, etc.)
- Multi-timeframe/multi-symbol
- Paper trading + live trading
- Dashboard UI (jesse-ui project)
- Active community + documentation

**What Jesse does NOT have:**
- LLM/AI-powered analysis and decisions
- News sentiment analysis with vector DB
- Grid-specific strategy (though it can be implemented as a Strategy subclass)
- Factor analysis
- Multi-bot monorepo architecture

### The Cost Analysis

**Building ourselves:**
- ~3 weeks of development (Sprints 1-23)
- 14,270 LOC to maintain
- Bugs to find and fix (16+ known issues)
- Testing to write (255 tests but gaps remain)
- Exchange precision handling still missing
- Paper trading only — no path to live without significant work

**Using Jesse as foundation:**
- ~1 week to set up + implement grid strategy as Jesse Strategy subclass
- Our unique features (AI, sentiment, factors) bolt on as *enhancements* to Jesse strategies
- Backtesting, optimization, indicators, exchange handling all free
- Live trading ready out of the box
- Community support for bugs
- But: learning curve, dependency on Jesse's development, potential limitations for unusual strategies

### Where Jesse Would Save Us

| Our Problem | Jesse Solution |
|------------|---------------|
| No live trading path | Built-in live mode with exchange adapters |
| 6 indicators | 170+ indicators |
| Exchange precision missing | Automatic precision handling |
| Metrics scattered in 3 places | Unified metrics service |
| StopLoss not wired | TP/SL built into strategy lifecycle |
| Float precision for money | Proper handling |
| No multi-timeframe | Native multi-timeframe support |
| No WebSocket | WebSocket live data |

### Where Jesse Would NOT Help

| Our Unique Feature | Status |
|-------------------|--------|
| AI/LLM analysis | Must build ourselves (can hook into Jesse's `before()` or `after()` methods) |
| News sentiment + vector DB | Must build ourselves (can run as data pipeline feeding into strategy) |
| Factor analysis | Must build ourselves (Jesse `before()` hook) |
| Discord alerts with rate limiting | Must build ourselves (Jesse has basic Telegram/Discord) |
| Dashboard (Streamlit) | Jesse has its own UI, but ours is more customized |
| Monorepo for multiple bots | Jesse strategies are modular by nature |

---

## 4. Options Going Forward

### Option A: Continue Custom (Current Path)

**Effort to production-ready:** 3-5 sprints
- Fix P0 bugs (1 sprint)
- Implement exchange precision + live order submission (1-2 sprints)
- WebSocket data feed (1 sprint)
- Production hardening + testing (1 sprint)

**Pros:**
- No migration cost
- Full control
- AI integration already working
- Sunk cost already invested

**Cons:**
- Maintaining 14K LOC forever
- Every new feature is custom work
- Exchange adapters are complex (Binance alone has dozens of edge cases)
- Community of one (us)

**Risk:** Medium-high. Live trading with a custom engine is risky — financial bugs can cost real money.

### Option B: Migrate to Jesse

**Effort:** 2-3 sprints
- Sprint 1: Jesse setup + grid strategy as Jesse Strategy subclass
- Sprint 2: Port AI layer as strategy hooks (before/after/update_position)
- Sprint 3: Port news sentiment, factor analysis, custom alerts

**Pros:**
- Battle-tested backtesting and live trading
- 170+ indicators free
- Exchange precision handling free
- Live trading free
- Community support
- Faster path to mainnet

**Cons:**
- Migration effort (rewrite grid strategy)
- Dependency on Jesse project (4.8K stars, active, but single maintainer)
- Jesse is crypto-only (no stocks/forex if we want later)
- Some of our UI (Streamlit dashboard) needs adapting
- Learning curve

**Risk:** Low-medium. Jesse is proven in production by many users.

### Option C: Hybrid — Jesse Core + Our Enhancements

**Effort:** 3-4 sprints
- Sprint 1: Jesse as strategy framework (replace our backtest, indicators, exchange, metrics)
- Sprint 2: Keep `shared/ai/`, `shared/vector_db/`, `shared/factors/` as standalone modules that feed context into Jesse strategies
- Sprint 3: Keep our AlertManager (it's better than Jesse's), wrap Jesse's metrics
- Sprint 4: Adapt dashboard to read from Jesse's data

**Pros:**
- Best of both worlds
- Our unique AI features preserved
- Jesse handles the hard parts (exchange, backtesting, live trading)
- We focus on what makes us different (AI-powered trading)

**Cons:**
- Integration complexity (Jesse has its own data store, we have ours)
- Two systems to understand
- Potential version conflicts

**Risk:** Medium. Integration can be tricky.

### Option D: Stay Custom But Adopt Jesse's Patterns

**Effort:** 2-3 sprints
- Sprint 1: Refactor strategy to declarative pattern (TP/SL as properties, not manual wiring)
- Sprint 2: Unify metrics service, add indicator library (use `ta-lib` or `pandas-ta`)
- Sprint 3: Add exchange precision layer, WebSocket feeds

**Pros:**
- No migration (evolutionary improvement)
- Learn from Jesse without depending on it
- Keep full control and our custom features
- Gradually improve quality

**Cons:**
- Still maintaining all the code ourselves
- Still custom exchange handling (risky for live trading)
- Slower than just using Jesse

**Risk:** Medium. Better code, still custom.

---

## 5. Recommendation

**For getting to live trading fastest:** Option B (Jesse migration)

**For keeping our unique AI advantage while reducing risk:** Option C (Hybrid)

**For minimal disruption:** Option D (Adopt patterns, stay custom)

### My Recommendation: Option C (Hybrid)

**Reasoning:**

1. **The hard parts of trading bot development are exchange connectivity, order management, and backtesting accuracy.** Jesse handles all of these. We shouldn't spend months reimplementing what exists.

2. **Our competitive advantage is the AI layer.** Nobody else is doing LLM-powered grid optimization with news sentiment analysis. This is what makes our bot different from the thousands of grid bots out there.

3. **Jesse is mature and active.** The project has been around ~5 years, has 4.8K GitHub stars, and active development. It's not going away.

4. **The migration cost is bounded.** Our grid strategy logic (~900 lines) needs rewriting as a Jesse Strategy subclass. Our AI, sentiment, and factor modules (~1500 lines total) can remain mostly unchanged.

5. **Live trading readiness.** Jesse can go live on Binance immediately. Our custom engine cannot.

### Estimated savings with Hybrid approach:

| Module | Keep Ours | Use Jesse | LOC Saved |
|--------|-----------|-----------|-----------|
| Backtesting engine | | ✅ | ~700 |
| Optimization | | ✅ (partially) | ~300 |
| Indicators | | ✅ | ~200 + access to 170 more |
| Exchange client | | ✅ | ~400 |
| Metrics | | ✅ | ~300 |
| Strategy lifecycle | | ✅ | ~200 |
| AI layer | ✅ | | 0 |
| News sentiment | ✅ | | 0 |
| Factor analysis | ✅ | | 0 |
| Alerts | ✅ | | 0 |
| Dashboard | ✅ (adapted) | | 0 |
| **Total** | | | **~2,100 LOC** |

That's ~15% of our codebase replaced with battle-tested code, and we gain live trading capability for free.

---

## 6. What Jesse Community Thinks

Based on Jesse's positioning:
- They explicitly focus on **strategy research** (backtesting + optimization) as the primary use case
- Live trading is their premium/advanced feature
- The framework is designed for **strategy developers** — people who want to test ideas fast
- Their GPT integration (JesseGPT) shows they're thinking about AI too, but at the strategy-writing level, not at the trading-decision level like we're doing

Our AI approach is fundamentally different from JesseGPT — Jesse uses AI to *write strategy code*, we use AI to *make real-time trading decisions*. These are complementary, not competing.

---

## Summary Table

| Aspect | Jesse | Our Bot | Winner |
|--------|-------|---------|--------|
| Strategy framework | Declarative, elegant | Imperative, verbose | Jesse |
| Backtesting | Battle-tested, multi-TF | Solid, single-TF | Jesse |
| Optimization | Optuna, basic | Optuna + walk-forward | **Ours** |
| Indicators | 170+ | 6 | Jesse |
| Risk management | Built-in lifecycle | Feature-rich but disconnected | Jesse (integration) |
| Exchange handling | Multi-exchange, precision | CCXT basic, no precision | Jesse |
| Live trading | Ready | Not ready | Jesse |
| AI/LLM decisions | None (JesseGPT writes code) | Real-time AI analysis | **Ours** |
| News sentiment | None | Full pipeline | **Ours** |
| Alerts | Basic | Sophisticated (rate limit, rules) | **Ours** |
| Dashboard | Jesse-UI (React) | Streamlit (custom) | Tie |
| Community | 4.8K stars, active | Solo project | Jesse |

---

*Analysis by Karax — 2026-03-07*
