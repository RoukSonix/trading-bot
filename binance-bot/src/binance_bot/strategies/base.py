"""Base strategy class."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import pandas as pd


class SignalType(Enum):
    """Trading signal types."""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class Signal:
    """Trading signal."""
    type: SignalType
    price: float
    amount: float
    reason: str
    confidence: float = 1.0  # 0-1
    
    def __repr__(self):
        return f"<Signal {self.type.value} {self.amount:.6f} @ ${self.price:,.2f} ({self.reason})>"


@dataclass
class GridLevel:
    """Grid level for grid trading strategy."""
    price: float
    side: SignalType  # BUY or SELL
    amount: float
    filled: bool = False
    order_id: Optional[str] = None
    # TP/SL fields (Sprint 21)
    take_profit: float = 0.0
    stop_loss: float = 0.0
    trailing_stop: float = 0.0       # Trailing stop distance (%)
    trailing_high: float = 0.0       # Highest price since fill (for long trailing)
    trailing_low: float = float('inf')  # Lowest price since fill (for short trailing)
    break_even_triggered: bool = False
    fill_price: float = 0.0          # Actual fill price
    fill_time: int = 0               # Fill timestamp
    pnl: float = 0.0                 # Realized P&L for this level

    def __repr__(self):
        status = "✓" if self.filled else "○"
        tp_sl = ""
        if self.take_profit > 0:
            tp_sl = f" TP=${self.take_profit:,.2f}"
        if self.stop_loss > 0:
            tp_sl += f" SL=${self.stop_loss:,.2f}"
        return f"<GridLevel {status} {self.side.value} @ ${self.price:,.2f}{tp_sl}>"


class BaseStrategy(ABC):
    """Abstract base class for trading strategies."""
    
    name: str = "BaseStrategy"
    
    def __init__(self, symbol: str = "BTC/USDT"):
        """Initialize strategy.
        
        Args:
            symbol: Trading pair
        """
        self.symbol = symbol
        self.is_active = False
    
    @abstractmethod
    def calculate_signals(self, df: pd.DataFrame, current_price: float) -> list[Signal]:
        """Calculate trading signals based on market data.
        
        Args:
            df: OHLCV DataFrame with indicators
            current_price: Current market price
            
        Returns:
            List of trading signals
        """
        pass
    
    @abstractmethod
    def get_status(self) -> dict:
        """Get current strategy status.
        
        Returns:
            Status dict with strategy-specific info
        """
        pass
    
    def start(self):
        """Start the strategy."""
        self.is_active = True
    
    def stop(self):
        """Stop the strategy."""
        self.is_active = False
