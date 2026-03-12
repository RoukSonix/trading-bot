# Sprint 24: P0 Runtime Crash Fixes — Implementation Plan

> **Date:** 2026-03-12
> **Branch:** `feature/sprint-24-p0-fixes`
> **Source:** AUDIT_V2.md (28 P0 issues, 23 in Sprint 24 scope)
> **Goal:** Eliminate all runtime crashes and data corruption bugs

---

## Implementation Order

Issues are grouped into 5 phases, ordered by dependency (foundational fixes first).

| Phase | Focus | Issues | Rationale |
|-------|-------|--------|-----------|
| 1 | Foundation (config, DB, state) | P0-CORE-1, P0-CORE-2, P0-CORE-3 | Everything imports `shared.config` and `shared.core` |
| 2 | Shared indicators | P0-CORE-4, P0-STRAT-1, P0-STRAT-2 | Indicators are used by strategies, backtest, and AI |
| 3 | Shared services (AI, alerts, risk, backtest, vector_db) | P0-AI-1, P0-AI-2, P0-ALERT-1, P0-ALERT-2, P0-RISK-1, P0-RISK-2, P0-BACK-1, P0-VDB-1, P0-VDB-2 | Services depend on Phase 1 & 2 |
| 4 | Bot & strategies | P0-BOT-1..4, P0-STRAT-3..6 | Bot depends on all shared modules |
| 5 | Jesse bot | P0-JESSE-1..3 | Independent codebase, can be done last |

---

## Phase 1: Foundation Fixes

### P0-CORE-1: `Settings()` crashes at import time without env vars

**File:** `shared/config/settings.py:196`
**Line:** 196 — `settings = Settings()`
**Problem:** `binance_api_key` and `binance_secret_key` use `Field(...)` (required). Missing env vars cause `ValidationError` at import time, crashing any code that imports `shared.config`. Blocks all testing and tooling.

**Fix:**
```python
# shared/config/settings.py:196
# BEFORE:
settings = Settings()

# AFTER:
def _get_settings() -> Settings:
    """Lazy settings factory — only validates on first access."""
    return Settings()

class _LazySettings:
    """Proxy that defers Settings() instantiation until first attribute access."""
    _instance: Settings | None = None

    def _load(self):
        if self._instance is None:
            self._instance = Settings()

    def __getattr__(self, name):
        self._load()
        return getattr(self._instance, name)

settings = _LazySettings()
```

**Alternative (simpler):** Give `binance_api_key` and `binance_secret_key` empty-string defaults, validate at runtime:
```python
binance_api_key: str = Field(default="", description="Binance API key")
binance_secret_key: str = Field(default="", description="Binance secret key")

def validate_trading_config(self):
    """Call before trading — raises if keys are missing."""
    if not self.binance_api_key or not self.binance_secret_key:
        raise ValueError("Binance API keys required for trading")
```

**Preferred approach:** Empty defaults + runtime validation. Simpler, keeps Settings as a normal Pydantic model, and unblocks testing.

**Test:**
```python
def test_settings_without_env_vars(monkeypatch):
    """Settings loads without crashing when API keys are missing."""
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_SECRET_KEY", raising=False)
    from shared.config.settings import Settings
    s = Settings()
    assert s.binance_api_key == ""

def test_settings_with_env_vars(monkeypatch):
    """Settings picks up env vars correctly."""
    monkeypatch.setenv("BINANCE_API_KEY", "test-key")
    monkeypatch.setenv("BINANCE_SECRET_KEY", "test-secret")
    from shared.config.settings import Settings
    s = Settings()
    assert s.binance_api_key == "test-key"
```

**Risk:** Low. Existing code that calls `settings.binance_api_key` still works. Only difference: empty string instead of crash when keys are absent.

---

### P0-CORE-2: `BotState.from_dict()` mutates caller's dict via `.pop()`

**File:** `shared/core/state.py:82-83`
**Lines:** 82-83
```python
grid_levels = data.pop("grid_levels", [])  # mutates caller's dict
positions = data.pop("positions", [])      # mutates caller's dict
```

**Problem:** `.pop()` removes keys from the dict passed by caller. Any code reusing the dict after calling `from_dict()` will find keys missing.

**Fix:**
```python
# BEFORE:
grid_levels = data.pop("grid_levels", [])
positions = data.pop("positions", [])
state = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

# AFTER:
grid_levels = data.get("grid_levels", [])
positions = data.get("positions", [])
excluded = {"grid_levels", "positions"}
state = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__ and k not in excluded})
```

**Test:**
```python
def test_from_dict_does_not_mutate_input():
    data = {"grid_levels": [1, 2], "positions": [{"a": 1}], "symbol": "BTC/USDT"}
    original = data.copy()
    BotState.from_dict(data)
    assert data == original  # dict must be unchanged
```

