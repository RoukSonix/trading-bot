"""Breakout strategy — enter on range break (Sprint 22)."""

from shared.strategies.base import StrategyInterface


class BreakoutStrategy(StrategyInterface):
    """Breakout strategy — enter when price breaks recent range.

    Goes long when price exceeds the 20-period high.
    Goes short when price drops below the 20-period low.
    """

    def __init__(self, qty_pct: float = 0.05, tp_pct: float = 4.0, sl_pct: float = 2.0):
        self.price: float = 0.0
        self.qty_pct = qty_pct
        self.tp_pct = tp_pct
        self.sl_pct = sl_pct

    def should_long(self, candles, indicators) -> bool:
        price = candles[-1]["close"] if candles else self.price
        high_20 = indicators.get("highest_20", float("inf"))
        return price > high_20

    def should_short(self, candles, indicators) -> bool:
        price = candles[-1]["close"] if candles else self.price
        low_20 = indicators.get("lowest_20", 0)
        return price < low_20

    def go_long(self) -> dict:
        return {
            "entry": self.price * 1.001,
            "qty_pct": self.qty_pct,
            "tp_pct": self.tp_pct,
            "sl_pct": self.sl_pct,
            "side": "long",
        }

    def go_short(self) -> dict:
        return {
            "entry": self.price * 0.999,
            "qty_pct": self.qty_pct,
            "tp_pct": self.tp_pct,
            "sl_pct": self.sl_pct,
            "side": "short",
        }

    def should_cancel_entry(self) -> bool:
        return False

    def hyperparameters(self) -> list[dict]:
        return [
            {"name": "qty_pct", "type": "float", "min": 0.01, "max": 0.20, "default": 0.05},
            {"name": "tp_pct", "type": "float", "min": 2.0, "max": 10.0, "default": 4.0},
            {"name": "sl_pct", "type": "float", "min": 1.0, "max": 5.0, "default": 2.0},
        ]
