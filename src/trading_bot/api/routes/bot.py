"""Bot control API endpoints."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class BotControlResponse(BaseModel):
    """Bot control action response."""
    success: bool
    message: str
    state: str
    timestamp: datetime


class BotConfigResponse(BaseModel):
    """Bot configuration."""
    symbol: str
    grid_levels: int
    grid_spacing_pct: float
    amount_per_level: float
    ai_enabled: bool
    risk_tolerance: str


# Bot instance reference (imported from main)
def _get_bot():
    from trading_bot.api.main import get_bot_instance
    return get_bot_instance()


@router.post("/pause", response_model=BotControlResponse)
async def pause_bot():
    """Pause the trading bot."""
    bot = _get_bot()
    
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not connected")
    
    from trading_bot.bot import BotState
    
    if bot.state == BotState.PAUSED:
        return BotControlResponse(
            success=False,
            message="Bot is already paused",
            state=bot.state.value,
            timestamp=datetime.now(),
        )
    
    # Set state to paused
    previous_state = bot.state.value
    bot.state = BotState.PAUSED
    
    return BotControlResponse(
        success=True,
        message=f"Bot paused (was: {previous_state})",
        state=bot.state.value,
        timestamp=datetime.now(),
    )


@router.post("/resume", response_model=BotControlResponse)
async def resume_bot():
    """Resume the trading bot."""
    bot = _get_bot()
    
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not connected")
    
    from trading_bot.bot import BotState
    
    if bot.state == BotState.TRADING:
        return BotControlResponse(
            success=False,
            message="Bot is already running",
            state=bot.state.value,
            timestamp=datetime.now(),
        )
    
    # Resume to trading or waiting
    bot.state = BotState.TRADING
    
    return BotControlResponse(
        success=True,
        message="Bot resumed",
        state=bot.state.value,
        timestamp=datetime.now(),
    )


@router.post("/stop", response_model=BotControlResponse)
async def stop_bot():
    """Stop the trading bot."""
    bot = _get_bot()
    
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not connected")
    
    if not bot.running:
        return BotControlResponse(
            success=False,
            message="Bot is already stopped",
            state="stopped",
            timestamp=datetime.now(),
        )
    
    bot.running = False
    
    return BotControlResponse(
        success=True,
        message="Bot stop requested",
        state="stopping",
        timestamp=datetime.now(),
    )


@router.get("/config", response_model=BotConfigResponse)
async def get_config():
    """Get bot configuration."""
    bot = _get_bot()
    
    if bot is None:
        return BotConfigResponse(
            symbol="BTC/USDT",
            grid_levels=5,
            grid_spacing_pct=1.0,
            amount_per_level=0.0001,
            ai_enabled=True,
            risk_tolerance="medium",
        )
    
    config = bot.config
    
    return BotConfigResponse(
        symbol=bot.symbol,
        grid_levels=config.grid_levels,
        grid_spacing_pct=config.grid_spacing_pct,
        amount_per_level=config.amount_per_level,
        ai_enabled=config.ai_enabled,
        risk_tolerance=config.risk_tolerance,
    )
