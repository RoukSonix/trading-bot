"""Base strategy interface inspired by Jesse AI (Sprint 22)."""

from abc import ABC, abstractmethod


class StrategyInterface(ABC):
    """Base strategy interface inspired by Jesse AI.

    Every strategy must implement these methods.
    """

    @abstractmethod
    def should_long(self, candles, indicators) -> bool:
        """Should we enter a long position?"""
        pass

    @abstractmethod
    def should_short(self, candles, indicators) -> bool:
        """Should we enter a short position?"""
        pass

    @abstractmethod
    def go_long(self) -> dict:
        """Define long entry: price, qty, TP, SL."""
        pass

    @abstractmethod
    def go_short(self) -> dict:
        """Define short entry: price, qty, TP, SL."""
        pass

    @abstractmethod
    def should_cancel_entry(self) -> bool:
        """Should pending entry be cancelled?"""
        pass

    def update_position(self, candles, indicators) -> dict | None:
        """Optional: update TP/SL while in position."""
        return None

    def hyperparameters(self) -> list[dict]:
        """Define optimizable parameters."""
        return []

    @property
    def name(self) -> str:
        return self.__class__.__name__

    def set_price(self, price: float):
        """Set current price for strategy calculations."""
        self.price = price
