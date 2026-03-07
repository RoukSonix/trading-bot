"""Strategy registry — catalog of available strategies (Sprint 22)."""

from shared.strategies.base import StrategyInterface
from shared.strategies.momentum_strategy import MomentumStrategy
from shared.strategies.mean_reversion_strategy import MeanReversionStrategy
from shared.strategies.breakout_strategy import BreakoutStrategy
from shared.strategies.grid_strategy import GridStrategyAdapter


class StrategyRegistry:
    """Registry of available strategies with configs."""

    STRATEGIES: dict[str, type[StrategyInterface]] = {
        "grid": GridStrategyAdapter,
        "momentum": MomentumStrategy,
        "mean_reversion": MeanReversionStrategy,
        "breakout": BreakoutStrategy,
    }

    @classmethod
    def get(cls, name: str) -> StrategyInterface:
        """Instantiate a strategy by short name.

        Args:
            name: One of 'grid', 'momentum', 'mean_reversion', 'breakout'.

        Returns:
            Strategy instance.

        Raises:
            KeyError: If name is not registered.
        """
        if name not in cls.STRATEGIES:
            raise KeyError(
                f"Unknown strategy '{name}'. Available: {cls.list_all()}"
            )
        return cls.STRATEGIES[name]()

    @classmethod
    def list_all(cls) -> list[str]:
        """List all registered strategy short names."""
        return list(cls.STRATEGIES.keys())

    @classmethod
    def register(cls, name: str, strategy_cls: type[StrategyInterface]):
        """Register a custom strategy class.

        Args:
            name: Short name for the strategy.
            strategy_cls: Strategy class (must implement StrategyInterface).
        """
        cls.STRATEGIES[name] = strategy_cls