**Risk:** Very low. Pure read-only change. The `cls(**...)` filter already excludes `grid_levels` and `positions` via `__dataclass_fields__` check.

---

### P0-CORE-3: Decimal values not JSON-serializable from database

**File:** `shared/core/database.py:189-204` (TradeLog.to_dict) and `355-378` (get_trades_summary)
**Problem:** `Numeric(18,8)` columns return `decimal.Decimal` objects. `round(Decimal)` returns `Decimal`, not `float`. JSON serialization raises `TypeError`.

**Fix — TradeLog.to_dict (lines 189-204):**
```python
# BEFORE:
"price": self.price,
"amount": self.amount,
"pnl": self.pnl,
"fees": self.fees,

# AFTER:
"price": float(self.price) if self.price is not None else 0.0,
"amount": float(self.amount) if self.amount is not None else 0.0,
"pnl": float(self.pnl) if self.pnl is not None else 0.0,
"fees": float(self.fees) if self.fees is not None else 0.0,
```

**Fix — get_trades_summary (lines 355-378):**
```python
# BEFORE:
"total_pnl": round(total_pnl, 4),
"total_fees": round(total_fees, 4),
"net_pnl": round(total_pnl - total_fees, 4),
...
"total_volume": round(sum(t.price * t.amount for t in trades), 4),

# AFTER:
"total_pnl": round(float(total_pnl), 4),
"total_fees": round(float(total_fees), 4),
"net_pnl": round(float(total_pnl - total_fees), 4),
...
"total_volume": round(float(sum(t.price * t.amount for t in trades)), 4),
```

**Test:**
```python
import json
from decimal import Decimal

def test_trade_log_to_dict_json_serializable():
    """to_dict() output must be JSON-serializable."""
    trade = TradeLog(price=Decimal("50000.12345678"), amount=Decimal("0.001"), pnl=Decimal("5.50"), fees=Decimal("0.01"))
    d = trade.to_dict()
    json.dumps(d)  # must not raise TypeError

def test_trades_summary_json_serializable():
    """get_trades_summary() output must be JSON-serializable."""
    summary = get_trades_summary(symbol="BTC/USDT")
    json.dumps(summary)  # must not raise TypeError
```

**Risk:** Low. `float(Decimal)` is a lossless conversion for the precision we use (4 decimal places in output).

---

## Phase 2: Shared Indicator Fixes

### P0-CORE-4: Division by zero in 8+ shared indicators

**Files and lines:**

| Location | Line | Expression | Zero condition |
|----------|------|-----------|----------------|
| `shared/indicators/momentum.py` | 14 | `avg_gain / avg_loss` | All prices rose (avg_loss=0) |
| `shared/indicators/momentum.py` | 43 | `(close - low_min) / (high_max - low_min)` | Flat market (high=low) |
| `shared/indicators/momentum.py` | 58 | `(rsi_val - rsi_min) / (rsi_max - rsi_min)` | Flat RSI |
| `shared/indicators/momentum.py` | 70 | `(high_max - close) / (high_max - low_min)` | Flat market |
| `shared/indicators/momentum.py` | 84 | `positive_mf / negative_mf` | All flow positive |
| `shared/indicators/momentum.py` | 104 | `double_smoothed / double_smoothed_abs` | No price change |
| `shared/indicators/trend.py` | 69 | `cum_tp_vol / cum_vol` | Zero volume |
| `shared/indicators/trend.py` | 240 | `(plus_di - minus_di).abs() / (plus_di + minus_di)` | Both DI zero |
| `shared/indicators/trend.py` | 278 | `(typical - sma) / (0.015 * mad)` | Flat prices (mad=0) |

**Fix pattern (apply to all):**
```python
# For pandas Series division — use .replace(0, np.nan):
# BEFORE:
rs = avg_gain / avg_loss

# AFTER:
rs = avg_gain / avg_loss.replace(0, np.nan)

# For scalar or Series where denominator can be zero:
# BEFORE:
stoch_k = 100 * (df["close"] - low_min) / (high_max - low_min)

# AFTER:
denom = high_max - low_min
stoch_k = 100 * (df["close"] - low_min) / denom.replace(0, np.nan)
stoch_k = stoch_k.fillna(50.0)  # neutral default for stochastic
```

**Specific fixes per indicator:**

