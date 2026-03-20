"""Order management API endpoints."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel

from shared.api.auth import require_api_key

router = APIRouter()


class OrderResponse(BaseModel):
    """Order record response."""
    id: str
    symbol: str
    side: str
    price: float
    amount: float
    filled: float
    status: str
    timestamp: datetime
    order_type: str = "limit"


class OrderListResponse(BaseModel):
    """Order list response."""
    orders: list[OrderResponse]
    total: int


class ForceTradeRequest(BaseModel):
    """Force trade request."""
    amount: Optional[float] = None
    price: Optional[float] = None


class ForceTradeResponse(BaseModel):
    """Force trade response."""
    success: bool
    message: str
    order_id: Optional[str] = None
    price: Optional[float] = None
    amount: Optional[float] = None


class CancelOrderResponse(BaseModel):
    """Cancel order response."""
    success: bool
    message: str
    order_id: str


def _get_bot():
    """Get bot instance."""
    from shared.api.main import get_bot_instance
    return get_bot_instance()


@router.get("", response_model=OrderListResponse)
async def get_orders(
    symbol: Optional[str] = None,
    side: Optional[str] = None,
):
    """Get open orders."""
    from shared.core.state import read_state
    
    # Try reading from shared state file first (Docker)
    state = read_state()
    
    orders = []
    
    if state and state.grid_levels:
        for i, level in enumerate(state.grid_levels):
            if level.get("order_id") and not level.get("filled"):
                if side and level.get("side") != side:
                    continue
                orders.append(OrderResponse(
                    id=level.get("order_id", f"grid_{i}"),
                    symbol=state.symbol,
                    side=level.get("side", "buy"),
                    price=level.get("price", 0),
                    amount=level.get("amount", 0),
                    filled=0.0,
                    status="open",
                    timestamp=datetime.fromisoformat(state.timestamp) if state.timestamp else datetime.now(timezone.utc),
                    order_type="limit",
                ))

    if orders:
        return OrderListResponse(orders=orders, total=len(orders))

    # Fallback to in-process bot instance (local dev)
    bot = _get_bot()
    if bot and bot.strategy and hasattr(bot.strategy, "levels"):
        for i, level in enumerate(bot.strategy.levels):
            if level.order_id and not level.filled:
                if side and level.side.value != side:
                    continue
                orders.append(OrderResponse(
                    id=level.order_id,
                    symbol=bot.symbol,
                    side=level.side.value,
                    price=level.price,
                    amount=level.amount,
                    filled=0.0,
                    status="open",
                    timestamp=datetime.now(timezone.utc),
                    order_type="limit",
                ))
    
    return OrderListResponse(orders=orders, total=len(orders))


async def _force_trade(side: str, request: ForceTradeRequest) -> ForceTradeResponse:
    """Execute a forced market trade."""
    bot = _get_bot()

    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not connected")

    if not bot.running:
        raise HTTPException(status_code=400, detail="Bot is not running")

    try:
        amount = request.amount or bot.config.amount_per_level

        if hasattr(bot, "exchange") and bot.exchange:
            create_order = (
                bot.exchange.create_market_buy_order if side == "buy"
                else bot.exchange.create_market_sell_order
            )
            order = await create_order(symbol=bot.symbol, amount=amount)
            return ForceTradeResponse(
                success=True,
                message=f"Market {side} executed",
                order_id=order.get("id"),
                price=order.get("average") or order.get("price"),
                amount=amount,
            )
        else:
            current_price = bot.strategy.center_price if bot.strategy else 0
            return ForceTradeResponse(
                success=True,
                message=f"Paper {side} executed",
                order_id=f"paper_{datetime.now(timezone.utc).timestamp()}",
                price=current_price,
                amount=amount,
            )
    except Exception as e:
        return ForceTradeResponse(
            success=False,
            message=f"{side.capitalize()} failed: {str(e)}",
        )


@router.post("/force-buy", response_model=ForceTradeResponse, dependencies=[Depends(require_api_key)])
async def force_buy(request: ForceTradeRequest = ForceTradeRequest()):
    """Execute a forced market buy."""
    return await _force_trade("buy", request)


@router.post("/force-sell", response_model=ForceTradeResponse, dependencies=[Depends(require_api_key)])
async def force_sell(request: ForceTradeRequest = ForceTradeRequest()):
    """Execute a forced market sell."""
    return await _force_trade("sell", request)


@router.delete("/{order_id}", response_model=CancelOrderResponse, dependencies=[Depends(require_api_key)])
async def cancel_order(order_id: str = Path(..., description="Order ID to cancel")):
    """Cancel a specific order."""
    bot = _get_bot()
    
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not connected")
    
    try:
        # Try to cancel through exchange
        if hasattr(bot, "exchange") and bot.exchange:
            await bot.exchange.cancel_order(order_id, bot.symbol)
            return CancelOrderResponse(
                success=True,
                message="Order cancelled",
                order_id=order_id,
            )
        else:
            # Paper trading - just mark as cancelled
            return CancelOrderResponse(
                success=True,
                message="Order cancelled (paper trading)",
                order_id=order_id,
            )
    except Exception as e:
        return CancelOrderResponse(
            success=False,
            message=f"Cancel failed: {str(e)}",
            order_id=order_id,
        )
