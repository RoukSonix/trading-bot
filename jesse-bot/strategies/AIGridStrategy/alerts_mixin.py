"""
AlertsMixin - Wrapper around shared/alerts/AlertManager for Jesse strategy.

Provides trade, status, error, and AI decision alerts.
Handles missing AlertManager gracefully (log warning, continue).
Suppresses alerts during backtesting.
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import AlertManager from shared/
_HAS_ALERTS = False
try:
    from shared.alerts.manager import AlertManager, AlertConfig, AlertLevel
    _HAS_ALERTS = True
except ImportError:
    AlertManager = None
    AlertConfig = None
    AlertLevel = None


class AlertsMixin:
    """Mixin that wraps shared AlertManager for Jesse strategies.

    Usage:
        Call methods from strategy lifecycle hooks.
        All methods are no-ops during backtesting or if AlertManager is unavailable.
    """

    def __init__(self, is_live: bool = False):
        self._is_live = is_live
        self._alert_manager: Optional[object] = None
        self._initialized = False

    def _ensure_init(self) -> bool:
        """Lazy-initialize AlertManager. Returns True if ready."""
        if self._initialized:
            return self._alert_manager is not None

        self._initialized = True

        if not _HAS_ALERTS:
            logger.warning("AlertsMixin: shared.alerts not available, alerts disabled")
            return False

        try:
            self._alert_manager = AlertManager(AlertConfig())
            logger.info("AlertsMixin: AlertManager initialized")
            return True
        except Exception as e:
            logger.warning(f"AlertsMixin: Failed to initialize AlertManager: {e}")
            return False

    def _should_send(self) -> bool:
        """Check if alerts should be sent (live mode + manager available)."""
        if not self._is_live:
            return False
        return self._ensure_init()

    def _run_async(self, coro):
        """Run an async coroutine from sync context."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(coro)
            else:
                loop.run_until_complete(coro)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(coro)
            finally:
                loop.close()

    def send_trade_alert(self, trade_info: dict) -> None:
        """Send alert on position open/close.

        Args:
            trade_info: dict with keys: symbol, side, price, amount,
                        pnl (optional), pnl_pct (optional), action (open/close)
        """
        if not self._should_send():
            return

        try:
            self._run_async(
                self._alert_manager.send_trade_alert(
                    symbol=trade_info.get('symbol', 'BTC-USDT'),
                    side=trade_info.get('side', 'unknown'),
                    price=trade_info.get('price', 0.0),
                    amount=trade_info.get('amount', 0.0),
                    pnl=trade_info.get('pnl'),
                    pnl_pct=trade_info.get('pnl_pct'),
                )
            )
            logger.debug(f"Trade alert sent: {trade_info.get('action', 'trade')}")
        except Exception as e:
            logger.warning(f"AlertsMixin: Failed to send trade alert: {e}")

    def send_status_alert(self, status: dict) -> None:
        """Send periodic status alert.

        Args:
            status: dict with keys: status, symbol, current_price,
                    total_value, trades_count, reason (optional)
        """
        if not self._should_send():
            return

        try:
            self._run_async(
                self._alert_manager.send_status_alert(
                    status=status.get('status', 'running'),
                    symbol=status.get('symbol', 'BTC-USDT'),
                    current_price=status.get('current_price'),
                    total_value=status.get('total_value'),
                    trades_count=status.get('trades_count'),
                    reason=status.get('reason'),
                )
            )
            logger.debug(f"Status alert sent: {status.get('status')}")
        except Exception as e:
            logger.warning(f"AlertsMixin: Failed to send status alert: {e}")

    def send_error_alert(self, error: str, context: Optional[str] = None,
                         exc: Optional[Exception] = None) -> None:
        """Send error alert.

        Args:
            error: Error message
            context: Where the error occurred
            exc: Exception object (optional)
        """
        if not self._should_send():
            return

        try:
            self._run_async(
                self._alert_manager.send_error_alert(
                    error=error,
                    context=context,
                    exc=exc,
                )
            )
            logger.debug(f"Error alert sent: {error[:50]}")
        except Exception as e:
            logger.warning(f"AlertsMixin: Failed to send error alert: {e}")

    def send_ai_decision_alert(self, analysis: dict) -> None:
        """Send alert when AI makes a trading decision.

        Args:
            analysis: dict with keys: trend, confidence, recommendation,
                      reasoning, grid_params (optional)
        """
        if not self._should_send():
            return

        try:
            fields = [
                {"name": "Trend", "value": str(analysis.get('trend', 'unknown')), "inline": True},
                {"name": "Confidence", "value": f"{analysis.get('confidence', 0):.1%}", "inline": True},
                {"name": "Action", "value": str(analysis.get('recommendation', 'N/A')), "inline": True},
            ]

            reasoning = analysis.get('reasoning', '')
            if reasoning:
                fields.append({"name": "Reasoning", "value": reasoning[:200], "inline": False})

            grid_params = analysis.get('grid_params', {})
            if grid_params:
                params_str = ", ".join(f"{k}={v}" for k, v in grid_params.items())
                fields.append({"name": "Grid Params", "value": params_str[:200], "inline": False})

            self._run_async(
                self._alert_manager.send_custom_alert(
                    title="AI Trading Decision",
                    message=f"AI recommends: {analysis.get('recommendation', 'N/A')}",
                    level=AlertLevel.INFO,
                    fields=fields,
                )
            )
            logger.debug(f"AI decision alert sent: {analysis.get('recommendation')}")
        except Exception as e:
            logger.warning(f"AlertsMixin: Failed to send AI decision alert: {e}")
