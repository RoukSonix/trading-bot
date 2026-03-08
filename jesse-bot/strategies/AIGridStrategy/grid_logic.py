"""
Grid trading logic — pure Python, no Jesse dependency.

Extracted for testability outside Docker/Redis environment.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GridConfig:
    """Grid configuration parameters."""
    grid_levels_count: int = 10
    grid_spacing_pct: float = 1.5
    amount_pct: float = 5.0
    atr_period: int = 14
    tp_atr_mult: float = 2.0
    sl_atr_mult: float = 1.5


class GridManager:
    """
    Manages grid levels and signal detection.
    
    Pure logic — no exchange, no Jesse dependency.
    """

    def __init__(self, config: Optional[GridConfig] = None):
        self.config = config or GridConfig()
        self.levels: list[dict] = []
        self.center: Optional[float] = None
        self.direction: str = 'both'  # 'long', 'short', or 'both'
        self.filled_levels: set[str] = set()

    def setup_grid(self, center_price: float) -> list[dict]:
        """Initialize grid levels around center price."""
        spacing = self.config.grid_spacing_pct / 100
        n_levels = self.config.grid_levels_count

        levels = []

        # Sell levels above center
        for i in range(1, n_levels + 1):
            levels.append({
                'price': center_price * (1 + spacing * i),
                'side': 'sell',
                'filled': False,
                'id': f'sell_{i}',
            })

        # Buy levels below center
        for i in range(1, n_levels + 1):
            levels.append({
                'price': center_price * (1 - spacing * i),
                'side': 'buy',
                'filled': False,
                'id': f'buy_{i}',
            })

        self.levels = levels
        self.center = center_price
        self.filled_levels = set()
        return levels

    def check_buy_signal(self, current_price: float) -> bool:
        """Check if price crossed below any unfilled buy level."""
        if not self.levels:
            return False

        for level in self.levels:
            if level['side'] == 'buy' and not level['filled']:
                if current_price <= level['price']:
                    level['filled'] = True
                    self.filled_levels.add(level['id'])
                    return True
        return False

    def check_sell_signal(self, current_price: float) -> bool:
        """Check if price crossed above any unfilled sell level."""
        if not self.levels:
            return False

        for level in self.levels:
            if level['side'] == 'sell' and not level['filled']:
                if current_price >= level['price']:
                    level['filled'] = True
                    self.filled_levels.add(level['id'])
                    return True
        return False

    def get_crossed_buy_level_price(self) -> Optional[float]:
        """Get price of most recently crossed buy level."""
        for level in self.levels:
            if level['side'] == 'buy' and level['id'] in self.filled_levels:
                return level['price']
        return None

    def get_crossed_sell_level_price(self) -> Optional[float]:
        """Get price of most recently crossed sell level."""
        for level in self.levels:
            if level['side'] == 'sell' and level['id'] in self.filled_levels:
                return level['price']
        return None

    def reset(self):
        """Reset grid state (after position close)."""
        self.levels = []
        self.center = None
        self.filled_levels = set()

    def filter_max_levels(self, max_fill_pct: float = 0.7) -> bool:
        """Check if we haven't exceeded max filled levels."""
        max_filled = self.config.grid_levels_count * 2 * max_fill_pct
        return len(self.filled_levels) < max_filled

    @property
    def buy_levels(self) -> list[dict]:
        """Get all buy levels sorted by price (highest first)."""
        return sorted(
            [l for l in self.levels if l['side'] == 'buy'],
            key=lambda x: x['price'],
            reverse=True,
        )

    @property
    def sell_levels(self) -> list[dict]:
        """Get all sell levels sorted by price (lowest first)."""
        return sorted(
            [l for l in self.levels if l['side'] == 'sell'],
            key=lambda x: x['price'],
        )

    @property
    def unfilled_count(self) -> int:
        """Count of unfilled levels."""
        return sum(1 for l in self.levels if not l['filled'])

    @property
    def filled_count(self) -> int:
        """Count of filled levels."""
        return len(self.filled_levels)
