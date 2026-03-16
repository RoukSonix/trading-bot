"""Position and PnL tracking."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from loguru import logger

from binance_bot.core.exchange import exchange_client
from shared.core.database import get_session, Position


@dataclass
class PositionInfo:
    """Position information."""
    symbol: str
    side: str  # long/short/both/flat
    amount: float
    entry_price: float
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    realized_pnl: float = 0.0
    total_cost: float = 0.0
    short_amount: float = 0.0
    short_entry_price: float = 0.0
    
    def __repr__(self):
        return f"<Position {self.side} {self.amount:.6f} {self.symbol} @ ${self.entry_price:,.2f} PnL: ${self.unrealized_pnl:+,.2f}>"


class PositionManager:
    """Manages position tracking and PnL calculation."""
    
    def __init__(self):
        """Initialize position manager."""
        self.positions: dict[str, PositionInfo] = {}
        self.total_realized_pnl: float = 0.0
    
    def update_position(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        is_short: bool = False,
    ):
        """Update position after a trade.

        Args:
            symbol: Trading pair
            side: buy or sell
            amount: Trade amount
            price: Trade price
            is_short: Whether this is a short-side trade
        """
        if symbol not in self.positions:
            self.positions[symbol] = PositionInfo(
                symbol=symbol,
                side="flat",
                amount=0.0,
                entry_price=0.0,
            )

        pos = self.positions[symbol]

        if is_short:
            if side == "sell":
                # Open/increase short
                if pos.short_amount > 0:
                    total_cost = (pos.short_entry_price * pos.short_amount) + (price * amount)
                    pos.short_amount += amount
                    pos.short_entry_price = total_cost / pos.short_amount if pos.short_amount > 0 else 0
                else:
                    pos.short_amount = amount
                    pos.short_entry_price = price
                pos.side = "short" if pos.amount == 0 else "both"
            else:  # buy (cover short)
                if pos.short_amount >= amount:
                    pnl = (pos.short_entry_price - price) * amount
                    self.total_realized_pnl += pnl
                    pos.realized_pnl += pnl
                    pos.short_amount -= amount
                    if pos.short_amount <= 0:
                        pos.short_amount = 0
                        pos.short_entry_price = 0
                    pos.side = "long" if pos.amount > 0 else "flat"
                else:
                    logger.warning(f"Insufficient short position to cover {amount} {symbol}")
        else:
            if side == "buy":
                # Calculate new average entry price
                if pos.amount > 0:
                    total_cost = (pos.entry_price * pos.amount) + (price * amount)
                    pos.amount += amount
                    pos.entry_price = total_cost / pos.amount if pos.amount > 0 else 0
                else:
                    pos.amount = amount
                    pos.entry_price = price

                pos.side = "long" if pos.short_amount == 0 else "both"
                pos.total_cost = pos.entry_price * pos.amount

            else:  # sell
                if pos.amount >= amount:
                    # Calculate realized PnL
                    pnl = (price - pos.entry_price) * amount
                    self.total_realized_pnl += pnl
                    pos.realized_pnl += pnl
                    pos.amount -= amount

                    if pos.amount <= 0:
                        pos.side = "short" if pos.short_amount > 0 else "flat"
                        pos.amount = 0
                        pos.entry_price = 0

                    pos.total_cost = pos.entry_price * pos.amount
                else:
                    logger.warning(f"Insufficient position to sell {amount} {symbol}")
        
        # Save to database
        self._save_position(pos)
        
        logger.info(f"Position updated: {pos}")
    
    def calculate_unrealized_pnl(self, symbol: str, current_price: float) -> float:
        """Calculate unrealized PnL for a position.
        
        Args:
            symbol: Trading pair
            current_price: Current market price
            
        Returns:
            Unrealized PnL in quote currency
        """
        if symbol not in self.positions:
            return 0.0
        
        pos = self.positions[symbol]
        pos.current_price = current_price
        
        long_pnl = 0.0
        short_pnl = 0.0

        if pos.amount > 0 and pos.entry_price > 0:
            long_pnl = (current_price - pos.entry_price) * pos.amount

        if pos.short_amount > 0 and pos.short_entry_price > 0:
            short_pnl = (pos.short_entry_price - current_price) * pos.short_amount

        pos.unrealized_pnl = long_pnl + short_pnl

        total_cost = (pos.entry_price * pos.amount) + (pos.short_entry_price * pos.short_amount)
        if total_cost > 0:
            pos.unrealized_pnl_pct = (pos.unrealized_pnl / total_cost) * 100
        else:
            pos.unrealized_pnl_pct = 0.0
        
        return pos.unrealized_pnl
    
    def get_position(self, symbol: str) -> Optional[PositionInfo]:
        """Get position for a symbol.
        
        Args:
            symbol: Trading pair
            
        Returns:
            Position info or None
        """
        return self.positions.get(symbol)
    
    def get_all_positions(self) -> list[PositionInfo]:
        """Get all non-flat positions."""
        return [p for p in self.positions.values() if p.side != "flat"]
    
    def get_portfolio_value(self, prices: dict[str, float]) -> dict:
        """Calculate total portfolio value.
        
        Args:
            prices: Dict of symbol -> current price
            
        Returns:
            Portfolio summary dict
        """
        total_value = 0.0
        total_unrealized_pnl = 0.0
        total_cost = 0.0
        
        for symbol, pos in self.positions.items():
            if pos.amount > 0:
                current_price = prices.get(symbol, pos.entry_price)
                self.calculate_unrealized_pnl(symbol, current_price)
                
                total_value += current_price * pos.amount
                total_unrealized_pnl += pos.unrealized_pnl
                total_cost += pos.total_cost
        
        return {
            "total_value": total_value,
            "total_cost": total_cost,
            "unrealized_pnl": total_unrealized_pnl,
            "unrealized_pnl_pct": ((total_value / total_cost) - 1) * 100 if total_cost > 0 else 0,
            "realized_pnl": self.total_realized_pnl,
            "total_pnl": total_unrealized_pnl + self.total_realized_pnl,
        }
    
    def sync_with_exchange(self, symbol: str = "BTC/USDT"):
        """Sync position with exchange balance.
        
        Args:
            symbol: Trading pair
        """
        try:
            base_currency = symbol.split("/")[0]  # e.g., BTC
            balance = exchange_client.get_balance(base_currency)
            
            if balance["total"] > 0:
                if symbol not in self.positions:
                    # Create position from balance (entry price unknown)
                    ticker = exchange_client.get_ticker(symbol)
                    self.positions[symbol] = PositionInfo(
                        symbol=symbol,
                        side="long",
                        amount=balance["total"],
                        entry_price=ticker["last"],  # Use current price as estimate
                        current_price=ticker["last"],
                    )
                else:
                    self.positions[symbol].amount = balance["total"]
                
                logger.info(f"Synced position: {balance['total']:.6f} {base_currency}")
            
        except Exception as e:
            logger.error(f"Failed to sync position: {e}")
    
    def _save_position(self, pos: PositionInfo):
        """Save position to database."""
        session = get_session()
        try:
            # Check if exists
            db_pos = session.query(Position).filter_by(symbol=pos.symbol).first()
            
            if db_pos:
                db_pos.side = pos.side
                db_pos.entry_price = pos.entry_price
                db_pos.amount = pos.amount
                db_pos.unrealized_pnl = pos.unrealized_pnl
                db_pos.realized_pnl = pos.realized_pnl
            else:
                db_pos = Position(
                    symbol=pos.symbol,
                    side=pos.side,
                    entry_price=pos.entry_price,
                    amount=pos.amount,
                    unrealized_pnl=pos.unrealized_pnl,
                    realized_pnl=pos.realized_pnl,
                )
                session.add(db_pos)
            
            session.commit()
        finally:
            session.close()
    
    def print_summary(self):
        """Print position summary."""
        logger.info("\n" + "=" * 50)
        logger.info("📊 POSITION SUMMARY")
        logger.info("=" * 50)
        
        positions = self.get_all_positions()
        
        if not positions:
            logger.info("No open positions")
        else:
            for pos in positions:
                pnl_color = "green" if pos.unrealized_pnl >= 0 else "red"
                logger.info(f"  {pos.symbol}:")
                logger.info(f"    Side: {pos.side.upper()}")
                logger.info(f"    Amount: {pos.amount:.6f}")
                logger.info(f"    Entry: ${pos.entry_price:,.2f}")
                logger.info(f"    Current: ${pos.current_price:,.2f}")
                logger.info(f"    Unrealized PnL: ${pos.unrealized_pnl:+,.2f} ({pos.unrealized_pnl_pct:+.2f}%)")
        
        logger.info(f"\n  Total Realized PnL: ${self.total_realized_pnl:+,.2f}")
        logger.info("=" * 50)


# Global instance
position_manager = PositionManager()
