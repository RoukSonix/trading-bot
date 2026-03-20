# Sprint 29: Architecture & Decoupling — Implementation Plan

**Date:** 2026-03-19
**Branch:** `sprint-29-architecture`
**Worktree:** `~/projects/CentricVoid/trading-bots-sprint-29-architecture/`
**Issues:** 11 (4× P1-STRAT + 3× P1-AI + 1× P1-BACK + 1× P1-DASH + 1× P3-STRAT)
**Files to modify:** ~10 source files, 1 new test file

---

## Issue 1: P1-BACK-1 — `shared/` imports from `binance_bot`

**Files:** `shared/backtest/engine.py:18-19`, `shared/optimization/optimizer.py:11`
**Bug:** The `shared/` package (used by all bots) imports directly from `binance_bot`, creating a circular dependency. Any bot that uses `shared/backtest/` must also install `binance_bot`.

```python
# shared/backtest/engine.py:18-19 (current)
from binance_bot.strategies import GridStrategy, GridConfig
from binance_bot.strategies.base import SignalType

# shared/optimization/optimizer.py:11 (current)
from binance_bot.strategies import GridStrategy, GridConfig
```

**Fix:** Use dependency injection — accept strategy as a protocol/parameter instead of importing concrete classes. Move `GridConfig`, `SignalType`, and the strategy protocol to `shared/strategies/` so all bots can reference them.

```python
# Step 1: Create shared/strategies/base.py with the shared types
# Move SignalType enum and GridConfig dataclass here (or re-export from binance_bot)
# Better: define a StrategyProtocol that any bot's strategy can implement

# shared/strategies/base.py (new)
from enum import Enum
from dataclasses import dataclass
from typing import Protocol, Optional
import pandas as pd

class SignalType(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"

@dataclass
class GridConfig:
    """Grid configuration — shared across bots."""
    grid_lower: float = 0.0
    grid_upper: float = 0.0
    grid_levels: int = 10
    amount_per_level: float = 0.0
    # ... (copy fields from binance_bot/strategies/grid.py:26-65)

# Step 2: Update shared/backtest/engine.py imports
from shared.strategies.base import GridConfig, SignalType

# Step 3: Accept strategy via constructor parameter, not import
class BacktestEngine:
    def __init__(self, strategy_factory, ...):
        self.strategy_factory = strategy_factory

# Step 4: Update shared/optimization/optimizer.py similarly
from shared.strategies.base import GridConfig

# Step 5: Update binance_bot/strategies/base.py to re-export from shared
from shared.strategies.base import SignalType  # or keep both in sync
```

**VALIDATION NOTE:** `GridConfig` is a dataclass with ~15 fields. `GridStrategy` is used heavily in engine.py (lines 162, 454, 594, 599, 619, 624). The cleanest approach is to move the shared types to `shared/strategies/base.py` and have `binance_bot/strategies/base.py` re-export from there. Alternatively, use late imports (simpler but less clean).

**Simpler alternative (late imports):**
```python
# shared/backtest/engine.py — change lines 18-19 to late imports inside functions
# Remove top-level imports, add them inside Backtester.__init__ and BacktestEngine methods
def __init__(self, ...):
    from binance_bot.strategies import GridStrategy, GridConfig
    from binance_bot.strategies.base import SignalType
    ...

# Same for optimizer.py:11
```

**Recommended:** Late imports first (minimal change), then create `shared/strategies/base.py` as a follow-up in Sprint 30.

**Test:**
- `test_shared_backtest_import_no_binance_bot`: Mock `binance_bot` as unavailable → importing `shared.backtest.engine` at module level does not raise ImportError.
- `test_optimizer_import_no_binance_bot`: Same for `shared.optimization.optimizer`.

---

## Issue 2: P1-STRAT-3 — Hardcoded `"BTC/USDT"` in `order_manager.py`

**File:** `binance-bot/src/binance_bot/core/order_manager.py:186,192,198`
**Bug:** `execute_signal()` always uses `"BTC/USDT"` instead of the signal's symbol. Also `cancel_order()` defaults to `"BTC/USDT"`.

