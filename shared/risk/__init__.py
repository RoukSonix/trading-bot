# Risk Management Module
"""
Risk management components for capital protection:
- Position sizing (Kelly criterion, fixed %)
- Stop-loss / take-profit
- TP/SL calculator (fixed %, ATR-based, risk-reward)
- Trailing stop manager
- Break-even stop manager
- Daily loss limits
- Max drawdown protection
- Risk metrics
"""

from .position_sizer import PositionSizer, SizingMethod
from .stop_loss import StopLossManager, StopLossType
from .tp_sl import TPSLCalculator
from .trailing_stop import TrailingStopManager
from .break_even import BreakEvenManager
from .limits import RiskLimits, LimitStatus
from .metrics import RiskMetrics

__all__ = [
    "PositionSizer",
    "SizingMethod",
    "StopLossManager",
    "StopLossType",
    "TPSLCalculator",
    "TrailingStopManager",
    "BreakEvenManager",
    "RiskLimits",
    "LimitStatus",
    "RiskMetrics",
]
