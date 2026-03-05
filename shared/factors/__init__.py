"""Factor analysis module for trading signal generation."""

from shared.factors.factor_calculator import (
    FactorCalculator,
    FactorResult,
    factor_calculator,
)
from shared.factors.factor_strategy import (
    FactorScore,
    FactorStrategy,
    GridAction,
    MarketRegime,
    factor_strategy,
)

__all__ = [
    "FactorCalculator",
    "FactorResult",
    "factor_calculator",
    "FactorScore",
    "FactorStrategy",
    "GridAction",
    "MarketRegime",
    "factor_strategy",
]
