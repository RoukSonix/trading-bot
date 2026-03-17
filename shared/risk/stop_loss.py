"""Stop-loss and take-profit management."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List
from loguru import logger


class StopLossType(Enum):
    """Type of stop-loss."""
    FIXED = "fixed"              # Fixed price level
    PERCENT = "percent"          # Percentage from entry
    ATR = "atr"                  # ATR-based (volatility adjusted)
    TRAILING = "trailing"        # Trailing stop


@dataclass
class StopLevel:
    """Stop-loss or take-profit level."""
    price: float
    type: StopLossType
    triggered: bool = False
    triggered_at: Optional[datetime] = None
    
    def check(self, current_price: float, is_long: bool = True) -> bool:
        """Check if stop level is triggered."""
        if self.triggered:
            return True
            
        if is_long:
            # Long position: stop triggers below price
            triggered = current_price <= self.price
        else:
            # Short position: stop triggers above price
            triggered = current_price >= self.price
            
        if triggered:
            self.triggered = True
            self.triggered_at = datetime.now()
            
        return triggered


@dataclass
class Position:
    """Trading position with risk levels."""
    symbol: str
    entry_price: float
    amount: float
    is_long: bool = True
    entry_time: datetime = field(default_factory=datetime.now)
    
    stop_loss: Optional[StopLevel] = None
    take_profit: Optional[StopLevel] = None
    trailing_stop: Optional[float] = None  # Trailing distance
    trailing_high: Optional[float] = None  # Highest price seen (for trailing)
    
    def update_trailing(self, current_price: float):
        """Update trailing stop based on current price."""
        if self.trailing_stop is None:
            return
            
        if self.is_long:
            # Long: track highest price
            if self.trailing_high is None or current_price > self.trailing_high:
                self.trailing_high = current_price
                new_stop = current_price - self.trailing_stop
                if self.stop_loss is None or new_stop > self.stop_loss.price:
                    self.stop_loss = StopLevel(
                        price=new_stop,
                        type=StopLossType.TRAILING,
                    )
        else:
            # Short: track lowest price
            if self.trailing_high is None or current_price < self.trailing_high:
                self.trailing_high = current_price
                new_stop = current_price + self.trailing_stop
                if self.stop_loss is None or new_stop < self.stop_loss.price:
                    self.stop_loss = StopLevel(
                        price=new_stop,
                        type=StopLossType.TRAILING,
                    )


class StopLossManager:
    """Manage stop-loss and take-profit for positions."""
    
    def __init__(
        self,
        default_stop_pct: float = 0.02,    # 2% default stop-loss
        default_tp_pct: float = 0.03,       # 3% default take-profit
        use_trailing: bool = False,
        trailing_pct: float = 0.015,        # 1.5% trailing distance
        atr_multiplier: float = 2.0,        # ATR multiplier for ATR-based stops
    ):
        self.default_stop_pct = default_stop_pct
        self.default_tp_pct = default_tp_pct
        self.use_trailing = use_trailing
        self.trailing_pct = trailing_pct
        self.atr_multiplier = atr_multiplier
        
        self.positions: Dict[str, Position] = {}
        self._position_counter: int = 0

        logger.info(
            f"StopLossManager initialized: "
            f"SL={default_stop_pct*100}%, TP={default_tp_pct*100}%, "
            f"trailing={use_trailing}"
        )
    
    def add_position(
        self,
        symbol: str,
        entry_price: float,
        amount: float,
        is_long: bool = True,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        stop_type: StopLossType = StopLossType.PERCENT,
        atr: Optional[float] = None,
    ) -> Position:
        """
        Add a position with automatic stop-loss and take-profit.
        
        Args:
            symbol: Trading pair symbol
            entry_price: Entry price
            amount: Position size
            is_long: True for long, False for short
            stop_loss_price: Override stop-loss price
            take_profit_price: Override take-profit price
            stop_type: Type of stop-loss calculation
            atr: ATR value for ATR-based stops
            
        Returns:
            Position object with configured stops
        """
        # Calculate stop-loss
        if stop_loss_price:
            sl_price = stop_loss_price
        elif stop_type == StopLossType.ATR and atr:
            sl_distance = atr * self.atr_multiplier
            sl_price = entry_price - sl_distance if is_long else entry_price + sl_distance
        else:
            sl_distance = entry_price * self.default_stop_pct
            sl_price = entry_price - sl_distance if is_long else entry_price + sl_distance
        
        # Calculate take-profit
        if take_profit_price:
            tp_price = take_profit_price
        else:
            tp_distance = entry_price * self.default_tp_pct
            tp_price = entry_price + tp_distance if is_long else entry_price - tp_distance
        
        # Create position
        position = Position(
            symbol=symbol,
            entry_price=entry_price,
            amount=amount,
            is_long=is_long,
            stop_loss=StopLevel(price=sl_price, type=stop_type),
            take_profit=StopLevel(price=tp_price, type=StopLossType.FIXED),
        )
        
        # Set up trailing stop if enabled
        if self.use_trailing:
            position.trailing_stop = entry_price * self.trailing_pct
            position.trailing_high = entry_price
        
        self._position_counter += 1
        position_id = f"{symbol}_{self._position_counter}"
        self.positions[position_id] = position

        logger.info(
            f"Position added: {position_id} @ ${entry_price:.2f}, "
            f"SL=${sl_price:.2f}, TP=${tp_price:.2f}"
        )

        return position
    
    def check_position(self, symbol: str, current_price: float) -> Dict:
        """
        Check if stop-loss or take-profit is triggered for any position matching symbol.

        Returns:
            Dict with action and details (first triggered result, or no-action)
        """
        results = self.check_positions_for_symbol(symbol, current_price)
        if results:
            return results[0]
        # Check if any positions exist for this symbol
        has_positions = any(pos.symbol == symbol for pos in self.positions.values())
        if not has_positions:
            return {"action": None, "reason": "Position not found"}
        return {"action": None}

    def check_positions_for_symbol(self, symbol: str, current_price: float) -> List[Dict]:
        """Check all positions for a symbol, return list of triggered results."""
        results = []
        for pid, position in list(self.positions.items()):
            if position.symbol != symbol:
                continue

            # Update trailing stop
            if position.trailing_stop:
                position.update_trailing(current_price)

            # Check stop-loss
            if position.stop_loss and position.stop_loss.check(current_price, position.is_long):
                pnl = self._calculate_pnl(position, current_price)
                logger.warning(
                    f"🛑 STOP-LOSS triggered: {pid} @ ${current_price:.2f}, "
                    f"PnL: ${pnl:.2f}"
                )
                results.append({
                    "action": "stop_loss",
                    "position_id": pid,
                    "price": current_price,
                    "stop_price": position.stop_loss.price,
                    "pnl": pnl,
                    "position": position,
                })
                continue

            # Check take-profit
            if position.take_profit:
                is_long = position.is_long
                tp_triggered = (
                    current_price >= position.take_profit.price if is_long
                    else current_price <= position.take_profit.price
                )
                if tp_triggered:
                    position.take_profit.triggered = True
                    position.take_profit.triggered_at = datetime.now()
                    pnl = self._calculate_pnl(position, current_price)
                    logger.info(
                        f"🎯 TAKE-PROFIT triggered: {pid} @ ${current_price:.2f}, "
                        f"PnL: ${pnl:.2f}"
                    )
                    results.append({
                        "action": "take_profit",
                        "position_id": pid,
                        "price": current_price,
                        "tp_price": position.take_profit.price,
                        "pnl": pnl,
                        "position": position,
                    })
        return results
    
    def _calculate_pnl(self, position: Position, current_price: float) -> float:
        """Calculate PnL for a position."""
        if position.is_long:
            return (current_price - position.entry_price) * position.amount
        else:
            return (position.entry_price - current_price) * position.amount
    
    def remove_position(self, symbol: str):
        """Remove all positions for a symbol."""
        to_remove = [pid for pid, pos in self.positions.items() if pos.symbol == symbol]
        for pid in to_remove:
            del self.positions[pid]
        if to_remove:
            logger.info(f"Positions removed for {symbol}: {to_remove}")

    def remove_position_by_id(self, position_id: str):
        """Remove a specific position by its ID."""
        if position_id in self.positions:
            del self.positions[position_id]
            logger.info(f"Position removed: {position_id}")
    
    def get_all_positions(self) -> List[Position]:
        """Get all active positions."""
        return list(self.positions.values())
    
    def update_stop_loss(self, symbol: str, new_price: float):
        """Manually update stop-loss price for all positions matching symbol."""
        for pid, pos in self.positions.items():
            if pos.symbol == symbol:
                pos.stop_loss = StopLevel(
                    price=new_price,
                    type=StopLossType.FIXED,
                )
                logger.info(f"Stop-loss updated: {pid} → ${new_price:.2f}")

    def update_take_profit(self, symbol: str, new_price: float):
        """Manually update take-profit price for all positions matching symbol."""
        for pid, pos in self.positions.items():
            if pos.symbol == symbol:
                pos.take_profit = StopLevel(
                    price=new_price,
                    type=StopLossType.FIXED,
                )
                logger.info(f"Take-profit updated: {pid} → ${new_price:.2f}")
