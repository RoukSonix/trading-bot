"""
State Provider - Exports Jesse bot state as JSON for dashboard/API consumption.

Writes bot state to data/jesse_state.json using atomic file operations.
Can be called from strategy after() hook at configurable intervals.
"""

import json
import os
import tempfile
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default state file path
DEFAULT_STATE_FILE = Path("data/jesse_state.json")


def get_bot_state(strategy) -> dict:
    """Extract current bot state from a Jesse strategy instance.

    Args:
        strategy: AIGridStrategy instance (or any Jesse Strategy subclass)

    Returns:
        Dict with: grid_levels, position, balance, pnl, factors,
                   sentiment, last_ai_analysis, trailing_stop_status
    """
    state = {
        "bot": "jesse",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol": getattr(strategy, 'symbol', 'BTC-USDT'),
        "exchange": getattr(strategy, 'exchange', 'Binance Perpetual Futures'),
    }

    # Balance and equity
    try:
        state["balance"] = strategy.balance
        state["available_margin"] = getattr(strategy, 'available_margin', strategy.balance)
    except Exception:
        state["balance"] = 0.0
        state["available_margin"] = 0.0

    # Current price
    try:
        state["current_price"] = strategy.price
    except Exception:
        state["current_price"] = None

    # Position info
    try:
        pos = strategy.position
        if pos.is_open:
            state["position"] = {
                "is_open": True,
                "side": "long" if strategy.is_long else "short",
                "qty": abs(pos.qty),
                "entry_price": pos.entry_price,
                "current_price": strategy.price,
                "pnl": pos.pnl,
                "pnl_pct": pos.pnl_percentage,
            }
        else:
            state["position"] = {"is_open": False}
    except Exception:
        state["position"] = {"is_open": False}

    # Grid levels from GridManager
    try:
        gm = strategy.vars.get('grid_manager')
        if gm is not None and hasattr(gm, 'levels'):
            state["grid_levels"] = [
                {
                    "price": lvl.get("price", lvl) if isinstance(lvl, dict) else getattr(lvl, 'price', lvl),
                    "side": lvl.get("side", "unknown") if isinstance(lvl, dict) else getattr(lvl, 'side', 'unknown'),
                    "filled": lvl.get("filled", False) if isinstance(lvl, dict) else getattr(lvl, 'filled', False),
                }
                for lvl in gm.levels
            ]
            state["grid_direction"] = getattr(gm, 'direction', 'both')
        else:
            state["grid_levels"] = []
            state["grid_direction"] = "both"
    except Exception:
        state["grid_levels"] = []
        state["grid_direction"] = "both"

    # Factors
    try:
        factors = strategy.vars.get('last_factors')
        if factors is not None:
            state["factors"] = _safe_serialize(factors)
        else:
            state["factors"] = None
    except Exception:
        state["factors"] = None

    # Sentiment
    try:
        sentiment = strategy.vars.get('last_sentiment')
        if sentiment is not None:
            state["sentiment"] = _safe_serialize(sentiment)
        else:
            state["sentiment"] = None
    except Exception:
        state["sentiment"] = None

    # Last AI analysis
    try:
        analysis = strategy.vars.get('last_ai_analysis')
        if analysis is not None:
            state["last_ai_analysis"] = _safe_serialize(analysis)
        else:
            state["last_ai_analysis"] = None
    except Exception:
        state["last_ai_analysis"] = None

    # Trailing stop status
    try:
        tsm = strategy.vars.get('trailing_stop')
        if tsm is not None:
            state["trailing_stop"] = {
                "active": getattr(tsm, 'active', False),
                "stop_price": getattr(tsm, 'stop_price', None),
                "highest_price": getattr(tsm, 'highest_price', None),
                "lowest_price": getattr(tsm, 'lowest_price', None),
            }
        else:
            state["trailing_stop"] = None
    except Exception:
        state["trailing_stop"] = None

    # Candle count
    state["candle_count"] = strategy.vars.get('candle_count', 0)

    return state


def get_trade_history(strategy, limit: int = 50) -> list:
    """Get recent trade history from Jesse strategy.

    Args:
        strategy: AIGridStrategy instance
        limit: Max number of trades to return

    Returns:
        List of trade dicts with: symbol, side, entry_price, exit_price,
                                  pnl, pnl_pct, qty, opened_at, closed_at
    """
    trades = []
    try:
        closed_trades = getattr(strategy, 'trades', [])
        for trade in closed_trades[-limit:]:
            trades.append({
                "symbol": getattr(trade, 'symbol', 'BTC-USDT'),
                "side": getattr(trade, 'type', 'unknown'),
                "entry_price": getattr(trade, 'entry_price', 0.0),
                "exit_price": getattr(trade, 'exit_price', 0.0),
                "pnl": getattr(trade, 'pnl', 0.0),
                "pnl_pct": getattr(trade, 'pnl_percentage', 0.0),
                "qty": abs(getattr(trade, 'qty', 0.0)),
                "opened_at": str(getattr(trade, 'opened_at', '')),
                "closed_at": str(getattr(trade, 'closed_at', '')),
            })
    except Exception as e:
        logger.warning(f"Failed to get trade history: {e}")

    return trades


def write_state(state: dict, path: Optional[Path] = None) -> None:
    """Write state dict to JSON file atomically.

    Uses write-to-temp-then-rename for atomicity.

    Args:
        state: State dictionary to write
        path: Output file path (default: data/jesse_state.json)
    """
    path = Path(path) if path else DEFAULT_STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=".jesse_state_",
        suffix=".tmp",
    )

    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(state, f, indent=2, default=str)
        os.replace(temp_path, path)
    except Exception:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def export_state(strategy, path: Optional[Path] = None) -> dict:
    """Convenience: get state + trade history and write to file.

    Args:
        strategy: AIGridStrategy instance
        path: Output file path (optional)

    Returns:
        The full state dict that was written
    """
    state = get_bot_state(strategy)
    state["trade_history"] = get_trade_history(strategy)

    write_state(state, path)
    logger.debug(f"Jesse state exported to {path or DEFAULT_STATE_FILE}")
    return state


def _safe_serialize(obj):
    """Convert obj to JSON-safe types (handle numpy, inf, nan)."""
    if isinstance(obj, dict):
        return {k: _safe_serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_serialize(v) for v in obj]
    if isinstance(obj, float):
        if obj != obj:  # NaN
            return None
        if obj == float('inf') or obj == float('-inf'):
            return None
        return obj
    # Handle numpy types
    type_name = type(obj).__name__
    if 'int' in type_name and hasattr(obj, 'item'):
        return int(obj)
    if 'float' in type_name and hasattr(obj, 'item'):
        val = float(obj)
        if val != val or val == float('inf') or val == float('-inf'):
            return None
        return val
    return obj
