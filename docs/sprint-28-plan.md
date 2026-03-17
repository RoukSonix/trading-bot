# Sprint 28: Alerts, API & Data Fixes — Implementation Plan

**Date:** 2026-03-17
**Branch:** `sprint-28-alerts-api`
**Worktree:** `~/projects/CentricVoid/trading-bots-sprint-28-alerts-api/`
**Issues:** 15 (3× P1-ALERT + 4× P1-CORE + 1× P1-RISK + 1× P2-ALERT + 2× P2-API + 2× P2-RISK + 1× P2-CORE + 1× P2-BOT)
**Files to modify:** ~15 source files, 1 new test file

---

## Issue 1: P1-ALERT-1 — Naive vs aware datetime mixing

**File:** `shared/alerts/manager.py:133,157` (naive) vs `206,253,297,433` (aware)
**Bug:** `_check_rate_limit()` (line 133) and `_record_alert()` (line 157) use `datetime.now()` (naive). But `send_trade_alert()` (line 206), `send_status_alert()` (line 253), `send_error_alert()` (line 297), and `_daily_summary_loop()` (line 433) use `datetime.now(timezone.utc)` (aware). Comparing naive vs aware datetimes raises `TypeError`.

```python
# Lines 133, 157 (current)
now = datetime.now()

# Fix: use timezone-aware everywhere
now = datetime.now(timezone.utc)
```

**Test:**
- `test_rate_limit_uses_utc`: call `_check_rate_limit()` → no TypeError when comparing with aware timestamps.
- `test_record_alert_uses_utc`: call `_record_alert()` → stored timestamps are timezone-aware.

---

## Issue 2: P1-ALERT-2 — Price movement iterates wrong direction

**File:** `shared/alerts/rules.py:297-300`
**Bug:** Loop iterates `self._price_history` oldest-to-newest. The deque (line 79: `deque(maxlen=1000)`) stores oldest items on the left. The loop finds the first (oldest) price before the cutoff and breaks, instead of the most recent price before the cutoff.

```python
# Lines 297-300 (current)
for point in self._price_history:
    if point.timestamp <= cutoff:
        old_price = point.price
        break

# Fix: iterate newest-to-oldest to find most recent price before cutoff
for point in reversed(self._price_history):
    if point.timestamp <= cutoff:
        old_price = point.price
        break
```

**Test:**
- `test_price_movement_uses_recent_price`: add prices [100, 150, 200] with timestamps spanning the window → old_price should be 150 (most recent before cutoff), not 100.
- `test_price_movement_no_history`: empty history → returns None.

---

## Issue 3: P1-ALERT-3 — `send_tp_sl_alert()` not wired through AlertManager

**File:** `shared/alerts/discord.py:347-402` (method exists), `shared/alerts/manager.py` (no route)
**Bug:** `DiscordAlert.send_tp_sl_alert()` is fully implemented but `AlertManager` has no corresponding method. TP/SL alerts can only be sent by bypassing the manager's rate limiting and routing.

```python
# Fix: Add method to AlertManager (after send_custom_alert, ~line 400)
async def send_tp_sl_alert(
    self,
    event_type: str,
    symbol: str,
    level_price: float,
    exit_price: float,
    pnl: float,
    direction: str = "long",
    break_even_price: Optional[float] = None,
) -> bool:
    """Send TP/SL event alert through all configured channels."""
    if not self._check_rate_limit("tp_sl"):
        return False

    sent = False
    if self.discord:
        sent = await self.discord.send_tp_sl_alert(
            event_type=event_type,
            symbol=symbol,
            level_price=level_price,
            exit_price=exit_price,
            pnl=pnl,
            direction=direction,
            break_even_price=break_even_price,
        )
    self._record_alert("tp_sl")
    return sent
```

**Test:**
- `test_tp_sl_alert_routed_through_manager`: mock DiscordAlert → call `manager.send_tp_sl_alert()` → discord method called.
- `test_tp_sl_alert_rate_limited`: send multiple rapid TP/SL alerts → rate limiter enforced.

