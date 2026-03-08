"""FastAPI application for trading bot dashboard."""

import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from shared.api.routes import (
    trades_router,
    positions_router,
    bot_router,
    orders_router,
    candles_router,
)
from sqlalchemy import text
from shared.core.database import init_db, engine as db_engine
from shared.core.state import read_state, BotState as SharedBotState
from shared.alerts import (
    AlertConfig,
    AlertLevel,
    get_alert_manager,
    get_rules_engine,
)
from shared.monitoring import get_metrics, setup_metrics_endpoint


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    init_db()
    # Initialize metrics
    metrics = get_metrics()
    metrics.reset_start_time()
    yield
    # Shutdown
    pass


app = FastAPI(
    title="Trading Bot API",
    description="REST API for trading bot monitoring and control",
    version="1.0.0",
    lifespan=lifespan,
)

# Setup Prometheus metrics endpoint
setup_metrics_endpoint(app)

# CORS for Streamlit frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Middleware to track API requests
@app.middleware("http")
async def track_requests(request: Request, call_next):
    """Track API requests for metrics."""
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    # Record metrics (skip /metrics endpoint to avoid recursion)
    if request.url.path != "/metrics":
        metrics = get_metrics()
        metrics.record_api_request(
            endpoint=request.url.path,
            method=request.method,
            status_code=response.status_code,
        )
    
    return response


# Include routers
app.include_router(trades_router, prefix="/api/trades", tags=["Trades"])
app.include_router(positions_router, prefix="/api/positions", tags=["Positions"])
app.include_router(bot_router, prefix="/api/bot", tags=["Bot Control"])
app.include_router(orders_router, prefix="/api/orders", tags=["Orders"])
app.include_router(candles_router, prefix="/api/candles", tags=["Candles"])


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


# Health Check Models
class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: datetime


class ReadinessResponse(BaseModel):
    """Readiness check response."""
    status: str
    checks: dict
    timestamp: datetime


# Alert Models
class AlertConfigRequest(BaseModel):
    """Alert configuration update request."""
    alerts_enabled: Optional[bool] = None
    discord_enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None
    alert_on_trade: Optional[bool] = None
    alert_on_error: Optional[bool] = None
    daily_summary_enabled: Optional[bool] = None
    daily_summary_time: Optional[str] = None
    rate_limit_per_minute: Optional[int] = None
    min_alert_interval_seconds: Optional[int] = None


class AlertConfigResponse(BaseModel):
    """Alert configuration response."""
    alerts_enabled: bool
    discord_enabled: bool
    email_enabled: bool
    alert_on_trade: bool
    alert_on_error: bool
    daily_summary_enabled: bool
    daily_summary_time: str
    rate_limit_per_minute: int
    min_alert_interval_seconds: int
    stats: dict


class TestAlertRequest(BaseModel):
    """Test alert request."""
    channel: str = "discord"  # discord, email, or all
    message: Optional[str] = None


class TestAlertResponse(BaseModel):
    """Test alert response."""
    success: bool
    channels_sent: list[str]
    message: str


class AlertRulesResponse(BaseModel):
    """Alert rules response."""
    rules: list[dict]


class AlertRuleUpdateRequest(BaseModel):
    """Update alert rule request."""
    name: str
    enabled: bool


# Bot instance reference (set by run_dashboard.py)
_bot_instance = None


def set_bot_instance(bot):
    """Set the bot instance for API access."""
    global _bot_instance
    _bot_instance = bot


def get_bot_instance():
    """Get the current bot instance."""
    return _bot_instance


@app.post("/api/bot/pause")
async def pause_bot():
    """Send pause command to bot via file IPC."""
    from shared.core.state import write_command
    write_command("pause")
    return {"success": True, "command": "pause"}


@app.post("/api/bot/resume")
async def resume_bot():
    """Send resume command to bot via file IPC."""
    from shared.core.state import write_command
    write_command("resume")
    return {"success": True, "command": "resume"}


@app.post("/api/bot/stop")
async def stop_bot():
    """Send stop command to bot via file IPC."""
    from shared.core.state import write_command
    write_command("stop")
    return {"success": True, "command": "stop"}