```python
# Lines 185-196 (current)
def execute_signal(self, signal: Signal, order_type: OrderType = OrderType.LIMIT) -> Order:
    side = "buy" if signal.type == SignalType.BUY else "sell"
    abs_amount = abs(signal.amount)

    if order_type == OrderType.MARKET:
        return self.create_market_order(
            symbol="BTC/USDT",  # TODO: get from signal
            side=side,
            amount=abs_amount,
        )
    else:
        return self.create_limit_order(
            symbol="BTC/USDT",
            ...
        )

# Line 198
def cancel_order(self, order_id: str, symbol: str = "BTC/USDT") -> bool:
```

**Fix:** Add `symbol` field to the `Signal` dataclass, then use `signal.symbol` in `execute_signal()`.

```python
# Step 0: Add symbol to Signal dataclass (binance_bot/strategies/base.py:18-24)
@dataclass
class Signal:
    type: SignalType
    price: float
    amount: float
    reason: str
    symbol: str = "BTC/USDT"   # <-- NEW FIELD (default preserves backward compat)
    confidence: float = 1.0

# Step 1: Fix execute_signal — use signal.symbol
def execute_signal(self, signal: Signal, order_type: OrderType = OrderType.LIMIT) -> Order:
    side = "buy" if signal.type == SignalType.BUY else "sell"
    abs_amount = abs(signal.amount)
    symbol = signal.symbol

    if order_type == OrderType.MARKET:
        return self.create_market_order(
            symbol=symbol,
            side=side,
            amount=abs_amount,
        )
    else:
        return self.create_limit_order(
            symbol=symbol,
            side=side,
            amount=abs_amount,
            price=signal.price,
        )
```

**VALIDATION NOTE (2026-03-19):** **CRITICAL** — The plan originally stated "The `Signal` class already has a `symbol` field" — **this is FALSE**. The `Signal` dataclass at `base.py:18-24` has fields: `type`, `price`, `amount`, `reason`, `confidence`. No `symbol` field exists. Using `signal.symbol` without adding the field would raise `AttributeError`. Two callers create `Signal` without `symbol`: `grid.py:423` and `grid.py:663` — these are fine with the default `"BTC/USDT"` value. Also check all callers of `cancel_order()` — the default `"BTC/USDT"` should be removed or the symbol made required.

**Test:**
- `test_execute_signal_uses_signal_symbol`: Create signal with symbol="ETH/USDT" → order placed with ETH/USDT.
- `test_execute_signal_btc`: Create signal with symbol="BTC/USDT" → order placed with BTC/USDT.

---

## Issue 3: P1-STRAT-6 — No retry in `ExchangeClient`

**File:** `binance-bot/src/binance_bot/core/exchange.py` (all methods: lines 35-150)
**Bug:** `get_balance()`, `get_all_balances()`, `get_ticker()`, `get_order_book()`, `get_ohlcv()` have zero error handling. Any `ccxt.NetworkError` or `ccxt.ExchangeNotAvailable` propagates unhandled.

```python
# Current — no error handling (e.g. get_ticker, line 90)
def get_ticker(self, symbol: str = "BTC/USDT") -> dict:
    ticker = self.exchange.fetch_ticker(symbol)
    return { ... }
```

**Fix:** Add retry decorator for transient errors. Use `tenacity` (already available in the project) or a simple custom retry.

```python
import time
from functools import wraps
import ccxt

def _retry_on_network_error(max_retries: int = 3, base_delay: float = 1.0):
    """Retry on transient CCXT errors with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (ccxt.NetworkError, ccxt.ExchangeNotAvailable) as e:
                    last_error = e
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"{func.__name__} attempt {attempt + 1}/{max_retries} failed: {e}. Retrying in {delay}s...")
                    time.sleep(delay)
            raise last_error
        return wrapper
    return decorator

# Apply to all exchange methods:
@_retry_on_network_error(max_retries=3)
def get_balance(self, currency: str = "USDT") -> dict:
    ...

@_retry_on_network_error(max_retries=3)
def get_ticker(self, symbol: str = "BTC/USDT") -> dict:
    ...

# Same for get_all_balances, get_order_book, get_ohlcv
```

**VALIDATION NOTE (2026-03-19):** `tenacity` is NOT in any requirements file (verified via grep). Use the custom `_retry_on_network_error` decorator above. File is 155 lines total — methods span lines 35-150. The decorator adds ~20 lines at the top. Clean change.

**Test:**
- `test_get_ticker_retries_on_network_error`: Mock exchange to raise `NetworkError` twice then succeed → returns ticker.
- `test_get_ticker_gives_up_after_max_retries`: Mock exchange to always raise → raises after 3 attempts.
- `test_get_balance_no_retry_on_auth_error`: Mock `AuthenticationError` → raises immediately (no retry).

