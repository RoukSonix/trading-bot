"""Order management for executing trades on exchange."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from loguru import logger

from binance_bot.core.exchange import exchange_client
from shared.core.database import get_session, Trade, Position
from binance_bot.strategies.base import Signal, SignalType


class OrderStatus(Enum):
    """Order status."""
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELED = "canceled"
    FAILED = "failed"


class OrderType(Enum):
    """Order type."""
    MARKET = "market"
    LIMIT = "limit"


@dataclass
class Order:
    """Order representation."""
    id: Optional[str] = None
    symbol: str = "BTC/USDT"
    side: str = "buy"  # buy/sell
    type: OrderType = OrderType.LIMIT
    amount: float = 0.0
    price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    filled: float = 0.0
    cost: float = 0.0
    fee: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def __repr__(self):
        return f"<Order {self.id} {self.side} {self.amount} {self.symbol} @ {self.price} [{self.status.value}]>"


class OrderManager:
    """Manages order execution and tracking."""
    
    def __init__(self):
        """Initialize order manager."""
        self.open_orders: dict[str, Order] = {}
        self.filled_orders: list[Order] = []
    
    def create_limit_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
    ) -> Order:
        """Create and submit a limit order.
        
        Args:
            symbol: Trading pair (e.g., BTC/USDT)
            side: buy or sell
            amount: Amount in base currency
            price: Limit price
            
        Returns:
            Order object with exchange response
        """
        order = Order(
            symbol=symbol,
            side=side,
            type=OrderType.LIMIT,
            amount=amount,
            price=price,
        )
        
        try:
            logger.info(f"Placing {side.upper()} limit order: {amount} {symbol} @ ${price:,.2f}")
            
            # Submit to exchange
            response = exchange_client.exchange.create_limit_order(
                symbol=symbol,
                side=side,
                amount=amount,
                price=price,
            )
            
            # Update order with response
            order.id = response["id"]
            order.status = self._parse_status(response["status"])
            order.filled = response.get("filled", 0)
            order.cost = response.get("cost", 0)
            
            if response.get("fee"):
                order.fee = response["fee"].get("cost", 0)
            
            # Track order
            if order.status in [OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]:
                self.open_orders[order.id] = order
            elif order.status == OrderStatus.FILLED:
                self.filled_orders.append(order)
                self._save_trade(order)
            
            logger.info(f"Order placed: {order}")
            return order
            
        except Exception as e:
            order.status = OrderStatus.FAILED
            logger.error(f"Failed to place order: {e}")
            return order
    
    def create_market_order(
        self,
        symbol: str,
        side: str,
        amount: float,
    ) -> Order:
        """Create and submit a market order.
        
        Args:
            symbol: Trading pair
            side: buy or sell
            amount: Amount in base currency
            
        Returns:
            Order object with exchange response
        """
        order = Order(
            symbol=symbol,
            side=side,
            type=OrderType.MARKET,
            amount=amount,
        )
        
        try:
            logger.info(f"Placing {side.upper()} market order: {amount} {symbol}")
            
            response = exchange_client.exchange.create_market_order(
                symbol=symbol,
                side=side,
                amount=amount,
            )
            
            order.id = response["id"]
            order.status = self._parse_status(response["status"])
            order.filled = response.get("filled", 0)
            order.cost = response.get("cost", 0)
            order.price = response.get("average") or response.get("price")
            
            if response.get("fee"):
                order.fee = response["fee"].get("cost", 0)
            
            if order.status == OrderStatus.FILLED:
                self.filled_orders.append(order)
                self._save_trade(order)
            
            logger.info(f"Order executed: {order}")
            return order
            
        except Exception as e:
            order.status = OrderStatus.FAILED
            logger.error(f"Failed to place order: {e}")
            return order
    
    def execute_signal(self, signal: Signal, order_type: OrderType = OrderType.LIMIT) -> Order:
        """Execute a trading signal.
        
        Args:
            signal: Trading signal to execute
            order_type: Type of order to place
            
        Returns:
            Executed order
        """
        side = "buy" if signal.type == SignalType.BUY else "sell"
        abs_amount = abs(signal.amount)

        if order_type == OrderType.MARKET:
            return self.create_market_order(
                symbol="BTC/USDT",  # TODO: get from signal
                side=side,
                amount=abs_amount,
            )
        else:
            return self.create_limit_order(
                symbol="BTC/USDT",
                side=side,
                amount=abs_amount,
                price=signal.price,
            )
    
    def cancel_order(self, order_id: str, symbol: str = "BTC/USDT") -> bool:
        """Cancel an open order.
        
        Args:
            order_id: Order ID to cancel
            symbol: Trading pair
            
        Returns:
            True if canceled successfully
        """
        try:
            exchange_client.exchange.cancel_order(order_id, symbol)
            
            if order_id in self.open_orders:
                self.open_orders[order_id].status = OrderStatus.CANCELED
                del self.open_orders[order_id]
            
            logger.info(f"Order {order_id} canceled")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False
    
    def cancel_all_orders(self, symbol: str = "BTC/USDT") -> int:
        """Cancel all open orders for a symbol.
        
        Args:
            symbol: Trading pair
            
        Returns:
            Number of orders canceled
        """
        try:
            orders = exchange_client.exchange.fetch_open_orders(symbol)
            canceled = 0
            
            for order in orders:
                if self.cancel_order(order["id"], symbol):
                    canceled += 1
            
            logger.info(f"Canceled {canceled} orders for {symbol}")
            return canceled
            
        except Exception as e:
            logger.error(f"Failed to cancel all orders: {e}")
            return 0
    
    def sync_orders(self, symbol: str = "BTC/USDT"):
        """Sync open orders with exchange.
        
        Args:
            symbol: Trading pair
        """
        try:
            orders = exchange_client.exchange.fetch_open_orders(symbol)
            
            # Update local tracking
            exchange_ids = {o["id"] for o in orders}
            
            # Check for filled orders
            for order_id in list(self.open_orders.keys()):
                if order_id not in exchange_ids:
                    # Order no longer open - check if filled
                    order = self.open_orders[order_id]
                    try:
                        status = exchange_client.exchange.fetch_order(order_id, symbol)
                        order.status = self._parse_status(status["status"])
                        order.filled = status.get("filled", 0)
                        order.cost = status.get("cost", 0)
                        
                        if order.status == OrderStatus.FILLED:
                            self.filled_orders.append(order)
                            self._save_trade(order)
                            logger.info(f"Order filled: {order}")
                        # Only delete after successful status fetch
                        del self.open_orders[order_id]
                    except Exception as e:
                        logger.warning(f"Failed to fetch order status for {order_id}: {e}")
                        # Keep order in tracking — will retry on next sync
            
            logger.info(f"Synced orders: {len(self.open_orders)} open")
            
        except Exception as e:
            logger.error(f"Failed to sync orders: {e}")
    
    def get_open_orders(self, symbol: str = "BTC/USDT") -> list[dict]:
        """Get all open orders from exchange.
        
        Args:
            symbol: Trading pair
            
        Returns:
            List of open orders
        """
        try:
            return exchange_client.exchange.fetch_open_orders(symbol)
        except Exception as e:
            logger.error(f"Failed to fetch open orders: {e}")
            return []
    
    def _parse_status(self, status: str) -> OrderStatus:
        """Parse exchange status to OrderStatus."""
        status_map = {
            "open": OrderStatus.OPEN,
            "closed": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELED,
            "expired": OrderStatus.CANCELED,
            "rejected": OrderStatus.FAILED,
        }
        return status_map.get(status, OrderStatus.PENDING)
    
    def _save_trade(self, order: Order):
        """Save filled order to database."""
        session = get_session()
        try:
            trade = Trade(
                symbol=order.symbol,
                side=order.side,
                price=order.price or 0,
                amount=order.filled,
                cost=order.cost,
                fee=order.fee,
                order_id=order.id,
                timestamp=int(order.created_at.timestamp() * 1000),
            )
            session.add(trade)
            session.commit()
            logger.debug(f"Trade saved: {trade}")
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


# Global instance
order_manager = OrderManager()