---

## Issue 4: P1-CORE-1 — `read_command()` TOCTOU race condition

**File:** `shared/core/state.py:169-182`
**Bug:** `path.exists()` check (line 173) followed by `open()` (line 176). File can be deleted between check and read. Also, `path.unlink()` (line 178) after read creates a second race — another reader could consume and delete between our read and unlink.

```python
# Lines 169-182 (current)
def read_command(path: Optional[Path] = None) -> Optional[str]:
    path = path or COMMAND_FILE
    path = Path(path)
    if not path.exists():        # TOCTOU: file may disappear
        return None
    try:
        with open(path, "r") as f:
            data = json.load(f)
        path.unlink()            # Race: another reader may have consumed
        return data.get("command")
    except (json.JSONDecodeError, KeyError):
        path.unlink(missing_ok=True)
        return None

# Fix: remove exists() check, handle FileNotFoundError directly
def read_command(path: Optional[Path] = None) -> Optional[str]:
    path = path or COMMAND_FILE
    path = Path(path)
    try:
        with open(path, "r") as f:
            data = json.load(f)
        path.unlink(missing_ok=True)
        return data.get("command")
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, KeyError):
        path.unlink(missing_ok=True)
        return None
```

**Test:**
- `test_read_command_file_not_found`: no command file → returns None, no exception.
- `test_read_command_valid`: write command file → reads and consumes it.
- `test_read_command_corrupt_json`: write invalid JSON → returns None, file removed.

---

## Issue 5: P1-CORE-2 — `write_command()` not atomic

**File:** `shared/core/state.py:160-166`
**Bug:** `write_command()` writes directly to the target file. A reader opening the file mid-write gets truncated/corrupt JSON, causing `JSONDecodeError`. Meanwhile, `write_state()` (same file) already uses atomic temp-file-then-rename.

```python
# Lines 160-166 (current)
def write_command(command: str, path: Optional[Path] = None) -> None:
    path = path or COMMAND_FILE
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump({"command": command, "timestamp": datetime.now().isoformat()}, f)

# Fix: use atomic write (same pattern as write_state)
import tempfile, os
def write_command(command: str, path: Optional[Path] = None) -> None:
    path = path or COMMAND_FILE
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps({"command": command, "timestamp": datetime.now(timezone.utc).isoformat()})
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(data)
        os.replace(tmp_path, str(path))
    except Exception:
        os.unlink(tmp_path)
        raise
```

**Note:** Also fixes P2-CORE-1 for this location by using `timezone.utc`.

**Test:**
- `test_write_command_atomic`: write command → file contains valid JSON (no partial writes).
- `test_write_command_creates_parent_dir`: write to nested path → directory created.

---

## Issue 6: P1-CORE-3 — `Indicators.to_dataframe()` crashes on empty candles

**File:** `shared/core/indicators.py:28-41`
**Bug:** Line 33 accesses `df["timestamp"].iloc[0]` without checking if the DataFrame is empty. Empty candle list → `IndexError`.

```python
# Line 28-33 (current)
df = pd.DataFrame(candles)

# Convert timestamp to datetime
if "timestamp" in df.columns:
    # Handle milliseconds
    if df["timestamp"].iloc[0] > 1e12:  # ← IndexError if empty

# Fix: add early return
df = pd.DataFrame(candles)
if df.empty:
    return df

# Convert timestamp to datetime
if "timestamp" in df.columns:
    if df["timestamp"].iloc[0] > 1e12:
```

**Test:**
- `test_to_dataframe_empty_candles`: pass `[]` → returns empty DataFrame, no error.
- `test_to_dataframe_empty_dicts`: pass `[{}, {}]` → returns DataFrame without crashing.
- `test_to_dataframe_valid`: pass valid candles → timestamps converted correctly.

---

## Issue 7: P1-CORE-4 — Module-level side effects in `database.py`

