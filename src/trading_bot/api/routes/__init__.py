"""API route modules."""

from trading_bot.api.routes.trades import router as trades_router
from trading_bot.api.routes.positions import router as positions_router
from trading_bot.api.routes.bot import router as bot_router

__all__ = ["trades_router", "positions_router", "bot_router"]
