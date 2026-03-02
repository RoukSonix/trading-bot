"""FastAPI application for trading bot dashboard."""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from trading_bot.api.routes import trades_router, positions_router, bot_router
from trading_bot.core.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    init_db()
    yield
    # Shutdown
    pass


app = FastAPI(
    title="Trading Bot API",
    description="REST API for trading bot monitoring and control",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for Streamlit frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(trades_router, prefix="/api/trades", tags=["Trades"])
app.include_router(positions_router, prefix="/api/positions", tags=["Positions"])
app.include_router(bot_router, prefix="/api/bot", tags=["Bot Control"])


class StatusResponse(BaseModel):
    """Bot status response."""
    status: str
    state: str
    symbol: str
    uptime_seconds: Optional[float] = None
    ticks: int = 0
    errors: int = 0
    current_price: Optional[float] = None
    timestamp: datetime


class GridLevelResponse(BaseModel):
    """Grid level info."""
    price: float
    side: str
    amount: float
    filled: bool
    order_id: Optional[str] = None


class GridResponse(BaseModel):
    """Grid levels response."""
    center_price: Optional[float]
    current_price: Optional[float]
    levels: list[GridLevelResponse]
    total_levels: int


# Bot instance reference (set by run_dashboard.py)
_bot_instance = None


def set_bot_instance(bot):
    """Set the bot instance for API access."""
    global _bot_instance
    _bot_instance = bot


def get_bot_instance():
    """Get the current bot instance."""
    return _bot_instance


@app.get("/api/status", response_model=StatusResponse)
async def get_status():
    """Get current bot status."""
    bot = get_bot_instance()
    
    if bot is None:
        return StatusResponse(
            status="disconnected",
            state="unknown",
            symbol="BTC/USDT",
            ticks=0,
            errors=0,
            timestamp=datetime.now(),
        )
    
    uptime = None
    if bot.start_time:
        uptime = (datetime.now() - bot.start_time).total_seconds()
    
    current_price = None
    if bot.strategy and bot.strategy.center_price:
        current_price = bot.strategy.center_price
    
    return StatusResponse(
        status="running" if bot.running else "stopped",
        state=bot.state.value,
        symbol=bot.symbol,
        uptime_seconds=uptime,
        ticks=bot.ticks,
        errors=bot.errors,
        current_price=current_price,
        timestamp=datetime.now(),
    )


@app.get("/api/grid", response_model=GridResponse)
async def get_grid():
    """Get current grid levels."""
    bot = get_bot_instance()
    
    if bot is None or bot.strategy is None:
        return GridResponse(
            center_price=None,
            current_price=None,
            levels=[],
            total_levels=0,
        )
    
    strategy = bot.strategy
    levels = []
    
    for level in strategy.levels:
        levels.append(GridLevelResponse(
            price=level.price,
            side=level.side.value,
            amount=level.amount,
            filled=level.filled,
            order_id=level.order_id,
        ))
    
    return GridResponse(
        center_price=strategy.center_price,
        current_price=strategy.center_price,  # Updated by tick
        levels=levels,
        total_levels=len(levels),
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
