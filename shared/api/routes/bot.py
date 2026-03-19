"""Bot control API endpoints — file-based IPC for Docker."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from shared.api.auth import require_api_key

from shared.core.state import read_state, write_command

router = APIRouter()


class BotControlResponse(BaseModel):
    success: bool
    message: str
    state: str
    timestamp: datetime


class BotConfigResponse(BaseModel):
    symbol: str
    grid_levels: int
    grid_spacing_pct: float
    amount_per_level: float
    ai_enabled: bool
    risk_tolerance: str


@router.post("/pause", response_model=BotControlResponse, dependencies=[Depends(require_api_key)])
async def pause_bot():
    """Send pause command to bot via file IPC."""
    write_command("pause")
    state = read_state()
    return BotControlResponse(
        success=True,
        message="Pause command sent",
        state=state.state if state else "unknown",
        timestamp=datetime.now(timezone.utc),
    )


@router.post("/resume", response_model=BotControlResponse, dependencies=[Depends(require_api_key)])
async def resume_bot():
    """Send resume command to bot via file IPC."""
    write_command("resume")
    state = read_state()
    return BotControlResponse(
        success=True,
        message="Resume command sent",
        state=state.state if state else "unknown",
        timestamp=datetime.now(timezone.utc),
    )


@router.post("/stop", response_model=BotControlResponse, dependencies=[Depends(require_api_key)])
async def stop_bot():
    """Send stop command to bot via file IPC."""
    write_command("stop")
    state = read_state()
    return BotControlResponse(
        success=True,
        message="Stop command sent",
        state=state.state if state else "unknown",
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/config", response_model=BotConfigResponse)
async def get_config():
    """Get bot config from state file."""
    state = read_state()
    if state is None:
        return BotConfigResponse(
            symbol="BTC/USDT",
            grid_levels=0,
            grid_spacing_pct=0,
            amount_per_level=0,
            ai_enabled=True,
            risk_tolerance="medium",
        )
    return BotConfigResponse(
        symbol=state.symbol,
        grid_levels=len(state.grid_levels),
        grid_spacing_pct=getattr(state, "grid_spacing_pct", 0.5),
        amount_per_level=getattr(state, "amount_per_level", 0),
        ai_enabled=True,
        risk_tolerance="medium",
    )
