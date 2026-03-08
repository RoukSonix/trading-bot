"""
AIGridStrategy - Grid Trading Strategy for Jesse

Grid trading strategy with bidirectional support, per-level TP/SL,
trailing stops, and multi-timeframe trend detection.
"""

from jesse.strategies import Strategy
import jesse.indicators as ta
from jesse import utils

from .grid_logic import (
    GridManager, GridConfig,
    TrailingStopManager,
    calculate_tp, calculate_sl, detect_trend,
)


class AIGridStrategy(Strategy):
    """
    Grid Trading Strategy for Jesse framework.

    Places buy orders below current price and sell orders above.
    When price crosses a level, a trade is executed and opposite level is created.
    Supports bidirectional filtering based on multi-timeframe trend detection.
    """

    def __init__(self):
        super().__init__()

        # Grid state stored in strategy vars
        self.vars['grid_levels'] = []  # List of grid levels
        self.vars['grid_center'] = None  # Center price for grid
        self.vars['grid_direction'] = 'both'  # 'long_only', 'short_only', or 'both'
        self.vars['last_review_index'] = 0  # For periodic reviews

        # Track filled levels to prevent duplicate trades
        self.vars['filled_levels'] = set()

        # Trailing stop manager (initialized when position opens)
        self.vars['trailing_stop'] = None

    def hyperparameters(self):
        """Strategy hyperparameters for optimization."""
        return [
            {
                'name': 'grid_levels_count',
                'type': int,
                'min': 3,
                'max': 30,
                'default': 10,
            },
            {
                'name': 'grid_spacing_pct',
                'type': float,
                'min': 0.3,
                'max': 5.0,
                'default': 1.5,
            },
            {
                'name': 'amount_pct',
                'type': float,
                'min': 1.0,
                'max': 10.0,
                'default': 5.0,  # % of balance per grid level
            },
            {
                'name': 'atr_period',
                'type': int,
                'min': 7,
                'max': 28,
                'default': 14,
            },
            {
                'name': 'tp_atr_mult',
                'type': float,
                'min': 1.0,
                'max': 4.0,
                'default': 2.0,
            },
            {
                'name': 'sl_atr_mult',
                'type': float,
                'min': 0.5,
                'max': 3.0,
                'default': 1.5,
            },
            {
                'name': 'trailing_activation_pct',
                'type': float,
                'min': 0.5,
                'max': 5.0,
                'default': 1.0,
            },
            {
                'name': 'trailing_distance_pct',
                'type': float,
                'min': 0.3,
                'max': 3.0,
                'default': 0.5,
            },
            {
                'name': 'trend_sma_fast',
                'type': int,
                'min': 5,
                'max': 30,
                'default': 10,
            },
            {
                'name': 'trend_sma_slow',
                'type': int,
                'min': 20,
                'max': 100,
                'default': 50,
            },
            {
                'name': 'max_total_levels',
                'type': int,
                'min': 10,
                'max': 100,
                'default': 40,
            },
        ]

    @property
    def grid_levels(self):
        """Get current grid levels."""
        return self.vars.get('grid_levels', [])

    @grid_levels.setter
    def grid_levels(self, value):
        """Set grid levels."""
        self.vars['grid_levels'] = value

    def should_long(self) -> bool:
        """Check if we should open a long position."""
        if self.position.is_open:
            return False

        # Initialize grid if not done
        if not self.grid_levels:
            self._setup_grid()
            return False  # Don't trade on first setup

        # Direction filter
        if self.vars['grid_direction'] == 'short_only':
            return False

        return self._check_grid_buy_signal()

    def should_short(self) -> bool:
        """Check if we should open a short position."""
        if self.position.is_open:
            return False

        # Initialize grid if not done
        if not self.grid_levels:
            self._setup_grid()
            return False

        # Direction filter
        if self.vars['grid_direction'] == 'long_only':
            return False

        return self._check_grid_sell_signal()

    def go_long(self):
        """Execute long entry."""
        qty = self._calculate_position_size()

        if qty <= 0:
            return

        entry_price = self._get_crossed_buy_level_price()
        self.buy = qty, self.price

        # Set TP/SL using grid_logic functions
        atr = ta.atr(self.candles, self.hp['atr_period'])
        tp_price = calculate_tp(entry_price, 'long', atr, self.hp['tp_atr_mult'])
        sl_price = calculate_sl(entry_price, 'long', atr, self.hp['sl_atr_mult'])

        self.take_profit = qty, tp_price
        self.stop_loss = qty, sl_price

    def go_short(self):
        """Execute short entry."""
        qty = self._calculate_position_size()

        if qty <= 0:
            return

        entry_price = self._get_crossed_sell_level_price()
        self.sell = qty, self.price

        atr = ta.atr(self.candles, self.hp['atr_period'])
        tp_price = calculate_tp(entry_price, 'short', atr, self.hp['tp_atr_mult'])
        sl_price = calculate_sl(entry_price, 'short', atr, self.hp['sl_atr_mult'])

        self.take_profit = qty, tp_price
        self.stop_loss = qty, sl_price

    def filters(self):
        """Pre-trade filters."""
        return [
            self._filter_volatility,
            self._filter_max_grid_levels,
        ]

    def before(self):
        """Called before strategy logic each candle.

        Detects trend using multi-timeframe data (4h candles if available)
        and sets grid direction accordingly.
        """
        # Use 4h candles for trend if available, else fall back to current timeframe
        try:
            candles_4h = self.get_candles(self.exchange, self.symbol, '4h')
            closes = list(candles_4h[:, 2])  # close prices
        except Exception:
            closes = list(self.candles[:, 2]) if self.candles is not None else []

        if closes:
            trend = detect_trend(
                closes,
                fast_period=self.hp['trend_sma_fast'],
                slow_period=self.hp['trend_sma_slow'],
            )
            if trend == 'uptrend':
                self.vars['grid_direction'] = 'long_only'
            elif trend == 'downtrend':
                self.vars['grid_direction'] = 'short_only'
            else:
                self.vars['grid_direction'] = 'both'

    def after(self):
        """Called after strategy logic each candle."""
        pass

    def update_position(self):
        """Called every candle when position is open. Manages trailing stop."""
        tsm = self.vars.get('trailing_stop')
        if tsm is None:
            return

        new_stop = tsm.update(self.price)
        if new_stop is not None:
            qty = abs(self.position.qty)
            self.stop_loss = qty, new_stop

    def on_open_position(self, order):
        """Called when position opens. Initialize trailing stop."""
        side = 'long' if self.is_long else 'short'
        tsm = TrailingStopManager(
            activation_pct=self.hp['trailing_activation_pct'],
            distance_pct=self.hp['trailing_distance_pct'],
        )
        tsm.start(self.position.entry_price, side)
        self.vars['trailing_stop'] = tsm

    def on_close_position(self, order, closed_trade):
        """Called when position closes."""
        self.vars['grid_levels'] = []
        self.vars['filled_levels'] = set()
        self.vars['trailing_stop'] = None

    # ==================== Grid Logic ====================

    def _setup_grid(self):
        """Initialize grid levels around current price."""
        center = self.price
        spacing = self.hp['grid_spacing_pct'] / 100
        n_levels = self.hp['grid_levels_count']
        direction = self.vars.get('grid_direction', 'both')

        # Cap levels to max_total_levels
        max_per_side = self.hp['max_total_levels'] // 2
        n_levels = min(n_levels, max_per_side)

        levels = []

        # Create sell levels above center (for short_only or both)
        if direction in ('short_only', 'both'):
            for i in range(1, n_levels + 1):
                levels.append({
                    'price': center * (1 + spacing * i),
                    'side': 'sell',
                    'filled': False,
                    'id': f'sell_{i}',
                })

        # Create buy levels below center (for long_only or both)
        if direction in ('long_only', 'both'):
            for i in range(1, n_levels + 1):
                levels.append({
                    'price': center * (1 - spacing * i),
                    'side': 'buy',
                    'filled': False,
                    'id': f'buy_{i}',
                })

        self.grid_levels = levels
        self.vars['grid_center'] = center

    def _check_grid_buy_signal(self) -> bool:
        """Check if price crossed below any buy grid level."""
        if not self.grid_levels:
            return False

        for level in self.grid_levels:
            if level['side'] == 'buy' and not level['filled']:
                if self.price <= level['price']:
                    level['filled'] = True
                    self.vars['filled_levels'].add(level['id'])
                    return True

        return False

    def _check_grid_sell_signal(self) -> bool:
        """Check if price crossed above any sell grid level."""
        if not self.grid_levels:
            return False

        for level in self.grid_levels:
            if level['side'] == 'sell' and not level['filled']:
                if self.price >= level['price']:
                    level['filled'] = True
                    self.vars['filled_levels'].add(level['id'])
                    return True

        return False

    def _get_crossed_buy_level_price(self) -> float:
        """Get the price of the buy level that was crossed."""
        for level in self.grid_levels:
            if level['side'] == 'buy' and level['id'] in self.vars['filled_levels']:
                return level['price']
        return self.price

    def _get_crossed_sell_level_price(self) -> float:
        """Get the price of the sell level that was crossed."""
        for level in self.grid_levels:
            if level['side'] == 'sell' and level['id'] in self.vars['filled_levels']:
                return level['price']
        return self.price

    def _calculate_position_size(self) -> float:
        """Calculate position size based on hp['amount_pct'] % of balance."""
        amount_pct = self.hp['amount_pct'] / 100
        return utils.size_to_qty(
            self.balance * amount_pct,
            self.price
        )

    # ==================== Filters ====================

    def _filter_volatility(self) -> bool:
        """Reject trades in extreme volatility."""
        if self.candles is None or len(self.candles) < 20:
            return True

        atr = ta.atr(self.candles, self.hp['atr_period'])
        volatility = atr / self.price

        # Reject if ATR > 8% of price (extremely volatile)
        return volatility < 0.08

    def _filter_max_grid_levels(self) -> bool:
        """Ensure we don't have too many filled levels."""
        filled_count = len(self.vars['filled_levels'])
        max_filled = self.hp['max_total_levels'] * 0.7
        return filled_count < max_filled
