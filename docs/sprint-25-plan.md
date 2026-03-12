# Sprint 25: Jesse Bot Fixes — Implementation Plan

> **Date:** 2026-03-12
> **Branch:** `feature/sprint-25-jesse-fixes`
> **Source:** AUDIT_V2.md (9 Jesse issues: 3 P0, 4 P1, 2 P2)
> **Goal:** Fix all Jesse-bot bugs from Audit V2

---

## Pre-Sprint Status

Sprint 24 already fixed the 3 P0-JESSE issues. Verified against actual source:

| Issue | Status | Verification |
|-------|--------|-------------|
| P0-JESSE-1 | ✅ Fixed in Sprint 24 | `__init__.py:357,360` uses `[:, 4]` (correct close column) |
| P0-JESSE-2 | ✅ Fixed in Sprint 24 | `grid_logic.py:281` initializes `self._side: Optional[str] = None` |
| P0-JESSE-3 | ✅ Fixed in Sprint 24 | `factors_mixin.py:204` uses `loss.replace(0, np.nan)` |

Sprint 25 scope: **6 remaining issues** (4 P1 + 2 P2).

---

## Implementation Order

Issues ordered by severity and dependency:

| Phase | Issue | Severity | File | Rationale |
|-------|-------|----------|------|-----------|
| 1 | P1-JESSE-3 | **CRITICAL** | `live_trader.py` | Grid rebuild destroys all live state every hour |
| 2 | P1-JESSE-4 | P1 | `live_trader.py` | Memory leak in same file, fix together |
| 3 | P1-JESSE-1 | P1 | `grid_logic.py` | Logic bug returns wrong level price |
| 4 | P1-JESSE-2 | P1 | `factors_mixin.py` | Fragile column mapping causes silent data corruption |
| 5 | P2-JESSE-1 | P2 | `ai_mixin.py` | Hardcoded symbol, fix together with P2-JESSE-2 |
| 6 | P2-JESSE-2 | P2 | `ai_mixin.py` | Hardcoded balance, same file as P2-JESSE-1 |

---

## Phase 1: P1-JESSE-3 — Live trader rebuilds grid every iteration (CRITICAL)

**File:** `jesse-bot/live_trader.py:610`
**Method:** `LiveTrader._loop_iteration()`

```python
# Line 610 — called EVERY iteration of the main loop:
levels = self.setup_grid(price, atr, closes)
```

**Problem:** `setup_grid()` calls `self.grid.setup_grid(price, direction=direction)` which resets
`self.levels`, `self.center`, and `self.filled_levels` to empty state. This is called every hour
in `_loop_iteration()`. All partially-filled grid state, the `level_order_map`, and fill tracking
are destroyed. This defeats the entire purpose of grid trading — the bot can never profit from
grid level fills because it forgets about them every iteration.

**Root cause:** No check for whether the grid already exists or whether the trend direction changed.

**Fix:**
```python
# In _loop_iteration(), replace line 610:

# BEFORE:
levels = self.setup_grid(price, atr, closes)

# AFTER:
# Only rebuild grid when: (1) no grid exists, or (2) trend direction changed
trend = detect_trend(
    closes,
    fast_period=PARAMS["trend_sma_fast"],
    slow_period=PARAMS["trend_sma_slow"],
)
if trend == "uptrend":
    new_direction = "long_only"
elif trend == "downtrend":
    new_direction = "short_only"
else:
    new_direction = "both"

if not self.grid.levels or new_direction != self.grid.direction:
    log.info(f"Grid rebuild: direction changed {self.grid.direction} → {new_direction}")
    levels = self.setup_grid(price, atr, closes)
else:
    levels = self.grid.levels
    log.info(
        f"Grid preserved: direction={self.grid.direction}, "
        f"filled={self.grid.filled_count}/{len(levels)}"
    )
```

Also update `sync_orders()` call on line 613 — it already takes `levels` param, no change needed.