---

## Issue 4: P1-STRAT-9 — Relative paths for emergency stop

**File:** `binance-bot/src/binance_bot/core/emergency.py:28-29`
**Bug:** `TRIGGER_FILE` and `STATE_FILE` use relative paths. When the bot runs from Docker (different CWD than development), these resolve to the wrong location.

```python
# Lines 28-29 (current)
TRIGGER_FILE = Path(".emergency_stop")
STATE_FILE = Path("data/emergency_state.json")
```

**Fix:** Resolve relative to the bot's known data directory (from settings or relative to the project root).

```python
# Fix: resolve relative to project root or make configurable
import os

# Use the bot's data directory (same one used by database.py)
_DATA_DIR = Path(os.getenv("BOT_DATA_DIR", "data"))
TRIGGER_FILE = _DATA_DIR / ".emergency_stop"
STATE_FILE = _DATA_DIR / "emergency_state.json"
```

**VALIDATION NOTE:** Check what directory the Docker container uses as CWD (`WORKDIR` in Dockerfile). Also check if `data/` is the correct directory — `database.py` already uses `Path("data")` for the SQLite file. The trigger file should be in the same data directory for consistency. Alternatively, make the paths absolute using `Path(__file__).parent.parent.parent.parent / "data"` but that's fragile. The env var approach is cleanest.

**Test:**
- `test_emergency_trigger_in_data_dir`: Verify `TRIGGER_FILE` is inside the data directory.
- `test_emergency_custom_data_dir`: Set `BOT_DATA_DIR=/tmp/test` → paths resolve to `/tmp/test/`.

---

## Issue 5: P1-STRAT-10 — Hardcoded `$0.01` tolerance in `_get_level_number`

**File:** `binance-bot/src/binance_bot/strategies/ai_grid.py:252`
**Bug:** `_get_level_number()` uses a fixed `0.01` tolerance to match prices to grid levels. This works for BTC (~$85k) but is wrong for cheap tokens (e.g., DOGE at $0.10 where 0.01 is 10% of the price) or precise assets.

```python
# Line 252 (current)
if abs(level.price - price) < 0.01:
```

**Fix:** Use a relative tolerance based on the grid spacing or the level price.

```python
# Fix: use relative tolerance (0.1% of price, minimum $0.001)
def _get_level_number(self, price: float) -> int:
    """Get grid level number for a price."""
    for i, level in enumerate(self.levels):
        tolerance = max(level.price * 0.001, 0.001)  # 0.1% or $0.001 minimum
        if abs(level.price - price) < tolerance:
            return i + 1
    return 0
```

**VALIDATION NOTE:** The grid spacing is `(grid_upper - grid_lower) / num_levels`. A tolerance of `spacing * 0.1` (10% of spacing) might be more appropriate. Check how callers use `_get_level_number` — if it's for exact level matching, the tolerance should be tight. If it's for "close enough", relative tolerance is better.

**Test:**
- `test_level_matching_btc_price`: Levels at $85,000 intervals → matching works with small offset.
- `test_level_matching_cheap_token`: Levels at $0.10 intervals → 0.01 offset still matches (not 10% away).
- `test_level_matching_no_match`: Price far from any level → returns 0.

---

## Issue 6: P1-STRAT-11 — Regex rejects nested JSON from LLM

**File:** `binance-bot/src/binance_bot/strategies/ai_grid.py:412`
**Bug:** The regex `r'\{[^{}]+\}'` requires no braces inside the JSON. LLM responses often contain nested objects (e.g., `{"action": "ADJUST", "params": {"lower": 80000}}`), which this regex cannot match.

```python
# Line 412 (current)
json_match = re.search(r'\{[^{}]+\}', response, re.DOTALL)
```

**Fix:** Use a balanced-brace matching approach or try `json.loads` on progressively larger substrings.

```python
# Fix: find the outermost JSON object using brace counting
def _extract_json(self, text: str) -> Optional[dict]:
    """Extract first JSON object from text, supporting nested braces."""
    start = text.find('{')
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None

# In _parse_ai_response (around line 409):
parsed = self._extract_json(response)
if parsed:
    action = str(parsed.get("action", "")).upper()
    ...
```

