"""API routes."""

from shared.api.routes.trades import router as trades_router
from shared.api.routes.positions import router as positions_router
from shared.api.routes.bot import router as bot_router
from shared.api.routes.orders import router as orders_router
from shared.api.routes.candles import router as candles_router

__all__ = [
    "trades_router",
    "positions_router",
    "bot_router",
    "orders_router",
    "candles_router",
]