**File:** `shared/core/database.py:10-34`
**Bug:** On import: creates `data/` directory (line 11), connects to SQLite (lines 14-22), registers WAL pragma listener (lines 27-32), creates sessionmaker (line 34). Any `import database` has filesystem side effects, making testing/tooling require full environment setup.

```python
# Lines 10-34 (current — all at module level)
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
DATABASE_URL = f"sqlite:///{DATA_DIR}/trading.db"
engine = create_engine(DATABASE_URL, ...)
SessionLocal = sessionmaker(bind=engine)

# Fix: lazy initialization with factory function
_engine = None
_SessionLocal = None

def get_engine():
    global _engine
    if _engine is None:
        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)
        db_url = f"sqlite:///{data_dir}/trading.db"
        _engine = create_engine(db_url, echo=False, connect_args={"timeout": 30, "check_same_thread": False}, pool_pre_ping=True)

        @event.listens_for(_engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()
    return _engine

def get_session():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine())
    return _SessionLocal()
```

**VALIDATION NOTE:** All callers that reference the module-level `engine`, `SessionLocal`, or `DATABASE_URL` must be updated. Search for imports:
- `from shared.core.database import SessionLocal` → `from shared.core.database import get_session`
- `from shared.core.database import engine` → `from shared.core.database import get_engine`
- Direct `SessionLocal()` calls → `get_session()`

Confirmed callers from grep:
- `shared/api/main.py:22` — `from shared.core.database import init_db, engine as db_engine` (used on line 366 in readiness check)
- `binance-bot/src/binance_bot/strategies/grid.py:19` — `from shared.core.database import SessionLocal, Trade, Position`
- `shared/api/routes/positions.py:9` — already uses `get_session` ✅

**VALIDATION NOTE (2026-03-17):** `init_db()` (line 113) and `_auto_migrate()` (line 120) inside `database.py` itself also reference `engine` and `DATABASE_URL` at module scope. These must be updated to call `get_engine()` internally. `Base = declarative_base()` (line 35) can remain at module level — no filesystem side effects.

**Test:**
- `test_import_no_side_effects`: import database module → `data/` directory NOT created, no SQLite connection.
- `test_get_engine_lazy_init`: call `get_engine()` → engine created, WAL mode enabled.
- `test_get_session_returns_session`: call `get_session()` → returns a valid Session.

---

## Issue 8: P1-RISK-1 — Duplicate orders in API response

**File:** `shared/api/routes/orders.py:59-108`
**Bug:** `get_orders()` reads orders from the state file (lines 68-87), appends to `orders` list, then ALSO reads from the bot instance (lines 90-106) and appends to the same list. No early return after state-file block. Same orders appear twice in the response.

```python
# Lines 87-90 (current — no early return)
            orders.append(OrderResponse(...))
    # Fallback to in-process bot instance (local dev)
    bot = _get_bot()

# Fix: add early return when state data was found
            orders.append(OrderResponse(...))
    if orders:
        return OrderListResponse(orders=orders, total=len(orders))
    # Fallback to in-process bot instance (local dev)
    bot = _get_bot()
```

**Test:**
- `test_orders_no_duplicates_from_state`: mock state with orders → API returns each order exactly once.
- `test_orders_fallback_to_bot`: empty state → falls through to bot instance.

---

## Issue 9: P2-CORE-1 — `datetime.now()` without timezone (52 occurrences)

**Files:** 13 files, ~50 total occurrences (49 explicit calls + 1 default_factory)
**Bug:** Inconsistent timezone handling. Some code uses `datetime.now()` (naive), some uses `datetime.now(timezone.utc)` (aware). Cross-module comparison raises `TypeError`.