**Test:**
- `test_parse_flat_json`: `'{"action": "CONTINUE", "risk": "LOW"}'` → parsed correctly.
- `test_parse_nested_json`: `'{"action": "ADJUST", "params": {"lower": 80000}}'` → parsed correctly.
- `test_parse_json_in_markdown`: `` '```json\n{"action": "PAUSE"}\n```' `` → parsed correctly.
- `test_parse_no_json`: `'Just a plain text response'` → returns None.

---

## Issue 7: P1-AI-1 — LLM parsing false positives on negation

**File:** `shared/ai/agent.py:196-201`
**Bug:** Simple `"bullish" in response_lower` matches "not bullish", "less bullish than expected", "bearish, not bullish at all". Same issue with "bearish", "high risk", "low risk", and grid recommendation parsing.

```python
# Lines 196-201 (current)
if "bullish" in response_lower:
    trend = Trend.BULLISH
elif "bearish" in response_lower:
    trend = Trend.BEARISH
else:
    trend = Trend.SIDEWAYS
```

**Fix:** Use regex word boundaries and exclude negation patterns. Also check for JSON first (see P1-AI-3).

```python
import re

# Fix: check for negation before keyword matching
def _detect_trend(self, response_lower: str) -> Trend:
    """Detect trend from response, handling negation."""
    # Try JSON first (P1-AI-3 fix)
    # ...

    # Negation-aware keyword matching
    negation_pattern = r'(?:not|no|don\'t|isn\'t|aren\'t|neither|without)\s+'

    bullish_match = re.search(r'\bbullish\b', response_lower)
    bullish_negated = re.search(negation_pattern + r'bullish', response_lower) if bullish_match else None

    bearish_match = re.search(r'\bbearish\b', response_lower)
    bearish_negated = re.search(negation_pattern + r'bearish', response_lower) if bearish_match else None

    if bullish_match and not bullish_negated:
        return Trend.BULLISH
    elif bearish_match and not bearish_negated:
        return Trend.BEARISH
    return Trend.SIDEWAYS
```

**VALIDATION NOTE:** Same negation issue affects:
- Risk level detection (lines 204-209): `"high risk" in response_lower`
- Grid recommendation (lines 212-217): `"activate grid" in response_lower`
- Volatility detection (lines 220-223): `"suitable" in response_lower`

All should get the same negation-aware treatment.

**Test:**
- `test_trend_bullish`: `"The market is bullish"` → BULLISH.
- `test_trend_not_bullish`: `"The market is not bullish"` → SIDEWAYS (not BULLISH).
- `test_trend_bearish_negated`: `"I don't think it's bearish"` → SIDEWAYS.
- `test_risk_not_high`: `"risk is not high"` → not HIGH.

---

## Issue 8: P1-AI-2 — `assess_risk()` dead code (89 lines)

**File:** `shared/ai/agent.py:343-431`
**Bug:** `assess_risk()` and `_parse_risk_assessment()` are 89 lines that the audit calls dead code. However, **jesse-bot DOES call it** at `jesse-bot/strategies/AIGridStrategy/ai_mixin.py:209`.

```python
# jesse-bot/strategies/AIGridStrategy/ai_mixin.py:209
assessment = await self._ai_agent.assess_risk(...)
```

**Fix:** Keep the method — it's NOT dead code. Add a comment documenting the caller. However, the binance-bot should also integrate it (or we accept that it's jesse-bot-only).

```python
# Line 343 — add docstring noting usage
async def assess_risk(
    self,
    ...
) -> RiskAssessment:
    """Assess risk for a position.

    Used by: jesse-bot/strategies/AIGridStrategy/ai_mixin.py
    """
```

**VALIDATION NOTE:** The audit incorrectly flagged this as dead code because it only searched `binance-bot/` and `shared/` for callers, missing `jesse-bot/`. Do NOT remove this method.

**Test:**
- `test_assess_risk_returns_valid_assessment`: Call with valid params → returns RiskAssessment.
- `test_assess_risk_parser_handles_edge_cases`: Covered by P1-AI-3 below.

---

## Issue 9: P1-AI-3 — All LLM parsing is fragile string matching

**File:** `shared/ai/agent.py:185-431` (3 parsers + 1 confirmer)
**Bug:** Four parsing functions rely on fragile string matching:
- `_parse_market_analysis()` (lines 185-256): substring `"bullish" in` matching
- `_parse_grid_optimization()` (lines 295-341): `line.startswith('GRID_LOWER:')` line-by-line
- `_parse_risk_assessment()` (lines 384-431): `'risk score' in line.lower()` line-by-line
- `confirm_signal()` (lines 433-466): similar string matching