**Test:**
```python
class TestLiveTraderGridPersistence:
    """P1-JESSE-3: Grid must NOT rebuild every iteration."""

    def test_grid_preserved_when_trend_unchanged(self, live_trader, mock_exchange):
        """Grid levels persist between iterations when trend is stable."""
        # Setup initial grid
        candles = make_candles(rising=True, count=100)
        mock_exchange.fetch_ohlcv.return_value = candles

        live_trader._loop_iteration()  # first iteration — builds grid
        initial_levels = list(live_trader.grid.levels)
        initial_center = live_trader.grid.center
        assert len(initial_levels) > 0

        live_trader._loop_iteration()  # second iteration — same trend
        assert live_trader.grid.levels == initial_levels
        assert live_trader.grid.center == initial_center

    def test_grid_rebuilds_on_trend_change(self, live_trader, mock_exchange):
        """Grid rebuilds when trend direction changes."""
        # First: uptrend
        mock_exchange.fetch_ohlcv.return_value = make_candles(rising=True, count=100)
        live_trader._loop_iteration()
        old_direction = live_trader.grid.direction

        # Then: downtrend
        mock_exchange.fetch_ohlcv.return_value = make_candles(falling=True, count=100)
        live_trader._loop_iteration()
        assert live_trader.grid.direction != old_direction

    def test_filled_levels_survive_iteration(self, live_trader, mock_exchange):
        """Filled grid levels are not lost between iterations."""
        candles = make_candles(rising=True, count=100)
        mock_exchange.fetch_ohlcv.return_value = candles

        live_trader._loop_iteration()
        # Simulate a fill
        live_trader.grid.filled_levels.add("buy_1")
        for lvl in live_trader.grid.levels:
            if lvl["id"] == "buy_1":
                lvl["filled"] = True

        live_trader._loop_iteration()
        assert "buy_1" in live_trader.grid.filled_levels
```

**Risk:** Medium. This fundamentally changes how the live trader manages grid state. The bot will
now hold grid levels across iterations, which is the correct behavior but represents a significant
behavioral change. Must test on testnet before any live deployment.

---

## Phase 2: P1-JESSE-4 — `filled_order_ids` grows unboundedly

**File:** `jesse-bot/live_trader.py:390`
**Method:** `LiveTrader.check_fills()`

```python
# Line 390:
self.filled_order_ids.add(trade_id)
# This set only grows — never pruned.
```

**Problem:** Every processed trade ID is added to `filled_order_ids` but never removed. Over weeks
of continuous operation, this set accumulates thousands of entries. While not a crash risk, it
causes increasing memory usage and slower `trade_id in self.filled_order_ids` lookups (though
set lookups are O(1), the memory footprint grows without bound).

**Fix:**
```python
# In LiveTrader.__init__, replace line 207:

# BEFORE:
self.filled_order_ids: set[str] = set()

# AFTER:
from collections import deque
# Keep last 500 trade IDs — enough to cover any fetch overlap
self._filled_order_ids_deque: deque[str] = deque(maxlen=500)
self.filled_order_ids: set[str] = set()

# Add a cleanup method:
def _prune_filled_order_ids(self) -> None:
    """Keep filled_order_ids bounded to last 500 trades."""
    if len(self.filled_order_ids) > 500:
        # Keep only IDs that are in the deque (most recent 500)
        self.filled_order_ids = set(self._filled_order_ids_deque)
```

```python
# In check_fills(), update line 390:

# BEFORE:
self.filled_order_ids.add(trade_id)

# AFTER:
self.filled_order_ids.add(trade_id)
self._filled_order_ids_deque.append(trade_id)

# At the end of check_fills(), add:
self._prune_filled_order_ids()
```

**Test:**
```python
class TestFilledOrderIdsBounded:
    """P1-JESSE-4: filled_order_ids must not grow unboundedly."""

    def test_filled_ids_pruned_after_limit(self, live_trader):
        """Set is pruned when it exceeds 500 entries."""
        for i in range(600):
            trade_id = f"trade_{i}"
            live_trader.filled_order_ids.add(trade_id)
            live_trader._filled_order_ids_deque.append(trade_id)

        live_trader._prune_filled_order_ids()
        assert len(live_trader.filled_order_ids) <= 500

    def test_recent_ids_preserved_after_prune(self, live_trader):
        """Most recent trade IDs survive pruning."""
        for i in range(600):
            trade_id = f"trade_{i}"
            live_trader.filled_order_ids.add(trade_id)
            live_trader._filled_order_ids_deque.append(trade_id)

        live_trader._prune_filled_order_ids()
        # Most recent 500 should be preserved
        assert "trade_599" in live_trader.filled_order_ids
        assert "trade_100" in live_trader.filled_order_ids
        # Oldest should be pruned
        assert "trade_0" not in live_trader.filled_order_ids

    def test_no_duplicate_processing_after_prune(self, live_trader):
        """Recently processed trades are not reprocessed after pruning."""
        for i in range(600):
            live_trader.filled_order_ids.add(f"trade_{i}")
            live_trader._filled_order_ids_deque.append(f"trade_{i}")

        live_trader._prune_filled_order_ids()

        # Recent trade should still be recognized
        assert "trade_599" in live_trader.filled_order_ids
```