| Indicator | Line | Fix | Default value |
|-----------|------|-----|---------------|
| RSI | 14 | `avg_loss.replace(0, np.nan)` → fillna(100.0) | RSI=100 when no losses |
| Stochastic | 43 | `(high_max - low_min).replace(0, np.nan)` → fillna(50.0) | Neutral |
| StochRSI | 58 | `(rsi_max - rsi_min).replace(0, np.nan)` → fillna(0.5) | Neutral |
| Williams %R | 70 | `(high_max - low_min).replace(0, np.nan)` → fillna(-50.0) | Neutral |
| MFI | 84 | `negative_mf.replace(0, np.nan)` → fillna(100.0) | MFI=100 when all positive |
| TSI | 104 | `double_smoothed_abs.replace(0, np.nan)` → fillna(0.0) | Neutral |
| VWAP | 69 | `cum_vol.replace(0, np.nan)` → fillna(method="ffill") | Previous VWAP |
| ADX-DX | 240 | `(plus_di + minus_di).replace(0, np.nan)` → fillna(0.0) | DX=0 |
| CCI | 278 | `mad.replace(0, np.nan)` → fillna(0.0) | CCI=0 |

**Test:**
```python
import pandas as pd
import numpy as np

def test_rsi_flat_market():
    """RSI handles flat prices without division by zero."""
    df = pd.DataFrame({"close": [100.0] * 30})
    result = calculate_rsi(df)
    assert not np.isinf(result).any()
    assert not np.isnan(result.iloc[-1])

def test_stochastic_flat_market():
    """Stochastic handles high==low without division by zero."""
    df = pd.DataFrame({"high": [100.0]*20, "low": [100.0]*20, "close": [100.0]*20})
    result = stochastic(df)
    assert not np.isinf(result).any()

def test_adx_flat_market():
    """ADX handles zero DI values."""
    df = pd.DataFrame({"high": [100.0]*30, "low": [100.0]*30, "close": [100.0]*30})
    result = calculate_adx(df)
    assert not np.isinf(result).any()

def test_cci_flat_prices():
    """CCI handles zero MAD."""
    df = pd.DataFrame({"high": [100.0]*25, "low": [100.0]*25, "close": [100.0]*25})
    result = calculate_cci(df)
    assert not np.isinf(result).any()

def test_vwap_zero_volume():
    """VWAP handles zero volume."""
    df = pd.DataFrame({"high": [101]*10, "low": [99]*10, "close": [100]*10, "volume": [0]*10})
    result = calculate_vwap(df)
    assert not np.isinf(result).any()
```

**Risk:** Medium. Changing indicator output for edge cases could affect strategy signals. The `fillna()` defaults must be chosen to produce "neutral" signals (no trade) rather than false signals.

---

### P0-STRAT-1: Division by zero in RSI (grid.py)

**File:** `binance-bot/src/binance_bot/strategies/grid.py:241`
```python
rs = avg_gain / avg_loss
```

**Fix:**
```python
# BEFORE:
rs = avg_gain / avg_loss
rsi = 100 - (100 / (1 + rs))

# AFTER:
rs = avg_gain / avg_loss.replace(0, np.nan)
rsi = 100 - (100 / (1 + rs))
rsi = rsi.fillna(100.0)  # no losses = RSI 100
```

**Test:** Same pattern as P0-CORE-4 RSI test.

**Risk:** Low. When `avg_loss=0`, RSI should logically be 100 (maximum bullish).

---

### P0-STRAT-2: Division by zero in ADX (grid.py)

**File:** `binance-bot/src/binance_bot/strategies/grid.py:291`
```python
dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
```

**Fix:**
```python
# BEFORE:
dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))

# AFTER:
di_sum = (plus_di + minus_di).replace(0, np.nan)
dx = 100 * ((plus_di - minus_di).abs() / di_sum)
dx = dx.fillna(0.0)
```

**Test:** Same pattern as P0-CORE-4 ADX test.

**Risk:** Low. When both DI are zero, ADX=0 (no trend) is the correct interpretation.

---

## Phase 3: Shared Service Fixes

### P0-AI-1: ZeroDivisionError when `best_bid=0`

**File:** `shared/ai/agent.py:158`
```python
spread = ((best_ask - best_bid) / best_bid) * 100
```

**Fix:**
```python
# BEFORE:
spread = ((best_ask - best_bid) / best_bid) * 100

# AFTER:
spread = ((best_ask - best_bid) / best_bid) * 100 if best_bid > 0 else 0.0
```

**Test:**
```python
def test_spread_calculation_zero_bid():
    """Spread calc doesn't crash when best_bid=0."""
    # Call the method with best_bid=0 in market_data
    result = agent.analyze_market(symbol="TEST", current_price=100, best_bid=0, best_ask=100, ...)
    # Should not raise ZeroDivisionError
```

**Risk:** Very low. Empty order book is an edge case; defaulting spread to 0 is safe.

---

### P0-AI-2: Module-level `TradingAgent()` crashes without env vars

**File:** `shared/ai/agent.py:470`
```python
trading_agent = TradingAgent()  # runs at import time
```

