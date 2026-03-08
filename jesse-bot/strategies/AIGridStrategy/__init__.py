"""
AIGridStrategy - Grid Trading Strategy for Jesse

Basic grid trading strategy that places buy orders below and sell orders above
the current price. When price crosses a level, it triggers a trade and creates
a new level on the opposite side.
"""

from jesse.strategies import Strategy
import jesse.indicators as ta
from jesse import utils


class AIGridStrategy(Strategy):
    """
    Grid Trading Strategy for Jesse framework.
    
    Places buy orders below current price and sell orders above.
    When price crosses a level, a trade is executed and opposite level is created.
    """

    def __init__(self):
        super().__init__()
        
        # Grid state stored in strategy vars
        self.vars['grid_levels'] = []  # List of grid levels
        self.vars['grid_center'] = None  # Center price for grid
        self.vars['grid_direction'] = 'both'  # 'long', 'short', or 'both'
        self.vars['last_review_index'] = 0  # For periodic reviews
        
        # Track filled levels to prevent duplicate trades
        self.vars['filled_levels'] = set()

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
        # If position already open, don't enter new trades
        if self.position.is_open:
            return False
        
        # Initialize grid if not done
        if not self.grid_levels:
            self._setup_grid()
            return False  # Don't trade on first setup
        
        # Check if price crossed below any buy grid level
        return self._check_grid_buy_signal()

    def should_short(self) -> bool:
        """Check if we should open a short position."""
        # If position already open, don't enter new trades
        if self.position.is_open:
            return False
        
        # Initialize grid if not done
        if not self.grid_levels:
            self._setup_grid()
            return False
        
        # Check if price crossed above any sell grid level
        return self._check_grid_sell_signal()

    def go_long(self):
        """Execute long entry."""
        # Calculate position size
        qty = self._calculate_position_size()
        
        if qty <= 0:
            return
        
        # Get the price level that was crossed
        entry_price = self._get_crossed_buy_level_price()
        
        # Place market order
        self.buy = qty, self.price
        
        # Set TP/SL using ATR
        atr = ta.atr(self.candles, self.hp['atr_period'])
        tp_price = entry_price + atr * self.hp['tp_atr_mult']
        sl_price = entry_price - atr * self.hp['sl_atr_mult']
        
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
        tp_price = entry_price - atr * self.hp['tp_atr_mult']
        sl_price = entry_price + atr * self.hp['sl_atr_mult']
        
        self.take_profit = qty, tp_price
        self.stop_loss = qty, sl_price

    def filters(self):
        """Pre-trade filters."""
        return [
            self._filter_volatility,
            self._filter_max_grid_levels,
        ]

    def before(self):
        """Called before strategy logic each candle."""
        # Could add AI review here in Sprint M3
        pass

    def after(self):
        """Called after strategy logic each candle."""
        pass

    def update_position(self):
        """Called every candle when position is open."""
        # Could add trailing stop logic here
        pass

    def on_open_position(self, order):
        """Called when position opens."""
        pass

    def on_close_position(self, order, closed_trade):
        """Called when position closes."""
        # Reset grid after position closes
        self.vars['grid_levels'] = []
        self.vars['filled_levels'] = set()

    # ==================== Grid Logic ====================

    def _setup_grid(self):
        """Initialize grid levels around current price."""
        center = self.price
        spacing = self.hp['grid_spacing_pct'] / 100
        n_levels = self.hp['grid_levels_count']
        
        levels = []
        
        # Create sell levels above center
        for i in range(1, n_levels + 1):
            levels.append({
                'price': center * (1 + spacing * i),
                'side': 'sell',
                'filled': False,
                'id': f'sell_{i}',
            })
        
        # Create buy levels below center
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
        max_filled = self.hp['grid_levels_count'] * 2 * 0.7  # 70% of levels
        
        return filled_count < max_filled