**Risk:** Low. The deque maxlen of 500 is conservative — `fetch_my_trades(limit=50)` only returns
50 trades per call, so 500 gives 10x buffer. Trades older than 500 fills ago are extremely unlikely
to reappear in a fresh API fetch.

---

## Phase 3: P1-JESSE-1 — `get_crossed_buy_level_price` returns wrong level

**File:** `jesse-bot/strategies/AIGridStrategy/grid_logic.py:110-115`

```python
# Lines 110-115:
def get_crossed_buy_level_price(self) -> Optional[float]:
    """Get price of most recently crossed buy level."""
    for level in self.levels:
        if level['side'] == 'buy' and level['id'] in self.filled_levels:
            return level['price']
    return None
```

**Problem:** The docstring says "most recently crossed" but the code returns the **first** filled
buy level found in `self.levels` iteration order. Since buy levels are created as
`buy_1, buy_2, buy_3, ...` where `buy_1` is highest price (closest to center), this always
returns the highest-price filled buy level — not the most recently filled one.

Same bug exists for `get_crossed_sell_level_price()` at lines 117-122.

**Impact:** In `__init__.py:270` and `:289`, the entry price for TP/SL calculations uses this
method. If multiple buy levels are filled in a single candle (fast price drop), TP/SL is
calculated from the wrong level, potentially setting stops too tight or too loose.

**Fix:**
```python
# Add a tracking field to GridManager.__init__ (after line 39):
self._last_filled_buy: Optional[str] = None
self._last_filled_sell: Optional[str] = None

# Update check_buy_signal (line 92):
# BEFORE:
level['filled'] = True
self.filled_levels.add(level['id'])
return True

# AFTER:
level['filled'] = True
self.filled_levels.add(level['id'])
self._last_filled_buy = level['id']
return True

# Update check_sell_signal (line 105):
# BEFORE:
level['filled'] = True
self.filled_levels.add(level['id'])
return True

# AFTER:
level['filled'] = True
self.filled_levels.add(level['id'])
self._last_filled_sell = level['id']
return True

# Replace get_crossed_buy_level_price (lines 110-115):
def get_crossed_buy_level_price(self) -> Optional[float]:
    """Get price of most recently crossed buy level."""
    if self._last_filled_buy is None:
        return None
    for level in self.levels:
        if level['id'] == self._last_filled_buy:
            return level['price']
    return None

# Replace get_crossed_sell_level_price (lines 117-122):
def get_crossed_sell_level_price(self) -> Optional[float]:
    """Get price of most recently crossed sell level."""
    if self._last_filled_sell is None:
        return None
    for level in self.levels:
        if level['id'] == self._last_filled_sell:
            return level['price']
    return None

# Update reset() to clear tracking (line 127):
def reset(self):
    self.levels = []
    self.center = None
    self.filled_levels = set()
    self._last_filled_buy = None
    self._last_filled_sell = None

# Update setup_grid() to clear tracking (after line 81):
self._last_filled_buy = None
self._last_filled_sell = None

# Update from_dict / to_dict for serialization:
# In to_dict():
'_last_filled_buy': self._last_filled_buy,
'_last_filled_sell': self._last_filled_sell,

# In from_dict():
gm._last_filled_buy = data.get('_last_filled_buy')
gm._last_filled_sell = data.get('_last_filled_sell')
```

