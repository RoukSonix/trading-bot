"""Shared state management for Docker containers.

Provides atomic read/write of bot state via JSON file.
Allows API and bot to communicate without shared memory.
"""

import json
import os
import tempfile
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional


# Default state file path
STATE_FILE = Path("data/bot_status.json")


@dataclass
class GridLevel:
    """Grid level state."""
    price: float
    side: str
    amount: float
    filled: bool
    order_id: Optional[str] = None


@dataclass
class Position:
    """Position state."""
    symbol: str
    side: str
    amount: float
    entry_price: float
    current_price: float
    unrealized_pnl: float


@dataclass
class BotState:
    """Bot state for file-based sharing between containers."""
    
    # Core status
    status: str = "stopped"  # running, stopped, error
    state: str = "unknown"   # waiting, trading, paused
    symbol: str = "BTC/USDT"
    
    # Runtime stats
    uptime_seconds: Optional[float] = None
    ticks: int = 0
    errors: int = 0
    
    # Market data
    current_price: Optional[float] = None
    center_price: Optional[float] = None
    
    # Grid state
    grid_levels: list = field(default_factory=list)
    
    # Positions
    positions: list = field(default_factory=list)
    
    # Paper trading stats
    paper_balance_usdt: float = 10000.0
    paper_holdings_btc: float = 0.0
    paper_total_value: float = 10000.0
    paper_trades_count: int = 0
    
    # Timestamp
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "BotState":
        """Create BotState from dictionary."""
        # Handle nested objects
        grid_levels = data.pop("grid_levels", [])
        positions = data.pop("positions", [])
        
        state = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        state.grid_levels = grid_levels
        state.positions = positions
        return state


def write_state(state: BotState, path: Optional[Path] = None) -> None:
    """Write bot state to JSON file atomically.
    
    Uses write-to-temp-then-rename pattern for atomicity.
    """
    path = path or STATE_FILE
    path = Path(path)
    
    # Ensure directory exists
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write to temp file first
    fd, temp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=".bot_status_",
        suffix=".tmp"
    )
    
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(state.to_dict(), f, indent=2, default=str)
        
        # Atomic rename
        os.replace(temp_path, path)
    except Exception:
        # Clean up temp file on error
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def read_state(path: Optional[Path] = None) -> Optional[BotState]:
    """Read bot state from JSON file.
    
    Returns None if file doesn't exist or is invalid.
    """
    path = path or STATE_FILE
    path = Path(path)
    
    if not path.exists():
        return None
    
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        return BotState.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def delete_state(path: Optional[Path] = None) -> None:
    """Delete the state file."""
    path = path or STATE_FILE
    path = Path(path)
    
    if path.exists():
        path.unlink()


# ── File-based command IPC ──
COMMAND_FILE = Path("data/bot_command.json")


def write_command(command: str, path: Optional[Path] = None) -> None:
    """Write a command for the bot to pick up."""
    path = path or COMMAND_FILE
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump({"command": command, "timestamp": datetime.now().isoformat()}, f)


def read_command(path: Optional[Path] = None) -> Optional[str]:
    """Read and consume a pending command. Returns command string or None."""
    path = path or COMMAND_FILE
    path = Path(path)
    if not path.exists():
        return None
    try:
        with open(path, "r") as f:
            data = json.load(f)
        path.unlink()  # consume command
        return data.get("command")
    except (json.JSONDecodeError, KeyError):
        path.unlink(missing_ok=True)
        return None
