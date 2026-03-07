"""Momentum / trend-following strategy using EMA crossover + RSI (Sprint 22)."""

from shared.strategies.base import StrategyInterface


class MomentumStrategy(StrategyInterface):
    """Trend-following strategy using EMA crossover + RSI.

    Goes long when fast EMA > slow EMA and RSI is not overbought.
    Goes short when fast EMA < slow EMA and RSI is not oversold.
    """

    def __init__(self, qty_pct: float = 0.05, tp_pct: float = 3.0, sl_pct: float = 1.5):
        self.price: float = 0.0
        self.qty_pct = qty_pct
        self.tp_pct = tp_pct
        self.sl_pct = sl_pct

    def should_long(self, candles, indicators) -> bool:
        ema_fast = indicators.get("ema_8", 0)
        ema_slow = indicators.get("ema_21", 0)
        rsi = indicators.get("rsi_14", 50)
        return ema_fast > ema_slow and rsi < 70

    def should_short(self, candles, indicators) -> bool:
        ema_fast = indicators.get("ema_8", 0)
        ema_slow = indicators.get("ema_21", 0)
        rsi = indicators.get("rsi_14", 50)
        return ema_fast < ema_slow and rsi > 30

    def go_long(self) -> dict:
        return {
            "entry": self.price * 0.999,
            "qty_pct": self.qty_pct,
            "tp_pct": self.tp_pct,
            "sl_pct": self.sl_pct,
            "side": "long",
        }

    def go_short(self) -> dict:
        return {
            "entry": self.price * 1.001,
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
            {"name": "tp_pct", "type": "float", "min": 1.0, "max": 10.0, "default": 3.0},
            {"name": "sl_pct", "type": "float", "min": 0.5, "max": 5.0, "default": 1.5},
        ]