**Fix:**
```python
# BEFORE:
trading_agent = TradingAgent()

# AFTER:
_trading_agent = None

def get_trading_agent() -> TradingAgent:
    """Lazy factory for TradingAgent singleton."""
    global _trading_agent
    if _trading_agent is None:
        _trading_agent = TradingAgent()
    return _trading_agent

# Keep backward-compatible name for existing imports
class _LazyAgent:
    def __getattr__(self, name):
        return getattr(get_trading_agent(), name)

trading_agent = _LazyAgent()
```

**Update callers:** Search for `from shared.ai.agent import trading_agent` — these still work via `_LazyAgent` proxy.

**Test:**
```python
def test_agent_module_importable_without_env(monkeypatch):
    """shared.ai.agent can be imported without OpenRouter key."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    import importlib, shared.ai.agent
    importlib.reload(shared.ai.agent)
    # Should not raise
```

**Risk:** Low. The lazy proxy preserves the existing API. Only difference: instantiation deferred to first use.

---

### P0-ALERT-1: Fragile `co_varnames` in `AlertConfig.from_dict`

**File:** `shared/alerts/manager.py:67`
```python
return cls(**{k: v for k, v in data.items() if k in cls.__init__.__code__.co_varnames})
```

**Fix:**
```python
import inspect

# BEFORE:
return cls(**{k: v for k, v in data.items() if k in cls.__init__.__code__.co_varnames})

# AFTER:
valid_params = set(inspect.signature(cls.__init__).parameters.keys()) - {"self"}
return cls(**{k: v for k, v in data.items() if k in valid_params})
```

**Test:**
```python
def test_alert_config_from_dict_ignores_extra_keys():
    data = {"enabled": True, "unknown_key": "value", "discord_webhook_url": "http://test"}
    config = AlertConfig.from_dict(data)
    assert config.enabled is True

def test_alert_config_from_dict_with_all_valid_keys():
    params = inspect.signature(AlertConfig.__init__).parameters
    data = {k: None for k in params if k != "self"}
    config = AlertConfig.from_dict(data)  # should not raise
```

**Risk:** Very low. `inspect.signature` is the standard, stable way to introspect parameters.

---

### P0-ALERT-2: Invalid `daily_summary_time` causes infinite error loop

**File:** `shared/alerts/manager.py:414`
```python
target_hour, target_minute = map(int, self.config.daily_summary_time.split(":"))
```

**Fix — validation in AlertConfig.__init__ or __post_init__:**
```python
# Add validation to AlertConfig (near line 30-60):
def __post_init__(self):
    # Validate daily_summary_time format
    try:
        parts = self.daily_summary_time.split(":")
        if len(parts) != 2:
            raise ValueError
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError
    except (ValueError, AttributeError):
        self.daily_summary_time = "20:00"  # safe default
```

**Fix — defensive parse in _daily_summary_loop (line 414):**
```python
# BEFORE:
target_hour, target_minute = map(int, self.config.daily_summary_time.split(":"))

# AFTER:
try:
    parts = self.config.daily_summary_time.split(":")
    target_hour, target_minute = int(parts[0]), int(parts[1])
except (ValueError, IndexError):
    target_hour, target_minute = 20, 0  # fallback
```

**Test:**
```python
def test_alert_config_invalid_summary_time():
    config = AlertConfig(daily_summary_time="invalid")
    assert config.daily_summary_time == "20:00"

def test_alert_config_valid_summary_time():
    config = AlertConfig(daily_summary_time="18:30")
    assert config.daily_summary_time == "18:30"

def test_alert_config_three_part_time():
    config = AlertConfig(daily_summary_time="20:00:00")
    assert config.daily_summary_time == "20:00"  # normalized
```

**Risk:** Low. Invalid config gets a safe default instead of infinite crash loop.

---

### P0-RISK-1: `NameError` in `get_pnl_summary()` — `total_cost_buys` undefined

**File:** `shared/api/routes/trades.py:107-142`
**Problem:** Variables `total_cost_buys` and `total_amount_buys` are defined inside an `else` block but referenced unconditionally at line 141.

**Fix:**
```python
# Initialize before the if/else branches:
total_cost_buys = 0.0
total_cost_sells = 0.0
total_amount_buys = 0.0
total_amount_sells = 0.0

# Then the existing if/else logic works correctly
```

**Test:**
```python
def test_get_pnl_summary_with_trade_logs():
    """No NameError when TradeLog records exist."""
    # Insert a TradeLog record, then call get_pnl_summary
    response = client.get("/api/trades/pnl-summary?symbol=BTC/USDT")
    assert response.status_code == 200

def test_get_pnl_summary_empty():
    """Works with no trade records."""
    response = client.get("/api/trades/pnl-summary?symbol=NONE/NONE")
    assert response.status_code == 200
```

**Risk:** Very low. Just variable initialization — no behavior change for the existing `else` path.

---

### P0-RISK-2: ZeroDivisionError in `position_sizer` when `entry_price=0`

