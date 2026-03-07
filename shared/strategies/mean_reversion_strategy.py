"""Mean reversion strategy using Bollinger Bands + RSI (Sprint 22)."""

from shared.strategies.base import StrategyInterface


class MeanReversionStrategy(StrategyInterface):
    """Mean reversion using Bollinger Bands + RSI.

    Goes long when price drops below lower BB and RSI is oversold.
    Goes short when price rises above upper BB and RSI is overbought.
    """

    def __init__(self, qty_pct: float = 0.05, tp_pct: float = 2.0, sl_pct: float = 1.0):
        self.price: float = 0.0
        self.qty_pct = qty_pct
        self.tp_pct = tp_pct
        self.sl_pct = sl_pct

    def should_long(self, candles, indicators) -> bool:
        price = candles[-1]["close"] if candles else self.price
        bb_lower = indicators.get("bb_lower", 0)
        rsi = indicators.get("rsi_14", 50)
        return price < bb_lower and rsi < 30

    def should_short(self, candles, indicators) -> bool:
        price = candles[-1]["close"] if candles else self.price
        bb_upper = indicators.get("bb_upper", float("inf"))
        rsi = indicators.get("rsi_14", 50)
        return price > bb_upper and rsi > 70

    def go_long(self) -> dict:
        return {
            "entry": self.price,
            "qty_pct": self.qty_pct,
            "tp_pct": self.tp_pct,
            "sl_pct": self.sl_pct,
            "side": "long",
        }

    def go_short(self) -> dict:
        return {
            "entry": self.price,
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
            {"name": "tp_pct", "type": "float", "min": 0.5, "max": 5.0, "default": 2.0},
            {"name": "sl_pct", "type": "float", "min": 0.5, "max": 3.0, "default": 1.0},
        ]
