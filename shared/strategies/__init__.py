"""Multi-strategy engine with regime-based strategy selection (Sprint 22)."""

from shared.strategies.base import StrategyInterface
from shared.strategies.regime import MarketRegime, MarketRegimeDetector
from shared.strategies.engine import StrategyEngine
from shared.strategies.registry import StrategyRegistry
from shared.strategies.momentum_strategy import MomentumStrategy
from shared.strategies.mean_reversion_strategy import MeanReversionStrategy
from shared.strategies.breakout_strategy import BreakoutStrategy
from shared.strategies.grid_strategy import GridStrategyAdapter

__all__ = [
    "StrategyInterface",
    "MarketRegime",
    "MarketRegimeDetector",
    "StrategyEngine",
    "StrategyRegistry",
    "MomentumStrategy",
    "MeanReversionStrategy",
    "BreakoutStrategy",
    "GridStrategyAdapter",
]