**Affected files and line counts:**
| File | Count | Lines |
|------|-------|-------|
| `binance-bot/src/binance_bot/bot.py` | 10 | 296, 368, 399, 545, 701, 713, 756, 787, 816, 865 |
| `shared/alerts/rules.py` | 7 | 58, 63, 83, 196, 224, 294, 398 |
| `shared/api/main.py` | 6 | 238, 243, 257, 333, 346, 411 |
| `shared/api/routes/candles.py` | 5 | 115, 163, 173, 188, 200 |
| `shared/api/routes/orders.py` | 4 | 85, 104, 145, 190 |
| `binance-bot/src/binance_bot/core/emergency.py` | 4 | 66, 87, 109, 208 |
| `shared/api/routes/bot.py` | 3 | 39, 52, 65 |
| `shared/core/state.py` | 2 | 75, 166 |
| `shared/alerts/manager.py` | 2 | 133, 157 |
| `shared/risk/stop_loss.py` | 3 | 39, 51 (default_factory=datetime.now), 234 |
| `shared/risk/metrics.py` | 2 | 60, 74 |
| `shared/risk/limits.py` | 1 | 164 |
| `shared/api/routes/positions.py` | 1 | 91 |

**VALIDATION NOTE (2026-03-17):** Original plan listed 52 occurrences / 13 in bot.py. Actual grep shows 49 explicit `datetime.now()` calls. Lines 882, 889, 891 in bot.py are `10000.0` defaults (P2-BOT-1), not datetime. Also `stop_loss.py:51` has `default_factory=datetime.now` (no parens) which also produces naive datetimes at runtime — added above.

**Fix:** Global find-and-replace `datetime.now()` → `datetime.now(timezone.utc)` in all locations. Ensure `from datetime import timezone` is imported where needed.

**Note:** Lines 133 and 157 in `manager.py` are already covered by Issue 1 (P1-ALERT-1). Line 166 in `state.py` is already covered by Issue 5 (P1-CORE-2). Fix once, count for both.

**Test:**
- `test_all_datetimes_timezone_aware`: grep all `.py` files for `datetime.now()` without `timezone` → zero matches.
- `test_datetime_comparison_no_type_error`: create objects from different modules → compare timestamps without TypeError.

---

## Issue 10: P2-API-3 — CORS allows all origins with credentials

**File:** `shared/api/main.py:57-63`
**Bug:** CORS middleware configured with `allow_origins=["*"]` and `allow_credentials=True`. This is both a security vulnerability and technically invalid per the CORS spec (browsers reject `*` with credentials).

```python
# Lines 57-63 (current)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Fix: restrict to known origins, read from settings
from shared.config.settings import Settings
settings = Settings()
allowed_origins = settings.cors_origins if hasattr(settings, 'cors_origins') else [
    "http://localhost:8501",   # Streamlit dashboard
    "http://localhost:3000",   # Dev frontend
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

**VALIDATION NOTE:** If `Settings()` is deferred per Issue 7 (P1-CORE-4), this needs to use the lazy-init pattern or read directly from env vars. Prefer: `os.getenv("CORS_ORIGINS", "http://localhost:8501,http://localhost:3000").split(",")`.

**Test:**
- `test_cors_rejects_unknown_origin`: request from `http://evil.com` → no CORS headers.
- `test_cors_allows_dashboard`: request from `http://localhost:8501` → proper CORS headers.

---

## Issue 11: P2-API-6 — No authentication on trading endpoints

**File:** `shared/api/routes/orders.py:111,156,201` and `shared/api/main.py`
**Bug:** Endpoints `/force-buy` (line 111), `/force-sell` (line 156), and `DELETE /{order_id}` (line 201) have zero authentication. Anyone on the network can execute trades.

```python
# Fix: Add API key dependency
# New file or add to shared/api/auth.py:
from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

async def require_api_key(api_key: str = Security(API_KEY_HEADER)) -> str:
    expected = os.getenv("TRADING_API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="API key not configured")
    if not api_key or api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key

# Then in orders.py, add dependency to write endpoints:
@router.post("/force-buy", ..., dependencies=[Depends(require_api_key)])
@router.post("/force-sell", ..., dependencies=[Depends(require_api_key)])
@router.delete("/{order_id}", ..., dependencies=[Depends(require_api_key)])
```

Also add auth to bot control endpoints in `shared/api/main.py` or `shared/api/routes/bot.py` (pause, resume, stop).