All break when LLMs:
- Wrap output in markdown code blocks
- Add extra whitespace/punctuation
- Use slightly different formats ("Grid Lower:" vs "GRID_LOWER:")
- Return nested JSON

**Fix:** Add a JSON-first approach to all parsers. Try to extract structured JSON first, fall back to the existing string parsing.

```python
def _try_parse_json(self, response: str) -> Optional[dict]:
    """Try to extract JSON from LLM response.

    Handles:
    - Raw JSON
    - Markdown code blocks (```json ... ```)
    - JSON embedded in prose
    """
    # Strip markdown code blocks
    cleaned = re.sub(r'```(?:json)?\s*', '', response)
    cleaned = re.sub(r'```', '', cleaned)

    # Try direct parse
    try:
        return json.loads(cleaned.strip())
    except (json.JSONDecodeError, ValueError):
        pass

    # Try extracting JSON object with nested brace support
    start = cleaned.find('{')
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(cleaned[start:], start):
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(cleaned[start:i + 1])
                except json.JSONDecodeError:
                    break
    return None

# Then in each parser, try JSON first:
def _parse_market_analysis(self, response, ...):
    parsed = self._try_parse_json(response)
    if parsed:
        trend_str = str(parsed.get("trend", "")).lower()
        # ... map to enum
        return MarketAnalysis(...)

    # Fall back to existing string matching
    response_lower = response.lower()
    ...

def _parse_grid_optimization(self, response, ...):
    parsed = self._try_parse_json(response)
    if parsed:
        return GridOptimization(
            lower_price=float(parsed.get("grid_lower", default_lower)),
            ...
        )

    # Fall back to existing line-by-line parsing
    for line in response.split('\n'):
        ...
```

**VALIDATION NOTE:** This is the largest change in the sprint. Each parser needs:
1. JSON extraction attempt via `_try_parse_json()`
2. Mapping from JSON keys to the expected dataclass fields
3. Fallback to existing string parsing (don't remove it — backward compat)

**Test:**
- `test_parse_market_json`: `'{"trend": "bullish", "risk": "low"}'` → correct MarketAnalysis.
- `test_parse_market_markdown_json`: `` '```json\n{"trend": "bearish"}\n```' `` → correct.
- `test_parse_market_fallback_string`: `'The market is bullish with low risk'` → falls back to string parsing.
- `test_parse_grid_json`: `'{"grid_lower": 80000, "grid_upper": 90000, "num_levels": 15}'` → correct.
- `test_parse_grid_fallback_lines`: `'GRID_LOWER: 80000\nGRID_UPPER: 90000'` → falls back.
- `test_parse_risk_json`: `'{"risk_score": 7, "action": "HOLD"}'` → correct.

---

## Issue 10: P1-DASH-1 — `time.sleep()` blocks Streamlit thread

**File:** `shared/dashboard/app.py:247-249`
**Bug:** `time.sleep(st.session_state.refresh_sec)` blocks the Streamlit server thread for up to 60 seconds. During this time the dashboard is completely unresponsive — no user interaction, no page loads.

```python
# Lines 247-249 (current)
if st.session_state.auto_refresh:
    time.sleep(st.session_state.refresh_sec)
    st.rerun()
```

**Fix:** Use Streamlit's built-in `st_autorefresh` component or `st.fragment` with rerun delay. The simplest fix for Streamlit ≥1.27 is `st.rerun()` with a timer-based approach.

```python
# Fix: use streamlit-autorefresh or st.empty() with fragment
# Option A: streamlit-autorefresh (requires pip install streamlit-autorefresh)
from streamlit_autorefresh import st_autorefresh

if st.session_state.auto_refresh:
    st_autorefresh(interval=st.session_state.refresh_sec * 1000, key="auto_refresh")

# Option B: Streamlit native (simpler, no dependency)
# Remove the sleep entirely, use st.rerun() with a shorter interval + timestamp check
import time as _time

if st.session_state.auto_refresh:
    last_refresh = st.session_state.get("_last_refresh", 0)
    if _time.time() - last_refresh >= st.session_state.refresh_sec:
        st.session_state._last_refresh = _time.time()
        st.rerun()
