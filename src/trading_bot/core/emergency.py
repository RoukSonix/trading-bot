"""Emergency Stop System.

Provides emergency shutdown capability for the trading bot:
- Manual trigger via file (.emergency_stop)
- Programmatic trigger via EmergencyStop.trigger()
- Automatic position closing
- State persistence for recovery
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger


class EmergencyStop:
    """Emergency stop handler for trading bot.
    
    Monitors for emergency stop triggers and handles graceful shutdown:
    - File-based trigger (.emergency_stop in working directory)
    - Programmatic trigger via trigger() method
    - Closes all positions before stopping
    - Saves state for recovery
    """
    
    TRIGGER_FILE = Path(".emergency_stop")
    STATE_FILE = Path("data/emergency_state.json")
    
    def __init__(self, exchange_client=None, strategy=None):
        """Initialize emergency stop handler.
        
        Args:
            exchange_client: Exchange client for position management
            strategy: Trading strategy for state access
        """
        self.exchange_client = exchange_client
        self.strategy = strategy
        self._triggered = False
        self._trigger_reason: Optional[str] = None
        self._trigger_time: Optional[datetime] = None
        
        # Ensure data directory exists
        self.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    @property
    def is_triggered(self) -> bool:
        """Check if emergency stop has been triggered."""
        return self._triggered or self._check_trigger_file()
    
    def _check_trigger_file(self) -> bool:
        """Check if trigger file exists."""
        if self.TRIGGER_FILE.exists():
            reason = "File trigger detected"
            try:
                content = self.TRIGGER_FILE.read_text().strip()
                if content:
                    reason = content
            except Exception:
                pass
            
            if not self._triggered:
                self._triggered = True
                self._trigger_reason = reason
                self._trigger_time = datetime.now()
                logger.critical(f"🚨 EMERGENCY STOP FILE DETECTED: {reason}")
            
            return True
        return False
    
    def trigger(self, reason: str = "Manual trigger") -> bool:
        """Programmatically trigger emergency stop.
        
        Args:
            reason: Reason for triggering emergency stop
            
        Returns:
            True if successfully triggered
        """
        if self._triggered:
            logger.warning("Emergency stop already triggered")
            return False
        
        self._triggered = True
        self._trigger_reason = reason
        self._trigger_time = datetime.now()
        
        logger.critical(f"🚨 EMERGENCY STOP TRIGGERED: {reason}")
        
        # Create trigger file for persistence
        try:
            self.TRIGGER_FILE.write_text(f"{reason}\nTriggered at: {self._trigger_time.isoformat()}")
        except Exception as e:
            logger.error(f"Failed to create trigger file: {e}")
        
        return True
    
    async def close_all_positions(self) -> dict:
        """Close all open positions.
        
        Returns:
            Dict with closed positions and results
        """
        results = {
            "success": False,
            "positions_closed": [],
            "errors": [],
            "timestamp": datetime.now().isoformat(),
        }
        
        if not self.exchange_client:
            logger.warning("No exchange client - cannot close positions")
            results["errors"].append("No exchange client configured")
            return results
        
        logger.warning("🛑 Closing all open positions...")
        
        try:
            # Get open positions from exchange
            positions = []
            
            # Try to get positions from exchange
            if hasattr(self.exchange_client, 'get_positions'):
                positions = self.exchange_client.get_positions()
            elif hasattr(self.exchange_client, 'fetch_positions'):
                positions = self.exchange_client.fetch_positions()
            
            for position in positions:
                symbol = position.get('symbol', 'UNKNOWN')
                amount = float(position.get('amount', 0) or position.get('contracts', 0))
                side = position.get('side', 'long')
                
                if abs(amount) < 1e-8:
                    continue
                
                try:
                    # Determine closing side
                    close_side = 'sell' if side == 'long' or amount > 0 else 'buy'
                    close_amount = abs(amount)
                    
                    logger.info(f"Closing position: {close_side} {close_amount} {symbol}")
                    
                    # Execute market order to close
                    if hasattr(self.exchange_client, 'create_market_order'):
                        order = self.exchange_client.create_market_order(
                            symbol, close_side, close_amount
                        )
                    elif hasattr(self.exchange_client, 'place_order'):
                        order = self.exchange_client.place_order(
                            symbol=symbol,
                            side=close_side,
                            order_type='market',
                            amount=close_amount,
                        )
                    else:
                        logger.error(f"Cannot close position - no order method available")
                        results["errors"].append(f"No order method for {symbol}")
                        continue
                    
                    results["positions_closed"].append({
                        "symbol": symbol,
                        "side": close_side,
                        "amount": close_amount,
                        "order_id": order.get('id', 'unknown'),
                    })
                    
                    logger.info(f"✅ Closed position: {symbol}")
                    
                except Exception as e:
                    error_msg = f"Failed to close {symbol}: {e}"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)
            
            # Also handle paper trading positions if strategy exists
            if self.strategy and hasattr(self.strategy, 'paper_holdings'):
                holdings = getattr(self.strategy, 'paper_holdings', 0)
                if holdings > 0:
                    logger.info(f"Paper trading: would close {holdings} holdings")
                    results["positions_closed"].append({
                        "symbol": "PAPER",
                        "type": "paper_trading",
                        "amount": holdings,
                    })
            
            results["success"] = len(results["errors"]) == 0
            
        except Exception as e:
            error_msg = f"Error closing positions: {e}"
            logger.error(error_msg)
            results["errors"].append(error_msg)
        
        return results
    
    def save_state(self, additional_state: Optional[dict] = None) -> bool:
        """Save current state for recovery.
        
        Args:
            additional_state: Additional state data to save
            
        Returns:
            True if state saved successfully
        """
        state = {
            "triggered": self._triggered,
            "trigger_reason": self._trigger_reason,
            "trigger_time": self._trigger_time.isoformat() if self._trigger_time else None,
            "saved_at": datetime.now().isoformat(),
        }
        
        # Add strategy state if available
        if self.strategy:
            try:
                if hasattr(self.strategy, 'get_status'):
                    state["strategy_status"] = self.strategy.get_status()
                if hasattr(self.strategy, 'paper_holdings'):
                    state["paper_holdings"] = self.strategy.paper_holdings
                if hasattr(self.strategy, 'paper_balance'):
                    state["paper_balance"] = self.strategy.paper_balance
            except Exception as e:
                logger.error(f"Failed to save strategy state: {e}")
        
        # Add any additional state
        if additional_state:
            state["additional"] = additional_state
        
        try:
            self.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.STATE_FILE.write_text(json.dumps(state, indent=2, default=str))
            logger.info(f"💾 Emergency state saved to {self.STATE_FILE}")
            return True
        except Exception as e:
            logger.error(f"Failed to save emergency state: {e}")
            return False
    
    def clear(self) -> bool:
        """Clear emergency stop state and trigger file.
        
        Returns:
            True if cleared successfully
        """
        self._triggered = False
        self._trigger_reason = None
        self._trigger_time = None
        
        try:
            if self.TRIGGER_FILE.exists():
                self.TRIGGER_FILE.unlink()
                logger.info("🗑️ Emergency trigger file removed")
            return True
        except Exception as e:
            logger.error(f"Failed to clear trigger file: {e}")
            return False
    
    def get_status(self) -> dict:
        """Get current emergency stop status.
        
        Returns:
            Dict with current status
        """
        return {
            "triggered": self.is_triggered,
            "reason": self._trigger_reason,
            "trigger_time": self._trigger_time.isoformat() if self._trigger_time else None,
            "trigger_file_exists": self.TRIGGER_FILE.exists(),
        }


# Convenience function for quick emergency stop
def emergency_stop(reason: str = "Quick stop") -> EmergencyStop:
    """Create and trigger an emergency stop.
    
    Usage:
        from trading_bot.core.emergency import emergency_stop
        emergency_stop("Market crash detected")
    """
    es = EmergencyStop()
    es.trigger(reason)
    return es