**Test:**
- `test_force_buy_requires_api_key`: POST `/force-buy` without header → 401.
- `test_force_buy_with_valid_key`: POST `/force-buy` with valid key → 200.
- `test_read_endpoints_no_auth`: GET `/orders` → 200 (no key needed).

---

## Issue 12: P2-ALERT-1 — Truthiness check on `current_price` suppresses 0.0

**File:** `shared/alerts/discord.py:226-227`
**Bug:** `if current_price:` evaluates to `False` when `current_price == 0.0`. The price field is silently omitted from the Discord embed. Same issue on line 229 with `total_value`.

```python
# Lines 226-229 (current)
if current_price:
    fields.append({"name": "Price", "value": f"${current_price:,.2f}", "inline": True})

if total_value:
    fields.append({"name": "Portfolio", "value": f"${total_value:,.2f}", "inline": True})

# Fix: explicit None check
if current_price is not None:
    fields.append({"name": "Price", "value": f"${current_price:,.2f}", "inline": True})

if total_value is not None:
    fields.append({"name": "Portfolio", "value": f"${total_value:,.2f}", "inline": True})
```

**Test:**
- `test_status_alert_price_zero`: current_price=0.0 → "Price" field present in embed.
- `test_status_alert_price_none`: current_price=None → "Price" field omitted.

---

## Issue 13: P2-RISK-1 — `trade_history` unbounded (memory leak)

**File:** `shared/risk/limits.py:81,165`
**Bug:** `trade_history: List[dict]` (line 81) grows with every `record_trade()` call (line 165: `self.trade_history.append(trade_info)`). No cleanup or bound. Long-running bot accumulates unlimited memory.

```python
# Line 81 (current)
trade_history: List[dict] = field(default_factory=list)

# Fix: use bounded deque
from collections import deque
trade_history: deque = field(default_factory=lambda: deque(maxlen=1000))
```

**Test:**
- `test_trade_history_bounded`: record 1500 trades → len(trade_history) == 1000.
- `test_trade_history_fifo`: oldest trade dropped when full.

---

## Issue 14: P2-RISK-2 — `equity_curve` unbounded (memory leak)

**File:** `shared/risk/metrics.py:39,74`
**Bug:** `equity_curve: List[tuple]` (line 39) grows with every `update_equity()` call (line 74: `self.equity_curve.append(...)`). No cleanup or bound.

```python
# Line 39 (current)
equity_curve: List[tuple] = field(default_factory=list)  # (timestamp, balance)

# Fix: use bounded deque
from collections import deque
equity_curve: deque = field(default_factory=lambda: deque(maxlen=10000))
```

**Note:** Larger maxlen (10,000) than trade_history because equity updates happen every cycle and are used for drawdown/chart calculations.

**Test:**
- `test_equity_curve_bounded`: call update_equity 15,000 times → len == 10,000.
- `test_equity_curve_preserves_recent`: most recent entries kept, oldest dropped.

---

## Issue 15: P2-BOT-1 — Hardcoded initial balance `10000.0` in 22 places

**Files:** 9 files, 22 occurrences

| File | Lines | Count |
|------|-------|-------|
| `binance-bot/src/binance_bot/bot.py` | 228, 229, 274, 329, 662, 667, 803, 831, 832, 882, 884, 889, 891 | 13 |
| `binance-bot/src/binance_bot/strategies/grid.py` | 93 | 1 |
| `shared/core/state.py` | 66, 68 | 2 |
| `shared/dashboard/app.py` | 323 | 1 |
| `shared/risk/metrics.py` | 40 | 1 |
| `shared/optimization/optimizer.py` | 26 | 1 |
| `binance-bot/scripts/run_grid_simple.py` | 104 | 1 |
| `jesse-bot/strategies/AIGridStrategy/ai_mixin.py` | 89, 197 | 2 |

**Fix:** Define constant in settings and reference everywhere.