@app.get("/api/status", response_model=StatusResponse)
async def get_status():
    """Get current bot status from shared state file."""
    # Try reading from shared state file first (works in Docker)
    state = read_state()
    
    if state is not None:
        # Update metrics from state
        metrics = get_metrics()
        metrics.set_bot_status(state.status == "running")
        if state.uptime_seconds:
            pass  # Uptime is managed by metrics module
        
        return StatusResponse(
            status=state.status,
            state=state.state,
            symbol=state.symbol,
            uptime_seconds=state.uptime_seconds,
            ticks=state.ticks,
            errors=state.errors,
            current_price=state.current_price,
            timestamp=datetime.fromisoformat(state.timestamp) if isinstance(state.timestamp, str) else state.timestamp,
        )
    
    # Fallback to in-process bot instance (local dev)
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
    """Get current grid levels from shared state file."""
    # Try reading from shared state file first (works in Docker)
    state = read_state()
    
    if state is not None and state.grid_levels:
        levels = []
        for level in state.grid_levels:
            levels.append(GridLevelResponse(
                price=level.get("price", 0),
                side=level.get("side", "buy"),
                amount=level.get("amount", 0),
                filled=level.get("filled", False),
                order_id=level.get("order_id"),
            ))
        
        # Update metrics
        metrics = get_metrics()
        filled_count = sum(1 for l in state.grid_levels if l.get("filled", False))
        metrics.set_grid_levels(active=len(levels) - filled_count, filled=filled_count)
        
        return GridResponse(
            center_price=state.center_price,
            current_price=state.current_price,
            levels=levels,
            total_levels=len(levels),
        )
    
    # Fallback to in-process bot instance (local dev)
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
        current_price=strategy.center_price,
        levels=levels,
        total_levels=len(levels),
    )