**File:** `shared/risk/position_sizer.py` — 7 locations (lines 88, 94, 111, 117, 155, 200, 206)
```python
amount_base = amount_usd / entry_price  # entry_price can be 0
```

**Fix — add guard at the top of `calculate()` method:**
```python
def calculate(self, entry_price: float, ...) -> PositionSize:
    # ADDED: guard against zero/negative entry price
    if entry_price <= 0:
        raise ValueError(f"entry_price must be positive, got {entry_price}")
    if portfolio_value <= 0:
        raise ValueError(f"portfolio_value must be positive, got {portfolio_value}")

    # ... rest of method unchanged
```

**Test:**
```python
def test_position_sizer_zero_entry_price():
    sizer = PositionSizer()
    with pytest.raises(ValueError, match="entry_price must be positive"):
        sizer.calculate(entry_price=0, portfolio_value=10000)

def test_position_sizer_negative_entry_price():
    sizer = PositionSizer()
    with pytest.raises(ValueError, match="entry_price must be positive"):
        sizer.calculate(entry_price=-1, portfolio_value=10000)

def test_position_sizer_valid():
    sizer = PositionSizer()
    result = sizer.calculate(entry_price=50000, portfolio_value=10000)
    assert result.amount_base > 0
```

**Risk:** Low. Callers should already have a valid price. If they don't, a clear error is better than a cryptic `ZeroDivisionError`.

---

### P0-BACK-1: `float('inf')` in profit_factor crashes JSON serialization

**Files:**
- `shared/backtest/engine.py:356`
- `shared/optimization/metrics.py:122`

```python
profit_factor = float("inf") if gross_profit > 0 else 0.0
```

**Fix:**
```python
# BEFORE (engine.py:356):
profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)

# AFTER:
profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (9999.99 if gross_profit > 0 else 0.0)

# BEFORE (metrics.py:122):
return float("inf") if gross_profit > 0 else 0.0

# AFTER:
return 9999.99 if gross_profit > 0 else 0.0
```

**Test:**
```python
import json

def test_backtest_results_json_serializable():
    """Backtest results with all-winning trades don't produce inf."""
    results = run_backtest(...)  # all winning trades
    json.dumps(results)  # must not raise ValueError

def test_profit_factor_capped():
    """profit_factor is finite even with zero losses."""
    pf = calculate_profit_factor(gross_profit=1000, gross_loss=0)
    assert pf == 9999.99
    assert json.dumps({"pf": pf})  # JSON-safe
```

**Risk:** Very low. `9999.99` is an effectively infinite profit factor. No strategy logic should depend on `float('inf')`.

---

### P0-VDB-1: Timezone mismatch in `news_fetcher.py` sort

**File:** `shared/vector_db/news_fetcher.py:242-243`
```python
articles.sort(key=lambda a: a.published_at or datetime.min, reverse=True)
```

**Fix:**
```python
# BEFORE:
articles.sort(key=lambda a: a.published_at or datetime.min, reverse=True)

# AFTER:
from datetime import timezone
_DATETIME_MIN_UTC = datetime.min.replace(tzinfo=timezone.utc)
articles.sort(key=lambda a: a.published_at or _DATETIME_MIN_UTC, reverse=True)
```

**Test:**
```python
from datetime import datetime, timezone

def test_news_sort_mixed_timezone():
    """Sorting articles with None published_at doesn't raise TypeError."""
    articles = [
        Article(published_at=datetime.now(timezone.utc)),
        Article(published_at=None),
    ]
    articles.sort(key=lambda a: a.published_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    assert articles[0].published_at is not None
```

**Risk:** Very low. Only affects sort order for articles with `None` published_at.

---

### P0-VDB-2: Timezone mismatch in `sentiment.py` comparison

**File:** `shared/vector_db/sentiment.py:169-170`
```python
pub_dt = datetime.fromisoformat(pub_str)
if pub_dt < cutoff:  # TypeError if naive vs aware
```

**Fix:**
```python
# BEFORE:
pub_dt = datetime.fromisoformat(pub_str)
if pub_dt < cutoff:

# AFTER:
pub_dt = datetime.fromisoformat(pub_str)
if pub_dt.tzinfo is None:
    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
if pub_dt < cutoff:
```

**Test:**
```python
def test_sentiment_naive_datetime_comparison():
    """Sentiment handles naive datetime strings without TypeError."""
    # Create a sentiment entry with naive datetime string
    result = analyze_sentiment(articles=[{"published_at": "2026-03-10T12:00:00"}])
    # Should not raise TypeError
```

**Risk:** Very low. Assuming UTC for naive timestamps is the safest interpretation for this use case (news articles).

---

## Phase 4: Bot & Strategy Fixes

### P0-BOT-1: `asyncio.get_event_loop()` deprecated