```python
# In shared/config/settings.py — add field:
paper_initial_balance: float = Field(default=10000.0, env="PAPER_INITIAL_BALANCE")

# In shared/core/state.py — use settings default:
from shared.config.settings import Settings
_DEFAULT_BALANCE = 10000.0  # Fallback if settings not loaded
paper_balance_usdt: float = _DEFAULT_BALANCE
paper_total_value: float = _DEFAULT_BALANCE

# In bot.py — read from settings:
initial_balance = self.settings.paper_initial_balance if hasattr(self, 'settings') else 10000.0
```

**VALIDATION NOTE:** This is a large-surface change. The `10000.0` appears in many `.get("key", 10000.0)` default-value positions. Strategy: (1) add `PAPER_INITIAL_BALANCE` constant to `shared/config/settings.py`, (2) update `BotState` defaults in `state.py`, (3) update `bot.py` to read from settings/state, (4) leave scripts and jesse-bot for a later pass (lower risk).

**VALIDATION NOTE (2026-03-17):** bot.py lines 329, 662, 667, 803, 831, 832 use `10000` (int) not `10000.0` (float). Grep for both forms during implementation. Total verified: 7× `10000.0` + 6× `10000` = 13 in bot.py ✅.

**Test:**
- `test_initial_balance_from_settings`: set env `PAPER_INITIAL_BALANCE=5000` → bot uses 5000.
- `test_initial_balance_default`: no env var → defaults to 10000.

---

## Implementation Order

| Step | Issue | Risk | Dependencies |
|------|-------|------|-------------|
| 1 | P1-CORE-3 (Issue 6) | Low | None — single early return |
| 2 | P2-ALERT-1 (Issue 12) | Low | None — 2 line changes |
| 3 | P1-ALERT-2 (Issue 2) | Low | None — add `reversed()` |
| 4 | P1-ALERT-1 (Issue 1) | Low | None — 2 datetime fixes |
| 5 | P1-CORE-1 (Issue 4) | Low | None — error handling refactor |
| 6 | P1-CORE-2 (Issue 5) | Low | None — atomic write pattern |
| 7 | P1-RISK-1 (Issue 8) | Low | None — add early return |
| 8 | P1-ALERT-3 (Issue 3) | Medium | Issue 1 (manager.py same file) |
| 9 | P2-RISK-1 (Issue 13) | Low | None — list→deque |
| 10 | P2-RISK-2 (Issue 14) | Low | None — list→deque |
| 11 | P2-API-3 (Issue 10) | Medium | None — CORS config change |
| 12 | P2-API-6 (Issue 11) | Medium | None — new auth middleware |
| 13 | P1-CORE-4 (Issue 7) | High | Callers across ~6 files |
| 14 | P2-CORE-1 (Issue 9) | High | All 15+ files, 52 locations |
| 15 | P2-BOT-1 (Issue 15) | High | 9 files, 22 locations |

**Rationale:** Low-risk single-file fixes first. Medium-risk API security changes middle. High-risk cross-cutting changes last (more callers, more regression surface).

---

## Files Modified

