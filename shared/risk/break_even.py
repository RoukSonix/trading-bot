"""Break-even stop manager for grid level positions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from binance_bot.strategies.base import GridLevel


class BreakEvenManager:
    """Move stop-loss to break-even after reaching a profit threshold."""

    def __init__(self, activation_pct: float = 1.0, offset_pct: float = 0.1):
        """Initialize break-even manager.

        Args:
            activation_pct: Activate break-even when profit reaches this %.
            offset_pct: Small offset above/below entry to ensure a tiny profit.
        """
        self.activation_pct = activation_pct
        self.offset_pct = offset_pct

    def check_and_activate(self, level: GridLevel, current_price: float) -> bool:
        """Check if break-even should activate.

        When price reaches activation_pct profit, moves stop_loss to
        fill_price +/- offset (ensuring break-even + small offset).

        Args:
            level: The filled grid level.
            current_price: Current market price.

        Returns:
            True if break-even was just activated (stop_loss was moved).
        """
        if not level.filled or level.fill_price == 0:
            return False

        if level.break_even_triggered:
            return False

        is_long = level.amount > 0

        if is_long:
            profit_pct = ((current_price - level.fill_price) / level.fill_price) * 100
            if profit_pct >= self.activation_pct:
                # Move SL to entry + offset
                level.stop_loss = level.fill_price * (1 + self.offset_pct / 100)
                level.break_even_triggered = True
                logger.info(
                    f"Break-even activated (long): level ${level.fill_price:,.2f} "
                    f"new SL=${level.stop_loss:,.2f}"
                )
                return True
        else:
            # Short position
            profit_pct = ((level.fill_price - current_price) / level.fill_price) * 100
            if profit_pct >= self.activation_pct:
                # Move SL to entry - offset (for short, SL above entry means loss)
                level.stop_loss = level.fill_price * (1 - self.offset_pct / 100)
                level.break_even_triggered = True
                logger.info(
                    f"Break-even activated (short): level ${level.fill_price:,.2f} "
                    f"new SL=${level.stop_loss:,.2f}"
                )
                return True

        return False
