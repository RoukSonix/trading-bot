"""Trailing stop-loss manager for grid level positions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from binance_bot.strategies.base import GridLevel


class TrailingStopManager:
    """Manage trailing stop-loss for active grid positions."""

    def __init__(self, trail_pct: float = 1.0, activation_pct: float = 0.5):
        """Initialize trailing stop manager.

        Args:
            trail_pct: Trailing distance as a percentage.
            activation_pct: Activate trailing after this % profit from fill.
        """
        self.trail_pct = trail_pct
        self.activation_pct = activation_pct

    def update(self, level: GridLevel, current_price: float) -> bool:
        """Update trailing stop and check if triggered.

        Tracks the best price since fill (high for long, low for short).
        Once the position reaches activation_pct profit, the trailing stop
        is placed trail_pct below the high (long) or above the low (short).

        Args:
            level: The filled grid level.
            current_price: Current market price.

        Returns:
            True if the trailing stop was triggered (should close position).
        """
        if not level.filled or level.fill_price == 0:
            return False

        is_long = level.amount > 0

        if is_long:
            # Track highest price since fill
            if current_price > level.trailing_high:
                level.trailing_high = current_price

            # Check activation threshold
            profit_pct = ((level.trailing_high - level.fill_price) / level.fill_price) * 100
            if profit_pct < self.activation_pct:
                return False

            # Calculate trailing stop price
            trail_price = self.calculate_trail_price(level.trailing_high, "long")
            level.trailing_stop = self.trail_pct

            # Triggered if price drops below trailing stop
            if current_price <= trail_price:
                logger.info(
                    f"Trailing stop triggered: level ${level.fill_price:,.2f} "
                    f"trail=${trail_price:,.2f} current=${current_price:,.2f}"
                )
                return True
        else:
            # Short: track lowest price since fill
            if current_price < level.trailing_low:
                level.trailing_low = current_price

            # Check activation threshold
            profit_pct = ((level.fill_price - level.trailing_low) / level.fill_price) * 100
            if profit_pct < self.activation_pct:
                return False

            # Calculate trailing stop price
            trail_price = self.calculate_trail_price(level.trailing_low, "short")
            level.trailing_stop = self.trail_pct

            # Triggered if price rises above trailing stop
            if current_price >= trail_price:
                logger.info(
                    f"Trailing stop triggered (short): level ${level.fill_price:,.2f} "
                    f"trail=${trail_price:,.2f} current=${current_price:,.2f}"
                )
                return True

        return False

    def calculate_trail_price(self, extreme: float, side: str) -> float:
        """Calculate current trailing stop price.

        Args:
            extreme: Highest price (long) or lowest price (short) since fill.
            side: "long" or "short".

        Returns:
            The trailing stop price.
        """
        if side == "long":
            return extreme * (1 - self.trail_pct / 100)
        else:
            return extreme * (1 + self.trail_pct / 100)
