"""Grid Trading Strategy.

Grid trading places buy orders below the current price and sell orders above it.
When price moves and hits a level, it triggers a trade and creates a new level
on the opposite side to capture the reversal.

Works best in sideways/ranging markets with clear support and resistance.
"""

from dataclasses import dataclass, field
from typing import Optional
import time
import pandas as pd
from loguru import logger

from binance_bot.strategies.base import BaseStrategy, Signal, SignalType, GridLevel
from shared.core.database import SessionLocal, Trade, Position


@dataclass
class GridConfig:
    """Grid strategy configuration."""
    
    # Grid parameters
    grid_levels: int = 10           # Number of grid levels on each side
    grid_spacing_pct: float = 1.0   # Spacing between levels (%)
    
    # Position sizing
    amount_per_level: float = 0.001  # Amount to trade at each level (in base currency)
    
    # Bounds (optional - if not set, calculated from current price)
    upper_price: Optional[float] = None
    lower_price: Optional[float] = None
    
    # Risk management
    max_position: float = 0.1       # Maximum total position size
    stop_loss_pct: float = 10.0     # Stop loss percentage from entry


class GridStrategy(BaseStrategy):
    """Grid Trading Strategy implementation."""
    
    name = "GridStrategy"
    
    def __init__(
        self,
        symbol: str = "BTC/USDT",
        config: Optional[GridConfig] = None,
    ):
        """Initialize grid strategy.
        
        Args:
            symbol: Trading pair
            config: Grid configuration
        """
        super().__init__(symbol)
        self.config = config or GridConfig()
        
        # Grid state
        self.levels: list[GridLevel] = []
        self.center_price: Optional[float] = None
        self.total_position: float = 0.0
        self.realized_pnl: float = 0.0
        
        # Paper trading state
        self.paper_balance: float = 10000.0  # Starting USDT
        self.paper_holdings: float = 0.0     # BTC holdings
        self.paper_trades: list[dict] = []
    
    def setup_grid(self, current_price: float) -> list[GridLevel]:
        """Set up grid levels around current price.
        
        Args:
            current_price: Current market price
            
        Returns:
            List of grid levels
        """
        self.center_price = current_price
        self.levels = []
        
        spacing = current_price * (self.config.grid_spacing_pct / 100)
        
        # Create buy levels below current price
        for i in range(1, self.config.grid_levels + 1):
            price = current_price - (spacing * i)
            level = GridLevel(
                price=price,
                side=SignalType.BUY,
                amount=self.config.amount_per_level,
            )
            self.levels.append(level)
        
        # Create sell levels above current price
        for i in range(1, self.config.grid_levels + 1):
            price = current_price + (spacing * i)
            level = GridLevel(
                price=price,
                side=SignalType.SELL,
                amount=self.config.amount_per_level,
            )
            self.levels.append(level)
        
        # Sort by price
        self.levels.sort(key=lambda x: x.price)
        
        logger.info(f"Grid setup: {len(self.levels)} levels around ${current_price:,.2f}")
        logger.info(f"  Range: ${self.levels[0].price:,.2f} - ${self.levels[-1].price:,.2f}")
        logger.info(f"  Spacing: {self.config.grid_spacing_pct}% (${spacing:,.2f})")
        
        return self.levels
    
    def calculate_signals(self, df: pd.DataFrame, current_price: float) -> list[Signal]:
        """Check grid levels and generate signals.
        
        Args:
            df: OHLCV DataFrame (used for context, not primary signal source)
            current_price: Current market price
            
        Returns:
            List of signals for levels that should be triggered
        """
        if not self.levels:
            self.setup_grid(current_price)
            return []
        
        signals = []
        
        for level in self.levels:
            if level.filled:
                continue
            
            # Check if price crossed this level
            should_trigger = False
            
            if level.side == SignalType.BUY and current_price <= level.price:
                should_trigger = True
            elif level.side == SignalType.SELL and current_price >= level.price:
                should_trigger = True
            
            if should_trigger:
                signal = Signal(
                    type=level.side,
                    price=level.price,
                    amount=level.amount,
                    reason=f"Grid level hit at ${level.price:,.2f}",
                )
                signals.append(signal)
                level.filled = True
                
                # Create opposite level
                self._create_opposite_level(level, current_price)
        
        return signals
    
    def _create_opposite_level(self, filled_level: GridLevel, current_price: float):
        """Create opposite level after a fill.
        
        When a buy fills, create a sell above it.
        When a sell fills, create a buy below it.
        """
        spacing = current_price * (self.config.grid_spacing_pct / 100)
        
        if filled_level.side == SignalType.BUY:
            # Create sell level above
            new_price = filled_level.price + spacing
            new_level = GridLevel(
                price=new_price,
                side=SignalType.SELL,
                amount=filled_level.amount,
            )
        else:
            # Create buy level below
            new_price = filled_level.price - spacing
            new_level = GridLevel(
                price=new_price,
                side=SignalType.BUY,
                amount=filled_level.amount,
            )
        
        self.levels.append(new_level)
        self.levels.sort(key=lambda x: x.price)
    
    def execute_paper_trade(self, signal: Signal) -> dict:
        """Execute a paper trade (simulation).
        
        Args:
            signal: Trading signal to execute
            
        Returns:
            Trade result dict
        """
        cost = signal.price * signal.amount
        
        if signal.type == SignalType.BUY:
            if self.paper_balance >= cost:
                self.paper_balance -= cost
                self.paper_holdings += signal.amount
                status = "filled"
            else:
                status = "insufficient_funds"
        else:  # SELL
            if self.paper_holdings >= signal.amount:
                self.paper_balance += cost
                self.paper_holdings -= signal.amount
                status = "filled"
            else:
                status = "insufficient_holdings"
        
        trade = {
            "signal": signal,
            "status": status,
            "balance": self.paper_balance,
            "holdings": self.paper_holdings,
        }
        
        if status == "filled":
            self.paper_trades.append(trade)
            logger.info(f"Paper trade: {signal.type.value.upper()} {signal.amount:.6f} @ ${signal.price:,.2f}")
            
            # Save to database
            try:
                db = SessionLocal()
                db_trade = Trade(
                    symbol=self.symbol,
                    side=signal.type.value,
                    price=signal.price,
                    amount=signal.amount,
                    cost=cost,
                    fee=0,
                    order_id=f"paper_{int(time.time() * 1000)}",
                    timestamp=int(time.time() * 1000),
                )
                db.add(db_trade)
                
                # Update position
                position = db.query(Position).filter(Position.symbol == self.symbol).first()
                if position:
                    if signal.type == SignalType.BUY:
                        # Average entry price
                        total_cost = position.entry_price * position.amount + cost
                        position.amount += signal.amount
                        position.entry_price = total_cost / position.amount if position.amount > 0 else 0
                    else:  # SELL
                        position.realized_pnl += (signal.price - position.entry_price) * signal.amount
                        position.amount -= signal.amount
                        if position.amount <= 0:
                            position.amount = 0
                            position.entry_price = 0
                    # Use threshold to avoid floating point errors
                    position.side = "long" if position.amount > 0.00000001 else "flat"
                    if position.amount < 0.00000001:
                        position.amount = 0
                        position.entry_price = 0
                else:
                    # Create new position
                    position = Position(
                        symbol=self.symbol,
                        side="long" if signal.type == SignalType.BUY else "flat",
                        entry_price=signal.price if signal.type == SignalType.BUY else 0,
                        amount=signal.amount if signal.type == SignalType.BUY else 0,
                        unrealized_pnl=0,
                        realized_pnl=0,
                    )
                    db.add(position)
                
                db.commit()
                db.close()
            except Exception as e:
                logger.warning(f"Failed to save trade to DB: {e}")
        
        return trade
    
    def get_status(self) -> dict:
        """Get current grid status."""
        active_buys = [l for l in self.levels if l.side == SignalType.BUY and not l.filled]
        active_sells = [l for l in self.levels if l.side == SignalType.SELL and not l.filled]
        filled = [l for l in self.levels if l.filled]
        
        # Calculate paper portfolio value
        current_value = self.paper_balance
        if self.center_price and self.paper_holdings > 0:
            current_value += self.paper_holdings * self.center_price
        
        return {
            "strategy": self.name,
            "symbol": self.symbol,
            "is_active": self.is_active,
            "center_price": self.center_price,
            "total_levels": len(self.levels),
            "active_buy_levels": len(active_buys),
            "active_sell_levels": len(active_sells),
            "filled_levels": len(filled),
            "config": {
                "grid_levels": self.config.grid_levels,
                "spacing_pct": self.config.grid_spacing_pct,
                "amount_per_level": self.config.amount_per_level,
            },
            "paper_trading": {
                "balance_usdt": self.paper_balance,
                "holdings_btc": self.paper_holdings,
                "total_value": current_value,
                "trades_count": len(self.paper_trades),
            },
        }
    
    def print_grid(self):
        """Print visual representation of the grid."""
        if not self.levels:
            logger.info("Grid not initialized")
            return
        
        logger.info(f"\n{'='*50}")
        logger.info(f"Grid Status for {self.symbol}")
        logger.info(f"Center: ${self.center_price:,.2f}")
        logger.info(f"{'='*50}")
        
        for level in reversed(self.levels):  # Top to bottom
            status = "✓ FILLED" if level.filled else "○ ACTIVE"
            side = "SELL" if level.side == SignalType.SELL else "BUY "
            marker = ">>>" if level.side == SignalType.SELL else "   "
            logger.info(f"{marker} ${level.price:>10,.2f} | {side} | {status}")
        
        logger.info(f"{'='*50}")
