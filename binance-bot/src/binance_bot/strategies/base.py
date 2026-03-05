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
    
    def __repr__(self):
        status = "✓" if self.filled else "○"
        return f"<GridLevel {status} {self.side.value} @ ${self.price:,.2f}>"


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
