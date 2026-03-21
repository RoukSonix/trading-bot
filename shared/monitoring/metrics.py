"""Prometheus metrics for trading bot.

This module provides comprehensive metrics for monitoring the trading bot
including trade counts, PnL, position sizes, errors, API latency, and uptime.
"""

import time
from typing import Optional

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    CollectorRegistry,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from fastapi import FastAPI, Response


# Create a custom registry to avoid conflicts
REGISTRY = CollectorRegistry()

# =============================================================================
# Trading Metrics
# =============================================================================

# Trade counter with labels for side (buy/sell) and symbol
trades_total = Counter(
    "trading_bot_trades_total",
    "Total number of trades executed",
    ["side", "symbol"],
    registry=REGISTRY,
)

# Total PnL gauge (can go up or down)
pnl_total = Gauge(
    "trading_bot_pnl_total",
    "Total profit and loss in quote currency",
    registry=REGISTRY,
)

# Current position size gauge
position_size = Gauge(
    "trading_bot_position_size",
    "Current position size in base currency",
    ["symbol", "side"],
    registry=REGISTRY,
)

# =============================================================================
# Error Metrics
# =============================================================================

errors_total = Counter(
    "trading_bot_errors_total",
    "Total number of errors",
    ["type"],  # types: exchange, database, network, strategy, unknown
    registry=REGISTRY,
)

# =============================================================================
# API Metrics
# =============================================================================

api_requests_total = Counter(
    "trading_bot_api_requests_total",
    "Total API requests to the trading bot",
    ["endpoint", "method", "status"],
    registry=REGISTRY,
)

# =============================================================================
# Exchange Metrics
# =============================================================================

exchange_latency_seconds = Histogram(
    "trading_bot_exchange_latency_seconds",
    "Latency of exchange API calls in seconds",
    ["operation"],  # operations: fetch_ticker, create_order, cancel_order, etc.
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)

# =============================================================================
# System Metrics
# =============================================================================

uptime_seconds = Gauge(
    "trading_bot_uptime_seconds",
    "Time since the bot started in seconds",
    registry=REGISTRY,
)

bot_status = Gauge(
    "trading_bot_status",
    "Current bot status (1=running, 0=stopped)",
    registry=REGISTRY,
)

grid_levels_active = Gauge(
    "trading_bot_grid_levels_active",
    "Number of active grid levels",
    registry=REGISTRY,
)

grid_levels_filled = Gauge(
    "trading_bot_grid_levels_filled",
    "Number of filled grid levels",
    registry=REGISTRY,
)


class TradingMetrics:
    """Wrapper class for managing trading metrics."""
    
    _start_time: float = 0

    def __init__(self):
        """Initialize metrics with start time."""
        self._start_time = time.time()

    # -------------------------------------------------------------------------
    # Trade Metrics
    # -------------------------------------------------------------------------
    
    def record_trade(self, side: str, symbol: str, amount: float = 1) -> None:
        """Record a trade execution.
        
        Args:
            side: Trade side ("buy" or "sell")
            symbol: Trading pair symbol (e.g., "BTC/USDT")
            amount: Number of trades to record (default 1)
        """
        trades_total.labels(side=side.lower(), symbol=symbol).inc(amount)
    
    def set_pnl(self, value: float) -> None:
        """Update the total PnL gauge.
        
        Args:
            value: Current total PnL value
        """
        pnl_total.set(value)
    
    def set_position_size(self, symbol: str, side: str, size: float) -> None:
        """Update the current position size.
        
        Args:
            symbol: Trading pair symbol
            side: Position side ("long" or "short")
            size: Position size in base currency
        """
        position_size.labels(symbol=symbol, side=side).set(size)
    
    # -------------------------------------------------------------------------
    # Error Metrics
    # -------------------------------------------------------------------------
    
    def record_error(self, error_type: str) -> None:
        """Record an error occurrence.
        
        Args:
            error_type: Type of error (exchange, database, network, strategy, unknown)
        """
        errors_total.labels(type=error_type).inc()
    
    # -------------------------------------------------------------------------
    # API Metrics
    # -------------------------------------------------------------------------
    
    def record_api_request(
        self, endpoint: str, method: str, status_code: int
    ) -> None:
        """Record an API request.
        
        Args:
            endpoint: API endpoint path
            method: HTTP method (GET, POST, etc.)
            status_code: HTTP response status code
        """
        api_requests_total.labels(
            endpoint=endpoint,
            method=method.upper(),
            status=str(status_code),
        ).inc()
    
    # -------------------------------------------------------------------------
    # Exchange Metrics
    # -------------------------------------------------------------------------
    
    def observe_exchange_latency(self, operation: str, duration: float) -> None:
        """Record exchange API latency.
        
        Args:
            operation: Operation type (fetch_ticker, create_order, etc.)
            duration: Duration in seconds
        """
        exchange_latency_seconds.labels(operation=operation).observe(duration)
    
    def time_exchange_operation(self, operation: str):
        """Context manager for timing exchange operations.
        
        Usage:
            with metrics.time_exchange_operation("fetch_ticker"):
                ticker = await exchange.fetch_ticker("BTC/USDT")
        """
        return exchange_latency_seconds.labels(operation=operation).time()
    
    # -------------------------------------------------------------------------
    # System Metrics
    # -------------------------------------------------------------------------
    
    def update_uptime(self) -> None:
        """Update the uptime gauge with current uptime."""
        uptime_seconds.set(time.time() - self._start_time)
    
    def set_bot_status(self, running: bool) -> None:
        """Update the bot status gauge.
        
        Args:
            running: True if bot is running, False otherwise
        """
        bot_status.set(1 if running else 0)
    
    def set_grid_levels(self, active: int, filled: int) -> None:
        """Update grid level metrics.
        
        Args:
            active: Number of active (unfilled) grid levels
            filled: Number of filled grid levels
        """
        grid_levels_active.set(active)
        grid_levels_filled.set(filled)
    
    def reset_start_time(self) -> None:
        """Reset the start time for uptime calculation."""
        self._start_time = time.time()


# Global metrics instance
_metrics: Optional[TradingMetrics] = None


def get_metrics() -> TradingMetrics:
    """Get the global metrics instance.
    
    Returns:
        TradingMetrics: The singleton metrics instance
    """
    global _metrics
    if _metrics is None:
        _metrics = TradingMetrics()
    return _metrics


def generate_metrics() -> bytes:
    """Generate Prometheus metrics in text format.
    
    Returns:
        bytes: Prometheus metrics in exposition format
    """
    # Update uptime before generating metrics
    get_metrics().update_uptime()
    return generate_latest(REGISTRY)


def setup_metrics_endpoint(app: FastAPI) -> None:
    """Set up the /metrics endpoint for Prometheus scraping.
    
    Args:
        app: FastAPI application instance
    """
    @app.get("/metrics", tags=["Monitoring"])
    async def metrics_endpoint() -> Response:
        """Prometheus metrics endpoint."""
        return Response(
            content=generate_metrics(),
            media_type=CONTENT_TYPE_LATEST,
        )
