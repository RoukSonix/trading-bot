"""Binance-specific core modules."""

from binance_bot.core.exchange import exchange_client
from binance_bot.core.emergency import EmergencyStop, emergency_stop

__all__ = [
    "exchange_client",
    "EmergencyStop",
    "emergency_stop",
]