**Test:**
```python
class TestCrossedLevelReturnsLastFilled:
    """P1-JESSE-1: get_crossed_buy_level_price returns most recently crossed."""

    def test_returns_most_recent_not_first(self):
        gm = GridManager(GridConfig(grid_levels_count=5, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0)

        # Fill buy_1 first (at 99000)
        gm.check_buy_signal(98500.0)
        assert gm.get_crossed_buy_level_price() == pytest.approx(99000.0, abs=1)

        # Fill buy_2 (at 98000)
        gm.check_buy_signal(97500.0)
        # Should return buy_2's price (98000), not buy_1's (99000)
        assert gm.get_crossed_buy_level_price() == pytest.approx(98000.0, abs=1)

    def test_sell_returns_most_recent_not_first(self):
        gm = GridManager(GridConfig(grid_levels_count=5, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0)

        gm.check_sell_signal(101500.0)  # fills sell_1 at 101000
        gm.check_sell_signal(102500.0)  # fills sell_2 at 102000
        assert gm.get_crossed_sell_level_price() == pytest.approx(102000.0, abs=1)

    def test_returns_none_when_no_fills(self):
        gm = GridManager(GridConfig(grid_levels_count=5))
        gm.setup_grid(100000.0)
        assert gm.get_crossed_buy_level_price() is None
        assert gm.get_crossed_sell_level_price() is None

    def test_reset_clears_last_filled(self):
        gm = GridManager(GridConfig(grid_levels_count=5, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0)
        gm.check_buy_signal(98500.0)
        gm.reset()
        assert gm.get_crossed_buy_level_price() is None

    def test_serialization_preserves_last_filled(self):
        gm = GridManager(GridConfig(grid_levels_count=5, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0)
        gm.check_buy_signal(98500.0)

        data = gm.to_dict()
        gm2 = GridManager.from_dict(data)
        assert gm2.get_crossed_buy_level_price() == gm.get_crossed_buy_level_price()
```