**File:** `binance-bot/src/binance_bot/bot.py:991`
```python
loop = asyncio.get_event_loop()
```

**Fix:**
```python
# BEFORE:
loop = asyncio.get_event_loop()

def signal_handler():
    asyncio.create_task(bot.stop())

loop.add_signal_handler(signal.SIGINT, signal_handler)
loop.add_signal_handler(signal.SIGTERM, signal_handler)
loop.run_until_complete(bot.start())

# AFTER:
async def main():
    loop = asyncio.get_running_loop()

    def signal_handler():
        asyncio.create_task(bot.stop())

    loop.add_signal_handler(signal.SIGINT, signal_handler)
    loop.add_signal_handler(signal.SIGTERM, signal_handler)
    await bot.start()

asyncio.run(main())
```

**Test:**
```python
import asyncio

def test_bot_uses_asyncio_run(monkeypatch):
    """Bot entrypoint uses asyncio.run() instead of deprecated get_event_loop()."""
    import ast, inspect
    source = inspect.getsource(run_bot)  # or read bot.py
    tree = ast.parse(source)
    # Check no get_event_loop calls exist
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "get_event_loop":
            pytest.fail("Found deprecated asyncio.get_event_loop()")
```

**Risk:** Medium. This changes the bot's entrypoint. Must test that signal handling still works correctly in Docker. The `asyncio.run()` pattern creates a new event loop, which is correct.

---

### P0-BOT-2: Unhandled network error during startup

**File:** `binance-bot/src/binance_bot/bot.py:286`
```python
await self._check_entry_conditions()  # outside main loop try/except
```

**Fix:**
```python
# BEFORE:
await self._check_entry_conditions()

# AFTER:
try:
    await self._check_entry_conditions()
except Exception as e:
    logger.warning(f"Initial entry check failed (will retry in main loop): {e}")
```

**Test:**
```python
@pytest.mark.asyncio
async def test_bot_start_survives_network_error(mocker):
    """Bot start() doesn't crash if initial market check fails."""
    mocker.patch.object(bot, '_check_entry_conditions', side_effect=ccxt.NetworkError("timeout"))
    # Should not raise — bot should continue to main loop
    await bot.start()
```

**Risk:** Low. The main loop will retry market checks. Startup failure is non-critical.

---

### P0-BOT-3: `ticker["last"]` can be `None`

**File:** `binance-bot/src/binance_bot/bot.py:296,468`

**Fix at line 468 (main loop — most critical):**
```python
# BEFORE:
ticker = exchange_client.get_ticker(self.symbol)
current_price = ticker["last"]

# AFTER:
ticker = exchange_client.get_ticker(self.symbol)
current_price = ticker.get("last") or ticker.get("close") or 0.0
if current_price <= 0:
    logger.warning(f"Invalid price from ticker: {ticker}")
    await asyncio.sleep(tick_interval)
    continue
```

**Fix at line 296 (startup alert — less critical):**
```python
# BEFORE:
current_price=ticker["last"],

# AFTER:
current_price=ticker.get("last", 0),
```

**Test:**
```python
@pytest.mark.asyncio
async def test_bot_handles_none_ticker_last(mocker):
    """Bot handles None ticker['last'] gracefully."""
    mocker.patch.object(exchange_client, 'get_ticker', return_value={"last": None, "close": 50000})
    # Main loop should use close price as fallback
```

**Risk:** Low. Adding null-safety to an existing field access. The `continue` skips one iteration instead of crashing.

---

### P0-BOT-4: `_print_stats()` KeyError on `paper_trading`

**File:** `binance-bot/src/binance_bot/bot.py:803`
```python
paper = status["paper_trading"]
```

**Fix:**
```python
# BEFORE:
paper = status["paper_trading"]

# AFTER:
paper = status.get("paper_trading", {})
```

**Test:**
```python
def test_print_stats_missing_paper_trading(mocker):
    """_print_stats doesn't crash when paper_trading key is missing."""
    mocker.patch.object(strategy, 'get_status', return_value={"grid": {}})
    bot._print_stats()  # should not raise KeyError
```

**Risk:** Very low. Simple defensive access.

---

### P0-STRAT-3: Division by zero when `num_levels=0`

**File:** `binance-bot/src/binance_bot/strategies/ai_grid.py:180,183`
```python
spacing_pct = (price_range / opt.num_levels) / current_price * 100  # line 180
self.config.grid_levels = opt.num_levels // 2                        # line 183
```

**Fix:**
```python
# BEFORE:
price_range = opt.upper_price - opt.lower_price
spacing_pct = (price_range / opt.num_levels) / current_price * 100
self.config.grid_levels = opt.num_levels // 2

# AFTER:
price_range = opt.upper_price - opt.lower_price
if opt.num_levels < 2:
    logger.warning(f"AI returned num_levels={opt.num_levels}, using default grid")
    self.setup_grid(current_price)
    return
spacing_pct = (price_range / opt.num_levels) / current_price * 100
self.config.grid_levels = max(1, opt.num_levels // 2)
```