# =============================================================================
# Health Check Endpoints
# =============================================================================

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Basic health check endpoint for Docker.
    
    Returns 200 if the API is responsive.
    """
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(),
    )


@app.get("/health/live", response_model=HealthResponse, tags=["Health"])
async def liveness_check():
    """Liveness probe for Kubernetes/Docker.
    
    Returns 200 if the process is alive and responding.
    Used by orchestrators to determine if the container should be restarted.
    """
    return HealthResponse(
        status="alive",
        timestamp=datetime.now(),
    )


@app.get("/health/ready", response_model=ReadinessResponse, tags=["Health"])
async def readiness_check(response: Response):
    """Readiness probe for Kubernetes/Docker.
    
    Checks if the service is ready to accept traffic:
    - Database connection is working
    - Bot state file is accessible (if bot is expected to be running)
    
    Returns 200 if ready, 503 if not ready.
    """
    checks = {}
    all_healthy = True
    
    # Check 1: Database connectivity
    try:
        # Use db_engine directly
        with db_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception as e:
        checks["database"] = {"status": "error", "message": str(e)}
        all_healthy = False
        # Record error metric
        get_metrics().record_error("database")
    
    # Check 2: State file accessible (optional check)
    state_path = Path("data/bot_state.json")
    if state_path.exists():
        try:
            state = read_state()
            if state is not None:
                checks["bot_state"] = {
                    "status": "ok",
                    "bot_status": state.status,
                }
            else:
                checks["bot_state"] = {"status": "ok", "message": "State file exists but empty"}
        except Exception as e:
            checks["bot_state"] = {"status": "warning", "message": str(e)}
    else:
        checks["bot_state"] = {"status": "ok", "message": "No state file (bot may not be running)"}
    
    # Check 3: Data directory writable
    try:
        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)
        test_file = data_dir / ".health_check"
        test_file.write_text("ok")
        test_file.unlink()
        checks["data_directory"] = {"status": "ok"}
    except Exception as e:
        checks["data_directory"] = {"status": "error", "message": str(e)}
        all_healthy = False
    
    # Set response status code
    if not all_healthy:
        response.status_code = 503
    
    return ReadinessResponse(
        status="ready" if all_healthy else "not_ready",
        checks=checks,
        timestamp=datetime.now(),
    )


# =============================================================================
# Alert Endpoints
# =============================================================================

@app.get("/api/alerts/config", response_model=AlertConfigResponse, tags=["Alerts"])
async def get_alert_config():
    """Get current alert configuration."""
    alert_manager = get_alert_manager()
    config = alert_manager.config
    stats = alert_manager.get_stats()
    
    return AlertConfigResponse(
        alerts_enabled=config.alerts_enabled,
        discord_enabled=config.discord_enabled,
        email_enabled=config.email_enabled,
        alert_on_trade=config.alert_on_trade,
        alert_on_error=config.alert_on_error,
        daily_summary_enabled=config.daily_summary_enabled,
        daily_summary_time=config.daily_summary_time,
        rate_limit_per_minute=config.rate_limit_per_minute,
        min_alert_interval_seconds=config.min_alert_interval_seconds,
        stats=stats,
    )


@app.put("/api/alerts/config", response_model=AlertConfigResponse, tags=["Alerts"])
async def update_alert_config(request: AlertConfigRequest):
    """Update alert configuration."""
    alert_manager = get_alert_manager()
    config = alert_manager.config
    
    # Update only provided fields
    if request.alerts_enabled is not None:
        config.alerts_enabled = request.alerts_enabled
    if request.discord_enabled is not None:
        config.discord_enabled = request.discord_enabled
    if request.email_enabled is not None:
        config.email_enabled = request.email_enabled
    if request.alert_on_trade is not None:
        config.alert_on_trade = request.alert_on_trade
    if request.alert_on_error is not None:
        config.alert_on_error = request.alert_on_error
    if request.daily_summary_enabled is not None:
        config.daily_summary_enabled = request.daily_summary_enabled
    if request.daily_summary_time is not None:
        config.daily_summary_time = request.daily_summary_time
    if request.rate_limit_per_minute is not None:
        config.rate_limit_per_minute = request.rate_limit_per_minute
    if request.min_alert_interval_seconds is not None:
        config.min_alert_interval_seconds = request.min_alert_interval_seconds
    
    stats = alert_manager.get_stats()
    
    return AlertConfigResponse(
        alerts_enabled=config.alerts_enabled,
        discord_enabled=config.discord_enabled,
        email_enabled=config.email_enabled,
        alert_on_trade=config.alert_on_trade,
        alert_on_error=config.alert_on_error,
        daily_summary_enabled=config.daily_summary_enabled,
        daily_summary_time=config.daily_summary_time,
        rate_limit_per_minute=config.rate_limit_per_minute,
        min_alert_interval_seconds=config.min_alert_interval_seconds,
        stats=stats,
    )


@app.post("/api/alerts/test", response_model=TestAlertResponse, tags=["Alerts"])
async def send_test_alert(request: TestAlertRequest):
    """Send a test alert to verify configuration."""
    alert_manager = get_alert_manager()
    channels_sent = []
    
    message = request.message or "This is a test alert from Trading Bot API."
    
    try:
        if request.channel in ("discord", "all"):
            if alert_manager.discord.enabled:
                success = await alert_manager.discord.send_custom(
                    title="🧪 Test Alert",
                    description=message,
                )
                if success:
                    channels_sent.append("discord")
        
        if request.channel in ("email", "all"):
            if alert_manager.email.enabled:
                success = await alert_manager.email.send_alert(
                    subject="Test Alert",
                    body=message,
                )
                if success:
                    channels_sent.append("email")
        
        if not channels_sent:
            return TestAlertResponse(
                success=False,
                channels_sent=[],
                message="No alerts sent. Check if channels are enabled and configured.",
            )
        
        return TestAlertResponse(
            success=True,
            channels_sent=channels_sent,
            message=f"Test alert sent to: {', '.join(channels_sent)}",
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send test alert: {str(e)}")


@app.get("/api/alerts/rules", response_model=AlertRulesResponse, tags=["Alerts"])
async def get_alert_rules():
    """Get all alert rules."""
    rules_engine = get_rules_engine()
    return AlertRulesResponse(rules=rules_engine.get_rules())


@app.put("/api/alerts/rules", tags=["Alerts"])
async def update_alert_rule(request: AlertRuleUpdateRequest):
    """Enable or disable an alert rule."""
    rules_engine = get_rules_engine()
    success = rules_engine.enable_rule(request.name, request.enabled)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"Rule not found: {request.name}")
    
    return {"success": True, "message": f"Rule '{request.name}' {'enabled' if request.enabled else 'disabled'}"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
