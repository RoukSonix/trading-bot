"""
AIGridStrategy - Grid Trading Strategy for Jesse

Grid trading strategy with bidirectional support, per-level TP/SL,
trailing stops, and multi-timeframe trend detection.
"""

from jesse.strategies import Strategy
import jesse.indicators as ta
from jesse import utils
from loguru import logger

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

    Uses GridManager from grid_logic.py as the canonical grid implementation.
    """

    def __init__(self):
        super().__init__()

        # Grid manager — canonical grid logic from grid_logic.py
        self.vars['grid_manager'] = None  # Initialized lazily with config from hp

        # Track previous grid direction for rebuild on trend change
        self.vars['prev_grid_direction'] = None

        # Track filled levels to prevent duplicate trades
        self.vars['filled_levels'] = set()

        # Trailing stop manager (initialized when position opens)
        self.vars['trailing_stop'] = None

    def _get_grid_manager(self) -> GridManager:
        """Get or create the GridManager instance with current hyperparameters."""
        if self.vars['grid_manager'] is None:
            config = GridConfig(
                grid_levels_count=self.hp['grid_levels_count'],
                grid_spacing_pct=self.hp['grid_spacing_pct'],
                amount_pct=self.hp['amount_pct'],
                atr_period=self.hp['atr_period'],
                tp_atr_mult=self.hp['tp_atr_mult'],
                sl_atr_mult=self.hp['sl_atr_mult'],
                max_total_levels=self.hp['max_total_levels'],
                trailing_activation_pct=self.hp['trailing_activation_pct'],
                trailing_distance_pct=self.hp['trailing_distance_pct'],
                trend_sma_fast=self.hp['trend_sma_fast'],
                trend_sma_slow=self.hp['trend_sma_slow'],
            )
            self.vars['grid_manager'] = GridManager(config)
        return self.vars['grid_manager']

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
        """Get current grid levels from GridManager."""
        gm = self._get_grid_manager()
        return gm.levels

    def should_long(self) -> bool:
        """Check if we should open a long position."""
        if self.position.is_open:
            return False

        gm = self._get_grid_manager()

        # Initialize grid if not done
        if not gm.levels:
            gm.setup_grid(self.price, gm.direction)
            return False  # Don't trade on first setup

        # Direction filter
        if gm.direction == 'short_only':
            return False

        return gm.check_buy_signal(self.price)

    def should_short(self) -> bool:
        """Check if we should open a short position."""
        if self.position.is_open:
            return False

        gm = self._get_grid_manager()

        # Initialize grid if not done
        if not gm.levels:
            gm.setup_grid(self.price, gm.direction)
            return False

        # Direction filter
        if gm.direction == 'long_only':
            return False

        return gm.check_sell_signal(self.price)

    def go_long(self):
        """Execute long entry."""
        qty = self._calculate_position_size()

        if qty <= 0:
            return

        gm = self._get_grid_manager()
        entry_price = gm.get_crossed_buy_level_price() or self.price
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

        gm = self._get_grid_manager()
        entry_price = gm.get_crossed_sell_level_price() or self.price
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
        and sets grid direction accordingly. Rebuilds grid when direction changes.
        """
        # Use 4h candles for trend if available, else fall back to current timeframe
        try:
            candles_4h = self.get_candles(self.exchange, self.symbol, '4h')
            closes = list(candles_4h[:, 2])  # close prices
        except Exception as e:
            logger.warning(f"4h candles unavailable, falling back to 1h: {e}")
            closes = list(self.candles[:, 2]) if self.candles is not None else []

        if closes:
            trend = detect_trend(
                closes,
                fast_period=self.hp['trend_sma_fast'],
                slow_period=self.hp['trend_sma_slow'],
            )
            if trend == 'uptrend':
                new_direction = 'long_only'
            elif trend == 'downtrend':
                new_direction = 'short_only'
            else:
                new_direction = 'both'

            gm = self._get_grid_manager()
            prev_direction = self.vars.get('prev_grid_direction')

            # Rebuild grid when trend direction changes
            if prev_direction is not None and new_direction != prev_direction:
                gm.reset()
                gm.setup_grid(self.price, new_direction)
                self.vars['filled_levels'] = set()

            gm.direction = new_direction
            self.vars['prev_grid_direction'] = new_direction

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
        gm = self._get_grid_manager()
        gm.reset()
        self.vars['filled_levels'] = set()
        self.vars['trailing_stop'] = None

    # ==================== Helpers ====================

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
        gm = self._get_grid_manager()
        return gm.filter_max_levels()