```

**VALIDATION NOTE:** Option B is preferred — no new dependency. But it still has a race: if the page renders quickly, it'll call `st.rerun()` in a tight loop until the interval passes. Better approach: just remove sleep and let `st.rerun()` trigger immediately. The natural page render time provides the delay. For longer intervals, use `streamlit-autorefresh`.

**Simplest fix (recommended):**
```python
if st.session_state.auto_refresh:
    st.rerun()  # Streamlit adds ~1-2s render time naturally
```

Then add `streamlit-autorefresh` for proper interval control if needed.

**Test:**
- `test_dashboard_no_sleep_import`: Verify `time.sleep` is not called in `app.py`.
- `test_auto_refresh_triggers_rerun`: Mock `st.rerun` → verify it's called when auto_refresh is True.

---

## Issue 11: P3-STRAT-3 — Duplicate RSI/EMA/ADX/ATR implementations

**File:** `binance-bot/src/binance_bot/strategies/grid.py:207-304,479-496`
**Bug:** `GridStrategy` re-implements:
- **EMA** (lines 226-227): `close.ewm(span=20).mean()` — duplicates `shared/indicators/trend.py:12` `ema()`
- **RSI** (lines 242-250): manual gain/loss calculation — duplicates `shared/indicators/momentum.py:7` `rsi()`
- **ADX** (lines 282-304): full `_calculate_adx()` method — duplicates `shared/indicators/trend.py:216` `adx()`
- **ATR** (lines 479-496): `update_atr()` method — duplicates `shared/indicators/volatility.py:7` `atr()`

Also duplicated in `shared/core/indicators.py` (class methods: `ema` at line 51, `rsi` at line 56, `atr` at line 82).

**Fix:** Replace inline calculations with calls to `shared/indicators/`.

```python
# In grid.py — replace detect_trend internals
from shared.indicators.trend import ema, adx
from shared.indicators.momentum import rsi
from shared.indicators.volatility import atr as calc_atr

def detect_trend(self, ohlcv_df: pd.DataFrame) -> str:
    if len(ohlcv_df) < 50:
        return "sideways"

    close = ohlcv_df["close"]

    # Use shared indicators instead of inline calculations
    ema_20 = ema(ohlcv_df, period=20)
    ema_50 = ema(ohlcv_df, period=50)

    ema_bullish = ema_20.iloc[-1] > ema_50.iloc[-1]
    ema_bearish = ema_20.iloc[-1] < ema_50.iloc[-1]

    current_price = close.iloc[-1]
    price_above_ema20 = current_price > ema_20.iloc[-1]
    price_above_ema50 = current_price > ema_50.iloc[-1]

    # ADX from shared
    adx_df = adx(ohlcv_df, period=14)
    adx_value = float(adx_df["adx"].iloc[-1]) if not adx_df.empty else 0.0
    strong_trend = adx_value > 25

    # RSI from shared
    rsi_series = rsi(ohlcv_df, period=14)
    current_rsi = float(rsi_series.iloc[-1])

    # Scoring (unchanged)
    ...

def update_atr(self, df: pd.DataFrame, period: int = 14):
    if len(df) < period:
        return
    atr_series = calc_atr(df, period=period)
    self.current_atr = float(atr_series.iloc[-1]) if not np.isnan(atr_series.iloc[-1]) else 0.0