**Test:**
```python
def test_apply_optimization_zero_levels(ai_grid):
    """_apply_optimization handles num_levels=0 without crash."""
    ai_grid.last_optimization = Optimization(num_levels=0, upper_price=51000, lower_price=49000)
    ai_grid._apply_optimization(current_price=50000)  # should not raise

def test_apply_optimization_one_level(ai_grid):
    ai_grid.last_optimization = Optimization(num_levels=1, upper_price=51000, lower_price=49000)
    ai_grid._apply_optimization(current_price=50000)  # should not raise
```

**Risk:** Low. AI returning `num_levels=0` is a degenerate case; falling back to default grid is safe.

---

### P0-STRAT-4: DB session leak in `_save_trade_to_db`

**File:** `binance-bot/src/binance_bot/strategies/grid.py:752-784`
```python
try:
    db = SessionLocal()
    # ... db operations ...
    db.commit()
    db.close()
except Exception as e:
    logger.warning(...)  # db.close() never called on exception
```

**Fix:**
```python
# BEFORE:
try:
    db = SessionLocal()
    # ... operations ...
    db.commit()
    db.close()
except Exception as e:
    logger.warning(f"Failed to save trade to DB: {e}")

# AFTER:
db = SessionLocal()
try:
    # ... operations ...
    db.commit()
except Exception as e:
    db.rollback()
    logger.warning(f"Failed to save trade to DB: {e}")
finally:
    db.close()
```

**Test:**
```python
def test_save_trade_closes_session_on_error(mocker):
    """DB session is closed even when commit fails."""
    mock_session = mocker.MagicMock()
    mock_session.commit.side_effect = Exception("DB error")
    mocker.patch('binance_bot.strategies.grid.SessionLocal', return_value=mock_session)

    grid._save_trade_to_db(signal, is_short=False, abs_amount=0.1, cost=5000)

    mock_session.rollback.assert_called_once()
    mock_session.close.assert_called_once()
```

**Risk:** Very low. Standard try/except/finally pattern for DB sessions.

---

### P0-STRAT-5: Bare `except:` swallows SystemExit

**File:** `binance-bot/src/binance_bot/core/order_manager.py:272`
```python
except:
    pass
```

**Fix:**
```python
# BEFORE:
except:
    pass

# AFTER:
except Exception as e:
    logger.warning(f"Failed to fetch order status for {order_id}: {e}")
```

**Test:**
```python
def test_bare_except_not_in_order_manager():
    """order_manager.py has no bare except clauses."""
    import ast
    with open("binance-bot/src/binance_bot/core/order_manager.py") as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            pytest.fail(f"Bare except at line {node.lineno}")
```

**Risk:** Very low. `Exception` still catches all runtime errors but not `SystemExit`/`KeyboardInterrupt`.

---

### P0-STRAT-6: Missing rollback on DB commit failure

**File:** `binance-bot/src/binance_bot/core/order_manager.py:308-326`
```python
try:
    session.commit()
finally:
    session.close()  # no rollback on failure
```

**Fix:**
```python
# BEFORE:
try:
    session.add(trade)
    session.commit()
finally:
    session.close()

# AFTER:
try:
    session.add(trade)
    session.commit()
except Exception:
    session.rollback()
    raise
finally:
    session.close()
```

**Test:**
```python
def test_save_trade_rollback_on_commit_failure(mocker):
    """Session is rolled back when commit fails."""
    mock_session = mocker.MagicMock()
    mock_session.commit.side_effect = Exception("integrity error")
    mocker.patch('binance_bot.core.order_manager.get_session', return_value=mock_session)

    with pytest.raises(Exception):
        order_manager._save_trade(mock_order)

    mock_session.rollback.assert_called_once()
    mock_session.close.assert_called_once()
```

**Risk:** Very low. Adding rollback ensures DB consistency on failure.

---

## Phase 5: Jesse Bot Fixes

### P0-JESSE-1: Wrong candle column index (HIGH vs CLOSE)

**File:** `jesse-bot/strategies/AIGridStrategy/__init__.py:357,360`
```python
closes = list(candles_4h[:, 2])  # column 2 is HIGH, not CLOSE
```

**Fix:**
```python
# BEFORE (line 357):
closes = list(candles_4h[:, 2])

# AFTER:
closes = list(candles_4h[:, 4])  # Jesse format: [timestamp, open, high, low, close, volume]

# BEFORE (line 360):
closes = list(self.candles[:, 2]) if self.candles is not None else []

# AFTER:
closes = list(self.candles[:, 4]) if self.candles is not None else []
```

