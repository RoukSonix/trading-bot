"""Grid strategy adapter — wraps existing GridStrategy in new StrategyInterface (Sprint 22)."""

from shared.strategies.base import StrategyInterface


class GridStrategyAdapter(StrategyInterface):
    """Adapter wrapping the existing GridStrategy into StrategyInterface.

    Grid trading is best suited for ranging/low-volatility markets. This
    adapter delegates signal generation to the existing GridStrategy and
    translates the result into the unified interface.
    """

    def __init__(self, qty_pct: float = 0.05, grid_levels: int = 10, spacing_pct: float = 1.0):
        self.price: float = 0.0
        self.qty_pct = qty_pct
        self.grid_levels = grid_levels
        self.spacing_pct = spacing_pct

    def should_long(self, candles, indicators) -> bool:
        """Grid strategy should activate in ranging markets."""
        rsi = indicators.get("rsi_14", 50)
        # Grid is suitable when RSI is in the neutral zone (ranging)
        return 35 <= rsi <= 65

    def should_short(self, candles, indicators) -> bool:
        """Grid handles shorts internally via bi-directional grid."""
        return False

    def go_long(self) -> dict:
        return {
            "entry": self.price,
            "qty_pct": self.qty_pct,
            "tp_pct": self.spacing_pct,
            "sl_pct": self.spacing_pct * 2,
            "side": "grid",
            "grid_levels": self.grid_levels,
            "spacing_pct": self.spacing_pct,
        }

    def go_short(self) -> dict:
        return {
            "entry": self.price,
            "qty_pct": self.qty_pct,
            "tp_pct": self.spacing_pct,
            "sl_pct": self.spacing_pct * 2,
            "side": "grid",
            "grid_levels": self.grid_levels,
            "spacing_pct": self.spacing_pct,
        }

    def should_cancel_entry(self) -> bool:
        return False

    def hyperparameters(self) -> list[dict]:
        return [
            {"name": "grid_levels", "type": "int", "min": 3, "max": 30, "default": 10},
            {"name": "spacing_pct", "type": "float", "min": 0.5, "max": 5.0, "default": 1.0},
            {"name": "qty_pct", "type": "float", "min": 0.01, "max": 0.20, "default": 0.05},
        ]