**Risk:** Low. The existing tests in `test_strategy.py::TestCrossedLevelPrices` test single-fill
scenarios which still pass (first fill = last fill when there's only one). The fix only changes
behavior when multiple levels are filled, which is the buggy path.

**Note:** Existing test `test_get_crossed_buy_level_price` (line 233) fills only one level and
will still pass. No regression.

---

## Phase 4: P1-JESSE-2 — Fragile candle-to-dataframe column mapping

**File:** `jesse-bot/strategies/AIGridStrategy/factors_mixin.py:297-299`

```python
# Lines 297-299:
df = pd.DataFrame(
    candles[:, 1:6] if candles.shape[1] >= 6 else candles,
    columns=['open', 'high', 'low', 'close', 'volume'][:candles.shape[1] - 1] if candles.shape[1] >= 6 else ['open', 'high', 'low', 'close', 'volume'][:candles.shape[1]],
)
```

**Problem:** When `candles.shape[1] < 6`:
- The `else` branch uses the raw array (including timestamp column 0)
- Column names are sliced to `candles.shape[1]` count
- Result: timestamp is mapped to `'open'`, open to `'high'`, etc. — completely wrong

This means any candle array without the expected 6 columns produces silently corrupt factor data.
The `if 'close' not in df.columns` guard on line 303 only catches arrays with < 5 columns.
Arrays with exactly 5 columns would pass the check but have wrong data in every column.

**Fix:**
```python
# Replace lines 297-306:

# BEFORE:
df = pd.DataFrame(
    candles[:, 1:6] if candles.shape[1] >= 6 else candles,
    columns=['open', 'high', 'low', 'close', 'volume'][:candles.shape[1] - 1] if candles.shape[1] >= 6 else ['open', 'high', 'low', 'close', 'volume'][:candles.shape[1]],
)

# Ensure we have at least OHLC
if 'close' not in df.columns:
    return None

return df

# AFTER:
EXPECTED_COLUMNS = ['open', 'high', 'low', 'close', 'volume']

if candles.shape[1] >= 6:
    # Standard Jesse format: [timestamp, open, high, low, close, volume]
    df = pd.DataFrame(candles[:, 1:6], columns=EXPECTED_COLUMNS)
elif candles.shape[1] == 5:
    # No timestamp column: [open, high, low, close, volume]
    df = pd.DataFrame(candles, columns=EXPECTED_COLUMNS)
else:
    logger.warning(f"Candle array has unexpected shape: {candles.shape}")
    return None

return df
```

**Test:**
```python
class TestCandlesToDataframe:
    """P1-JESSE-2: Candle-to-dataframe must handle all column counts."""

    def test_standard_6_column_candles(self):
        """Standard Jesse format: [ts, open, high, low, close, volume]."""
        candles = np.array([
            [1000, 100.0, 105.0, 95.0, 102.0, 1000.0],
            [2000, 102.0, 108.0, 98.0, 106.0, 1200.0],
        ])
        df = FactorsMixin._candles_to_dataframe(candles)
        assert df is not None
        assert list(df.columns) == ['open', 'high', 'low', 'close', 'volume']
        assert df['close'].iloc[0] == 102.0
        assert df['open'].iloc[0] == 100.0

    def test_5_column_candles_no_timestamp(self):
        """5-column format: [open, high, low, close, volume]."""
        candles = np.array([
            [100.0, 105.0, 95.0, 102.0, 1000.0],
            [102.0, 108.0, 98.0, 106.0, 1200.0],
        ])
        df = FactorsMixin._candles_to_dataframe(candles)
        assert df is not None
        assert df['close'].iloc[0] == 102.0
        assert df['open'].iloc[0] == 100.0  # NOT timestamp

    def test_4_column_returns_none(self):
        """Arrays with < 5 columns return None."""
        candles = np.array([[100, 105, 95, 102], [102, 108, 98, 106]])
        df = FactorsMixin._candles_to_dataframe(candles)
        assert df is None

    def test_7_column_candles_extra_ignored(self):
        """Arrays with > 6 columns still work (extra cols ignored)."""
        candles = np.array([
            [1000, 100.0, 105.0, 95.0, 102.0, 1000.0, 999.0],
        ])
        df = FactorsMixin._candles_to_dataframe(candles)
        assert df is not None
        assert df['close'].iloc[0] == 102.0

    def test_empty_candles_returns_none(self):
        df = FactorsMixin._candles_to_dataframe(np.array([]))
        assert df is None

    def test_none_candles_returns_none(self):
        df = FactorsMixin._candles_to_dataframe(None)
        assert df is None
```

**Risk:** Low. The 6-column path (standard Jesse format) is unchanged. The fix only corrects
the fallback path for non-standard arrays. Any caller using standard Jesse candles sees no
change.

---

## Phase 5: P2-JESSE-1 — Hardcoded `"BTCUSDT"` in AI mixin

**File:** `jesse-bot/strategies/AIGridStrategy/ai_mixin.py:148,197,235`

```python
# Line 148 (_ai_analyze_market_async):
analysis: MarketAnalysis = await self._ai_agent.analyze_market(
    symbol="BTCUSDT",

# Line 197 (_ai_review_position_async):
assessment = await self._ai_agent.assess_risk(
    symbol="BTCUSDT",

# Line 235 (_ai_optimize_grid_async):
optimization: GridOptimization = await self._ai_agent.optimize_grid(
    symbol="BTCUSDT",
```

**Problem:** Even when trading ETH-USDT (the actual configured pair), all AI calls analyze
"BTCUSDT". The AI receives BTC context and makes BTC-based recommendations for an ETH position.
This corrupts AI analysis, risk assessment, and grid optimization.

**Fix:** Add `symbol` parameter to the async methods and pass it through from callers.

```python
# Add symbol parameter to AIMixin methods:

def ai_analyze_market(
    self,
    candles: list[list[float]],
    indicators: dict[str, float],
    symbol: str = "BTCUSDT",  # <-- add parameter with backward-compatible default
) -> dict:

def ai_review_position(
    self,
    position_info: dict,
    market_data: dict,
    symbol: str = "BTCUSDT",  # <-- add parameter
) -> str:

def ai_optimize_grid(
    self,
    current_grid: dict,
    market_analysis: dict,
    symbol: str = "BTCUSDT",  # <-- add parameter
) -> dict:

# Thread symbol through to the async methods:

async def _ai_analyze_market_async(self, candles, indicators, symbol="BTCUSDT"):
    # ... (existing code) ...
    analysis = await self._ai_agent.analyze_market(
        symbol=symbol,  # <-- was hardcoded "BTCUSDT"
        # ...
    )

async def _ai_review_position_async(self, position_info, market_data, symbol="BTCUSDT"):
    assessment = await self._ai_agent.assess_risk(
        symbol=symbol,  # <-- was hardcoded "BTCUSDT"
        # ...
    )

async def _ai_optimize_grid_async(self, current_grid, market_analysis, symbol="BTCUSDT"):
    optimization = await self._ai_agent.optimize_grid(
        symbol=symbol,  # <-- was hardcoded "BTCUSDT"
        # ...
    )
```

**Update callers in `__init__.py`:**
```python
# Line 524 (_run_ai_analysis):
analysis = self._ai_mixin.ai_analyze_market(candle_data, indicators, symbol=self.symbol)

# Line 580 (_run_ai_position_review):
decision = self._ai_mixin.ai_review_position(position_info, market_data, symbol=self.symbol)
```

**Also update caller in `live_trader.py`** if AI mixin is used there (currently it is not —
live_trader doesn't use AI, so no change needed).

**Test:**
```python
class TestAIMixinSymbol:
    """P2-JESSE-1: AI mixin must use actual trading symbol."""

    def test_analyze_passes_symbol_to_agent(self, ai_mixin, mock_agent):
        """ai_analyze_market passes symbol to TradingAgent."""
        ai_mixin.ai_analyze_market([], {}, symbol="ETHUSDT")
        call_kwargs = mock_agent.analyze_market.call_args.kwargs
        assert call_kwargs["symbol"] == "ETHUSDT"

    def test_review_passes_symbol_to_agent(self, ai_mixin, mock_agent):
        """ai_review_position passes symbol to TradingAgent."""
        ai_mixin.ai_review_position({}, {}, symbol="ETHUSDT")
        call_kwargs = mock_agent.assess_risk.call_args.kwargs
        assert call_kwargs["symbol"] == "ETHUSDT"

    def test_optimize_passes_symbol_to_agent(self, ai_mixin, mock_agent):
        """ai_optimize_grid passes symbol to TradingAgent."""
        ai_mixin.ai_optimize_grid({}, {}, symbol="ETHUSDT")
        call_kwargs = mock_agent.optimize_grid.call_args.kwargs
        assert call_kwargs["symbol"] == "ETHUSDT"

    def test_default_symbol_is_btcusdt(self, ai_mixin, mock_agent):
        """Default symbol is BTCUSDT for backward compatibility."""
        ai_mixin.ai_analyze_market([], {})
        call_kwargs = mock_agent.analyze_market.call_args.kwargs
        assert call_kwargs["symbol"] == "BTCUSDT"
```

**Risk:** Very low. Default parameter preserves existing behavior. Callers that pass `symbol=`
get the correct behavior.

---

## Phase 6: P2-JESSE-2 — Hardcoded `total_balance=10000.0`

**File:** `jesse-bot/strategies/AIGridStrategy/ai_mixin.py:209-210`

```python
# Lines 209-210 (_ai_review_position_async):
total_balance=10000.0,
position_pct=10.0,
```

**Problem:** AI risk assessment uses a hardcoded $10,000 balance and 10% position size regardless
of actual account balance. This means AI recommendations for position sizing and risk are based
on a fictional portfolio — too conservative for larger accounts, too aggressive for smaller ones.

**Fix:** Add `total_balance` parameter to `ai_review_position` and calculate `position_pct`:

```python
# Update ai_review_position signature:
def ai_review_position(
    self,
    position_info: dict,
    market_data: dict,
    symbol: str = "BTCUSDT",
    total_balance: float = 10000.0,  # <-- add parameter
) -> str:

# Update _ai_review_position_async:
async def _ai_review_position_async(
    self,
    position_info: dict,
    market_data: dict,
    symbol: str = "BTCUSDT",
    total_balance: float = 10000.0,
) -> str:
    current_price = position_info.get('current_price', 0.0)
    qty = position_info.get('qty', 0.0)
    position_value = current_price * qty
    position_pct = (position_value / total_balance * 100) if total_balance > 0 else 0.0

    assessment = await self._ai_agent.assess_risk(
        symbol=symbol,
        # ...
        total_balance=total_balance,       # <-- was 10000.0
        position_pct=position_pct,         # <-- was 10.0
    )
```

**Update caller in `__init__.py`:**
```python
# Line 580 (_run_ai_position_review):
decision = self._ai_mixin.ai_review_position(
    position_info, market_data,
    symbol=self.symbol,
    total_balance=self.balance,
)
```

**Test:**
```python
class TestAIMixinBalance:
    """P2-JESSE-2: AI mixin must use actual balance."""

    def test_review_passes_real_balance(self, ai_mixin, mock_agent):
        """ai_review_position passes actual balance to TradingAgent."""
        position_info = {"current_price": 2000.0, "qty": 0.5}
        ai_mixin.ai_review_position(
            position_info, {},
            symbol="ETHUSDT",
            total_balance=50000.0,
        )
        call_kwargs = mock_agent.assess_risk.call_args.kwargs
        assert call_kwargs["total_balance"] == 50000.0
        assert call_kwargs["position_pct"] == pytest.approx(2.0)  # 1000/50000 * 100

    def test_review_calculates_position_pct(self, ai_mixin, mock_agent):
        """position_pct is calculated from actual position value and balance."""
        position_info = {"current_price": 3000.0, "qty": 1.0}
        ai_mixin.ai_review_position(
            position_info, {},
            total_balance=10000.0,
        )
        call_kwargs = mock_agent.assess_risk.call_args.kwargs
        assert call_kwargs["position_pct"] == pytest.approx(30.0)  # 3000/10000 * 100

    def test_review_zero_balance_safe(self, ai_mixin, mock_agent):
        """Zero balance doesn't cause division by zero."""
        position_info = {"current_price": 2000.0, "qty": 0.5}
        ai_mixin.ai_review_position(
            position_info, {},
            total_balance=0.0,
        )
        call_kwargs = mock_agent.assess_risk.call_args.kwargs
        assert call_kwargs["position_pct"] == 0.0

    def test_default_balance_is_10000(self, ai_mixin, mock_agent):
        """Default balance is 10000 for backward compatibility."""
        ai_mixin.ai_review_position({}, {})
        call_kwargs = mock_agent.assess_risk.call_args.kwargs
        assert call_kwargs["total_balance"] == 10000.0
```

**Risk:** Very low. Default parameter preserves existing behavior. The calculated `position_pct`
is more accurate than the hardcoded 10%.

---

## Test File Structure

```
jesse-bot/tests/
├── test_strategy.py             # Existing (66 tests) — update for P1-JESSE-1
└── test_sprint25.py             # NEW — all Sprint 25 tests
    ├── TestLiveTraderGridPersistence   # P1-JESSE-3 (3 tests)
    ├── TestFilledOrderIdsBounded       # P1-JESSE-4 (3 tests)
    ├── TestCrossedLevelReturnsLastFilled  # P1-JESSE-1 (5 tests)
    ├── TestCandlesToDataframe          # P1-JESSE-2 (6 tests)
    ├── TestAIMixinSymbol               # P2-JESSE-1 (4 tests)
    └── TestAIMixinBalance              # P2-JESSE-2 (4 tests)
```

**Estimated test count:** 25 new tests
**Estimated lines changed:** ~120 (fixes) + ~300 (tests)

---

## Risk Assessment Summary

| Risk Level | Issues | Concern |
|------------|--------|---------|
| **Medium** | P1-JESSE-3 | Fundamental behavior change to grid lifecycle |
| **Low** | P1-JESSE-1, P1-JESSE-2, P1-JESSE-4 | Logic corrections, bounded data structures |
| **Very Low** | P2-JESSE-1, P2-JESSE-2 | Adding parameters with backward-compatible defaults |

### Key risks to watch:

1. **P1-JESSE-3 (Grid persistence):** The biggest change. The live trader will now hold grid
   state across iterations. If a bug causes stale grid levels to never be cleaned up, the bot
   could accumulate orders at prices far from the current market. Mitigated by: (a) trend change
   detection triggers rebuild, (b) `sync_orders()` already cancels stale orders outside grid
   range (line 325-336).

2. **P1-JESSE-1 (Last filled tracking):** The `_last_filled_buy/sell` fields must be serialized
   in `to_dict/from_dict` for the live_trader's state persistence. If omitted, a restart would
   lose the "last filled" info (but this is acceptable since the grid would be rebuilt anyway).

3. **Existing test regression:** The fix for P1-JESSE-1 changes `get_crossed_buy_level_price()`
   behavior. Existing test at `test_strategy.py:233-239` fills only one level so it still passes
   (first = last when there's only one fill). No regression.

---

## Checklist

- [ ] Phase 1: P1-JESSE-3 — Fix grid rebuild in live_trader.py
- [ ] Phase 2: P1-JESSE-4 — Bound filled_order_ids in live_trader.py
- [ ] Phase 3: P1-JESSE-1 — Fix get_crossed_buy_level_price in grid_logic.py
- [ ] Phase 4: P1-JESSE-2 — Fix candle-to-dataframe in factors_mixin.py
- [ ] Phase 5: P2-JESSE-1 — Parameterize symbol in ai_mixin.py
- [ ] Phase 6: P2-JESSE-2 — Parameterize total_balance in ai_mixin.py
- [ ] All tests passing (`pytest jesse-bot/tests/ -v`)
- [ ] Update `docs/STATUS.md`