**Test:**
```python
import numpy as np

def test_candle_close_column_index():
    """Close prices use column index 4, not 2."""
    # Jesse candle format: [timestamp, open, high, low, close, volume]
    candles = np.array([
        [1000, 100, 105, 95, 102, 1000],
        [2000, 102, 108, 98, 106, 1200],
    ])
    closes = list(candles[:, 4])
    assert closes == [102, 106]  # close prices, not highs [105, 108]
```

**Risk:** Medium. This changes trend detection signals. The fix is clearly correct (using close instead of high), but it will change the strategy's behavior. Requires backtesting to validate.

---

### P0-JESSE-2: `_side` accessed before assignment

**File:** `jesse-bot/strategies/AIGridStrategy/grid_logic.py:306-307`
```python
side = self._side  # _side only set in start(), not in __init__
```

**Fix:**
```python
# In TrailingStopManager.__init__ (add):
self._side = None

# In update() method (line 306-307):
# BEFORE:
side = self._side

# AFTER:
side = getattr(self, '_side', None)
if side is None:
    return None
```

**Test:**
```python
def test_trailing_stop_update_before_start():
    """update() returns None if called before start()."""
    tsm = TrailingStopManager(...)
    result = tsm.update(current_price=50000)
    assert result is None
```

**Risk:** Very low. Defensive initialization prevents `AttributeError`.

---

### P0-JESSE-3: Division by zero in RSI (factors_mixin)

**File:** `jesse-bot/strategies/AIGridStrategy/factors_mixin.py:203`
```python
rs = gain / loss  # loss can be zero
```

**Fix:**
```python
# BEFORE:
rs = gain / loss

# AFTER:
rs = gain / loss.replace(0, np.nan)
```

**Test:**
```python
def test_factors_rsi_no_losses():
    """RSI calculation handles zero losses without crash."""
    # Create DataFrame with only rising prices
    closes = pd.Series([100 + i for i in range(20)])
    # Calculate RSI — should not raise ZeroDivisionError
```

**Risk:** Low. Same pattern as P0-STRAT-1.

---

## Risk Assessment Summary

| Risk Level | Issues | Concern |
|------------|--------|---------|
| **High** | None | — |
| **Medium** | P0-BOT-1, P0-CORE-4, P0-JESSE-1 | Entrypoint change, indicator behavior change, strategy signal change |
| **Low** | P0-AI-2, P0-CORE-1, P0-STRAT-3, P0-RISK-2, P0-BOT-2, P0-BOT-3 | Lazy init proxies, default values, guard clauses |
| **Very Low** | All others | Simple null checks, `.get()`, `try/finally`, `.replace(0, nan)` |

### Key risks to watch:
1. **P0-CORE-1 (Settings lazy init):** If any module depends on `settings` being fully initialized at import time, the lazy proxy could cause import-order issues. Mitigated by using empty defaults instead.
2. **P0-CORE-4 (Indicator defaults):** `fillna()` values for indicators must produce "neutral" trading signals. Wrong defaults could produce false signals.
3. **P0-BOT-1 (asyncio.run):** The new event loop pattern must be tested in Docker with signal handling.
4. **P0-JESSE-1 (Column index):** Correcting close vs high will change all grid direction decisions in jesse-bot. Must validate with backtests.

---

## Test File Structure

```
tests/
├── test_sprint24_core.py        # P0-CORE-1,2,3 tests
├── test_sprint24_indicators.py  # P0-CORE-4, P0-STRAT-1,2 tests
├── test_sprint24_services.py    # P0-AI-1,2, P0-ALERT-1,2, P0-RISK-1,2, P0-BACK-1, P0-VDB-1,2 tests
├── test_sprint24_bot.py         # P0-BOT-1,2,3,4, P0-STRAT-3,4,5,6 tests
└── test_sprint24_jesse.py       # P0-JESSE-1,2,3 tests
```

**Estimated test count:** ~35 tests
**Estimated lines changed:** ~200 (fixes) + ~400 (tests)

---

## Checklist

- [ ] Phase 1: Foundation (P0-CORE-1, P0-CORE-2, P0-CORE-3)
- [ ] Phase 2: Indicators (P0-CORE-4, P0-STRAT-1, P0-STRAT-2)
- [ ] Phase 3: Services (P0-AI-1, P0-AI-2, P0-ALERT-1, P0-ALERT-2, P0-RISK-1, P0-RISK-2, P0-BACK-1, P0-VDB-1, P0-VDB-2)
- [ ] Phase 4: Bot & Strategies (P0-BOT-1..4, P0-STRAT-3..6)
- [ ] Phase 5: Jesse (P0-JESSE-1..3)
- [ ] All tests passing (`pytest tests/ -v`)
- [ ] Update `docs/STATUS.md`