```

**VALIDATION NOTE:** Verify that `shared/indicators/trend.py` `ema()` and `adx()` return compatible types (pd.Series / pd.DataFrame). The `adx()` function returns a DataFrame with columns `["plus_di", "minus_di", "adx"]` — need to extract `["adx"]` column. The `rsi()` function returns a pd.Series. Also remove `_calculate_adx()` method (lines 282-304) after migration.

**Test:**
- `test_detect_trend_uses_shared_indicators`: Mock shared indicators → verify they're called (not inline calc).
- `test_detect_trend_results_unchanged`: Compare output of old vs new implementation on sample data → identical.
- `test_update_atr_uses_shared`: Mock `shared.indicators.volatility.atr` → verify called.

---

## Implementation Order

| Step | Issue | Risk | Dependencies |
|------|-------|------|-------------|
| 1 | P1-STRAT-9 (Issue 4) | Low | None — path constants |
| 2 | P1-STRAT-10 (Issue 5) | Low | None — single tolerance line |
| 3 | P1-STRAT-3 (Issue 2) | Low | None — use signal.symbol |
| 4 | P1-STRAT-11 (Issue 6) | Low | None — regex replacement |
| 5 | P1-AI-2 (Issue 8) | Low | None — just add docstring |
| 6 | P1-DASH-1 (Issue 10) | Low | None — remove sleep |
| 7 | P1-STRAT-6 (Issue 3) | Medium | None — new retry decorator |
| 8 | P1-AI-1 (Issue 7) | Medium | None — negation-aware matching |
| 9 | P1-AI-3 (Issue 9) | High | Issue 7 (same file, overlapping code) |
| 10 | P3-STRAT-3 (Issue 11) | Medium | None — but must verify shared indicators API |
| 11 | P1-BACK-1 (Issue 1) | High | Most cross-cutting — import restructuring |

**Rationale:** Simple constant/path fixes first. Retry logic and AI parsing middle (contained risk). Cross-cutting import changes and indicator consolidation last (highest regression surface).

---

## Files Modified

| File | Issues | Changes |
|------|--------|---------|
| `binance-bot/src/binance_bot/core/emergency.py` | P1-STRAT-9 | Path constants → use data dir (~3 lines) |
| `binance-bot/src/binance_bot/strategies/ai_grid.py` | P1-STRAT-10, P1-STRAT-11 | Tolerance fix + JSON extractor (~25 lines) |
| `binance-bot/src/binance_bot/core/order_manager.py` | P1-STRAT-3 | Use signal.symbol (~4 lines) |
| `binance-bot/src/binance_bot/core/exchange.py` | P1-STRAT-6 | Add retry decorator (~25 lines) |
| `binance-bot/src/binance_bot/strategies/grid.py` | P3-STRAT-3 | Replace inline indicators with shared (~50 lines net reduction) |
| `shared/ai/agent.py` | P1-AI-1, P1-AI-2, P1-AI-3 | JSON-first parsing + negation handling (~60 lines added, existing kept as fallback) |
| `shared/dashboard/app.py` | P1-DASH-1 | Remove time.sleep (~2 lines) |
| `shared/backtest/engine.py` | P1-BACK-1 | Late imports (~6 lines) |
| `shared/optimization/optimizer.py` | P1-BACK-1 | Late imports (~4 lines) |

## Test File

`tests/unit/test_sprint29_architecture.py` — ~300 lines covering all 11 issues.

Test classes:
- `TestP1Back1SharedImports`
- `TestP1Strat3HardcodedSymbol`
- `TestP1Strat6ExchangeRetry`
- `TestP1Strat9EmergencyPaths`
- `TestP1Strat10PriceTolerance`
- `TestP1Strat11NestedJson`
- `TestP1Ai1NegationParsing`
- `TestP1Ai2AssessRiskNotDead`
- `TestP1Ai3JsonFirstParsing`
- `TestP1Dash1NoSleep`
- `TestP3Strat3DuplicateIndicators`

---

## Validation (2026-03-19)

All 11 issues validated against source. Line numbers verified by reading each file.

### Line number discrepancies from AUDIT_V2.md (corrected above):
- P1-STRAT-3: audit said 185,192 → actual 186,192 (off by 1 on first)
- P1-STRAT-10: audit said 248 → actual 252 (off by 4)
- P1-STRAT-11: audit said 408 → actual 412 (off by 4)
- P1-AI-1: audit said 196-200 → actual 196-201 (range end off by 1)
- P1-AI-2: audit said "dead code, never called" → **WRONG**: jesse-bot calls it at `ai_mixin.py:209`
- P3-STRAT-3: audit said 201-295,470-487 → actual 207-304,479-496 (offset ~6 lines)

### Key findings during validation:
1. **P1-AI-2 is NOT dead code** — jesse-bot uses `assess_risk()`. Do not remove.
2. **P1-BACK-1** has two viable approaches: late imports (quick fix) vs. creating `shared/strategies/base.py` (proper fix). Recommend late imports for this sprint.
3. **P3-STRAT-3** — `shared/indicators/` has proper implementations of all four indicators. The `adx()` function returns a DataFrame (not float), so the call site needs to extract the `["adx"]` column.
4. **P1-STRAT-6** — The file is only 155 lines. The retry decorator adds ~20 lines at the top and 5 decorator applications. Clean change.
5. **P1-AI-3** — The `_try_parse_json()` utility will be shared across all 4 parsers. Implement once, use in all.