| File | Issues | Changes |
|------|--------|---------|
| `shared/alerts/manager.py` | P1-ALERT-1, P1-ALERT-3 | datetime fix + new method (~25 lines) |
| `shared/alerts/rules.py` | P1-ALERT-2, P2-CORE-1 | reversed() + datetime fixes |
| `shared/alerts/discord.py` | P2-ALERT-1 | 2 truthiness checks |
| `shared/core/state.py` | P1-CORE-1, P1-CORE-2, P2-CORE-1 | TOCTOU fix + atomic write |
| `shared/core/indicators.py` | P1-CORE-3 | 2-line early return |
| `shared/core/database.py` | P1-CORE-4 | Lazy init refactor (~30 lines) |
| `shared/api/routes/orders.py` | P1-RISK-1, P2-API-6, P2-CORE-1 | Early return + auth |
| `shared/api/main.py` | P2-API-3, P2-CORE-1 | CORS restrict + datetime |
| `shared/api/routes/bot.py` | P2-API-6, P2-CORE-1 | Auth + datetime |
| `shared/api/routes/candles.py` | P2-CORE-1 | datetime fixes (5 locations) |
| `shared/api/routes/positions.py` | P2-CORE-1 | datetime fix (1 location) |
| `shared/risk/limits.py` | P2-RISK-1, P2-CORE-1 | list→deque + datetime |
| `shared/risk/metrics.py` | P2-RISK-2, P2-CORE-1, P2-BOT-1 | list→deque + datetime + constant |
| `shared/risk/stop_loss.py` | P2-CORE-1 | datetime fixes (2 locations) |
| `shared/config/settings.py` | P2-BOT-1 | New field: paper_initial_balance |
| `binance-bot/src/binance_bot/bot.py` | P2-CORE-1, P2-BOT-1 | datetime (13) + balance constant (13) |
| `binance-bot/src/binance_bot/core/emergency.py` | P2-CORE-1 | datetime fixes (4 locations) |
| `binance-bot/src/binance_bot/strategies/grid.py` | P2-BOT-1 | balance constant (1 location) |
| `shared/dashboard/app.py` | P2-BOT-1 | balance constant (1 location) |
| `shared/optimization/optimizer.py` | P2-BOT-1 | balance constant (1 location) |
| `shared/api/auth.py` | P2-API-6 | **New file** — API key middleware |

## Test File

`tests/unit/test_sprint28_alerts_api.py` — ~350 lines covering all 15 issues.

Test classes:
- `TestP1Alert1DatetimeMixing`
- `TestP1Alert2PriceDirection`
- `TestP1Alert3TpSlWiring`
- `TestP1Core1ReadCommandToctou`
- `TestP1Core2WriteCommandAtomic`
- `TestP1Core3EmptyCandles`
- `TestP1Core4DatabaseSideEffects`
- `TestP1Risk1DuplicateOrders`
- `TestP2Core1DatetimeTimezone`
- `TestP2Api3CorsOrigins`
- `TestP2Api6Authentication`
- `TestP2Alert1TruthinessPrice`
- `TestP2Risk1TradeHistoryBounded`
- `TestP2Risk2EquityCurveBounded`
- `TestP2Bot1HardcodedBalance`

---

## Validation (2026-03-17)

All 15 issues validated against source. Line numbers verified by reading each file.

### Line number discrepancies from AUDIT_V2.md (corrected above):
- P1-ALERT-1: audit said 120,144,416 → actual 133,157,433
- P1-CORE-1: audit said 163-176 → actual 169-182
- P1-CORE-2: audit said 154-160 → actual 160-166
- P1-CORE-4: audit said 10-32 → actual 10-34
- P2-RISK-1: audit said 81,158-162 → actual 81,161-165
- P2-BOT-1: audit said 6+ places → actual 22 occurrences across 9 files
- P2-CORE-1: audit said 30+ places → actual ~50 occurrences across 13 files

### Second-pass validation (2026-03-17, full source read)

Every source file read line-by-line. Corrections applied inline:

1. **Issue 7 (P1-CORE-4):** Added note — `init_db()` and `_auto_migrate()` inside `database.py` also need `get_engine()` internally.
2. **Issue 8 (P1-RISK-1):** Fix code had `count=len(orders)` but `OrderListResponse` uses `total` field → corrected to `total=`.
3. **Issue 9 (P2-CORE-1):** bot.py count was 13 → corrected to 10. Lines 882/889/891 are `10000.0` (P2-BOT-1), not `datetime.now()`. Added `stop_loss.py:51` `default_factory=datetime.now`. Total ~50 (not 52).
4. **Issue 15 (P2-BOT-1):** bot.py uses `10000` (int) on 6 lines and `10000.0` (float) on 7 lines — noted to grep both forms.
5. **No side effects found** in any proposed fix that would break existing behavior beyond the intended change.
6. **All other line numbers confirmed exactly** — no discrepancies in Issues 1–6, 10–14.
