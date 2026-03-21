"""
Grid trading logic — pure Python, no Jesse dependency.

Extracted for testability outside Docker/Redis environment.
"""

from dataclasses import dataclass, field
from typing import Optional

from shared.constants import MAX_GRID_FILL_PCT


@dataclass
class GridConfig:
    """Grid configuration parameters."""
    grid_levels_count: int = 10
    grid_spacing_pct: float = 1.5
    amount_pct: float = 5.0
    atr_period: int = 14
    tp_atr_mult: float = 2.0
    sl_atr_mult: float = 1.5
    max_total_levels: int = 40
    trailing_activation_pct: float = 1.0
    trailing_distance_pct: float = 0.5
    trend_sma_fast: int = 10
    trend_sma_slow: int = 50


class GridManager:
    """
    Manages grid levels and signal detection.

    Pure logic — no exchange, no Jesse dependency.
    """

    def __init__(self, config: Optional[GridConfig] = None):
        self.config = config or GridConfig()
        self.levels: list[dict] = []
        self.center: Optional[float] = None
        self.direction: str = 'both'  # 'long_only', 'short_only', or 'both'
        self.filled_levels: set[str] = set()
        self._last_filled_buy: Optional[str] = None
        self._last_filled_sell: Optional[str] = None

    def setup_grid(self, center_price: float, direction: Optional[str] = None) -> list[dict]:
        """Initialize grid levels around center price.

        Args:
            center_price: Center price for the grid.
            direction: 'long_only', 'short_only', or 'both'. If None, uses self.direction.
        """
        if direction is not None:
            self.direction = direction
        spacing = self.config.grid_spacing_pct / 100
        n_levels = self.config.grid_levels_count

        # Cap levels to max_total_levels
        max_per_side = self.config.max_total_levels // 2
        n_levels = min(n_levels, max_per_side)

        levels = []

        # Sell levels above center (for short_only or both)
        if self.direction in ('short_only', 'both'):
            for i in range(1, n_levels + 1):
                levels.append({
                    'price': center_price * (1 + spacing * i),
                    'side': 'sell',
                    'filled': False,
                    'id': f'sell_{i}',
                })

        # Buy levels below center (for long_only or both)
        if self.direction in ('long_only', 'both'):
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
        self._last_filled_buy = None
        self._last_filled_sell = None
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
                    self._last_filled_buy = level['id']
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
                    self._last_filled_sell = level['id']
                    return True
        return False

    def get_crossed_buy_level_price(self) -> Optional[float]:
        """Get price of most recently crossed buy level."""
        if self._last_filled_buy is None:
            return None
        for level in self.levels:
            if level['id'] == self._last_filled_buy:
                return level['price']
        return None

    def get_crossed_sell_level_price(self) -> Optional[float]:
        """Get price of most recently crossed sell level."""
        if self._last_filled_sell is None:
            return None
        for level in self.levels:
            if level['id'] == self._last_filled_sell:
                return level['price']
        return None

    def reset(self):
        """Reset grid state (after position close)."""
        self.levels = []
        self.center = None
        self.filled_levels = set()
        self._last_filled_buy = None
        self._last_filled_sell = None

    def filter_max_levels(self, max_fill_pct: float = MAX_GRID_FILL_PCT) -> bool:
        """Check if we haven't exceeded max filled levels."""
        total_levels = len(self.levels) if self.levels else self.config.grid_levels_count * 2
        max_filled = total_levels * max_fill_pct
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

    def to_dict(self) -> dict:
        """Serialize grid state to dict (for dashboard/API)."""
        return {
            'config': {
                'grid_levels_count': self.config.grid_levels_count,
                'grid_spacing_pct': self.config.grid_spacing_pct,
                'amount_pct': self.config.amount_pct,
                'atr_period': self.config.atr_period,
                'tp_atr_mult': self.config.tp_atr_mult,
                'sl_atr_mult': self.config.sl_atr_mult,
                'max_total_levels': self.config.max_total_levels,
                'trailing_activation_pct': self.config.trailing_activation_pct,
                'trailing_distance_pct': self.config.trailing_distance_pct,
                'trend_sma_fast': self.config.trend_sma_fast,
                'trend_sma_slow': self.config.trend_sma_slow,
            },
            'levels': [dict(l) for l in self.levels],
            'center': self.center,
            'direction': self.direction,
            'filled_levels': list(self.filled_levels),
            '_last_filled_buy': self._last_filled_buy,
            '_last_filled_sell': self._last_filled_sell,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'GridManager':
        """Deserialize grid state from dict."""
        config_data = data.get('config', {})
        config = GridConfig(**config_data)
        gm = cls(config)
        gm.levels = data.get('levels', [])
        gm.center = data.get('center')
        gm.direction = data.get('direction', 'both')
        gm.filled_levels = set(data.get('filled_levels', []))
        gm._last_filled_buy = data.get('_last_filled_buy')
        gm._last_filled_sell = data.get('_last_filled_sell')
        return gm


def calculate_tp(entry_price: float, side: str, atr: float, tp_mult: float) -> float:
    """Calculate take-profit price.

    Args:
        entry_price: Entry price of the position.
        side: 'long' or 'short'.
        atr: Current ATR value.
        tp_mult: ATR multiplier for TP distance.

    Returns:
        Take-profit price.
    """
    if side == 'long':
        return entry_price + atr * tp_mult
    else:
        return entry_price - atr * tp_mult


def calculate_sl(entry_price: float, side: str, atr: float, sl_mult: float) -> float:
    """Calculate stop-loss price.

    Args:
        entry_price: Entry price of the position.
        side: 'long' or 'short'.
        atr: Current ATR value.
        sl_mult: ATR multiplier for SL distance.

    Returns:
        Stop-loss price.
    """
    if side == 'long':
        return entry_price - atr * sl_mult
    else:
        return entry_price + atr * sl_mult


def detect_trend(prices: list[float], fast_period: int = 10, slow_period: int = 50) -> str:
    """Detect trend using SMA crossover.

    Args:
        prices: List of closing prices (most recent last).
        fast_period: Fast SMA period.
        slow_period: Slow SMA period.

    Returns:
        'uptrend', 'downtrend', or 'neutral' if not enough data
        or if fast_period >= slow_period (invalid crossover).
    """
    if fast_period >= slow_period:
        return 'neutral'

    if len(prices) < slow_period:
        return 'neutral'

    fast_sma = sum(prices[-fast_period:]) / fast_period
    slow_sma = sum(prices[-slow_period:]) / slow_period

    if fast_sma > slow_sma:
        return 'uptrend'
    elif fast_sma < slow_sma:
        return 'downtrend'
    else:
        return 'neutral'


class TrailingStopManager:
    """Manages trailing stop logic for open positions.

    Pure logic — no exchange, no Jesse dependency.
    """

    def __init__(self, activation_pct: float = 1.0, distance_pct: float = 0.5):
        """
        Args:
            activation_pct: Minimum profit % to activate trailing stop.
            distance_pct: Trail distance as % from peak price.
        """
        self.activation_pct = activation_pct
        self.distance_pct = distance_pct
        self.entry_price: Optional[float] = None
        self.peak_price: Optional[float] = None
        self.current_stop: Optional[float] = None
        self.activated: bool = False
        self._side: Optional[str] = None

    def start(self, entry_price: float, side: str):
        """Initialize trailing stop for a new position.

        Args:
            entry_price: Position entry price.
            side: 'long' or 'short'.
        """
        self.entry_price = entry_price
        self.peak_price = entry_price
        self.current_stop = None
        self.activated = False
        self._side = side

    def update(self, current_price: float) -> Optional[float]:
        """Update trailing stop with current price.

        Args:
            current_price: Current market price.

        Returns:
            New stop-loss price if updated, None if no change.
        """
        if self.entry_price is None:
            return None

        side = self._side

        # Update peak price
        if side == 'long':
            if current_price > self.peak_price:
                self.peak_price = current_price
        else:  # short
            if current_price < self.peak_price:
                self.peak_price = current_price

        # Check activation threshold
        if not self.activated:
            if side == 'long':
                profit_pct = (self.peak_price - self.entry_price) / self.entry_price * 100
            else:
                profit_pct = (self.entry_price - self.peak_price) / self.entry_price * 100

            if profit_pct >= self.activation_pct:
                self.activated = True
            else:
                return None

        # Calculate new trailing stop
        if side == 'long':
            new_stop = self.peak_price * (1 - self.distance_pct / 100)
            # Only tighten, never loosen
            if self.current_stop is None or new_stop > self.current_stop:
                self.current_stop = new_stop
                return self.current_stop
        else:  # short
            new_stop = self.peak_price * (1 + self.distance_pct / 100)
            # Only tighten (for short, tighter means lower stop)
            if self.current_stop is None or new_stop < self.current_stop:
                self.current_stop = new_stop
                return self.current_stop

        return None

    def reset(self):
        """Reset trailing stop state."""
        self.entry_price = None
        self.peak_price = None
        self.current_stop = None
        self.activated = False
