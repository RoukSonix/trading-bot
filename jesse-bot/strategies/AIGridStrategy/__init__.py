"""
AIGridStrategy - Grid Trading Strategy for Jesse

Grid trading strategy with bidirectional support, per-level TP/SL,
trailing stops, multi-timeframe trend detection, AI integration,
factor analysis, and news sentiment.
"""

import logging

from jesse.strategies import Strategy
import jesse.indicators as ta
from jesse import utils
from loguru import logger

from .grid_logic import (
    GridManager, GridConfig,
    TrailingStopManager,
    calculate_tp, calculate_sl, detect_trend,
)
from .ai_mixin import AIMixin
from .factors_mixin import FactorsMixin
from .sentiment_mixin import SentimentMixin

logger = logging.getLogger(__name__)


class AIGridStrategy(Strategy):
    """
    Grid Trading Strategy for Jesse framework.

    Places buy orders below current price and sell orders above.
    When price crosses a level, a trade is executed and opposite level is created.
    Supports bidirectional filtering based on multi-timeframe trend detection.
    Uses GridManager from grid_logic.py as the canonical grid implementation.
    AI integration provides periodic market analysis and position review.
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

        # AI candle counter
        self.vars['candle_count'] = 0
        self.vars['last_ai_analysis'] = None
        self.vars['last_factors'] = None
        self.vars['last_sentiment'] = None

        # Initialize mixins
        self._ai_mixin = AIMixin()
        self._factors_mixin = FactorsMixin()
        self._sentiment_mixin = SentimentMixin(cache_interval_candles=60)

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
            {
                'name': 'ai_review_interval',
                'type': int,
                'min': 15,
                'max': 240,
                'default': 60,
            },
            {
                'name': 'ai_enabled',
                'type': bool,
                'default': True,
            },
            {
                'name': 'min_grid_suitability',
                'type': float,
                'min': 0.1,
                'max': 0.9,
                'default': 0.3,
            },
            {
                'name': 'sentiment_weight',
                'type': float,
                'min': 0.0,
                'max': 1.0,
                'default': 0.3,
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
            self._filter_grid_suitability,
        ]

    def before(self):
        """Called before strategy logic each candle.

        Detects trend using multi-timeframe data (4h candles if available)
        and sets grid direction accordingly. Rebuilds grid when direction changes.
        Calculates factors and ticks sentiment cache.
        Periodically runs AI analysis when ai_enabled=True.
        """
        # Increment candle counter
        self.vars['candle_count'] += 1

        # Tick sentiment cache
        self._sentiment_mixin.tick()

        # Calculate factors from current candles
        if self.candles is not None and len(self.candles) >= 20:
            factors = self._factors_mixin.calculate_factors(self.candles)
            self.vars['last_factors'] = factors

        # Cache sentiment
        self.vars['last_sentiment'] = self._sentiment_mixin.get_sentiment_detail()

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

        # AI periodic analysis (with factors + sentiment context)
        if self.hp.get('ai_enabled', True):
            interval = self.hp.get('ai_review_interval', 60)
            if self.vars['candle_count'] % interval == 0:
                self._run_ai_analysis()

    def after(self):
        """Called after strategy logic each candle."""
        pass

    def update_position(self):
        """Called every candle when position is open. Manages trailing stop and AI review."""
        # Trailing stop update
        tsm = self.vars.get('trailing_stop')
        if tsm is not None:
            new_stop = tsm.update(self.price)
            if new_stop is not None:
                qty = abs(self.position.qty)
                self.stop_loss = qty, new_stop

        # AI position review
        if self.hp.get('ai_enabled', True):
            interval = self.hp.get('ai_review_interval', 60)
            if self.vars['candle_count'] % interval == 0:
                self._run_ai_position_review()

    def on_open_position(self, order):
        """Called when position opens. Initialize trailing stop and log AI context."""
        side = 'long' if self.is_long else 'short'
        tsm = TrailingStopManager(
            activation_pct=self.hp['trailing_activation_pct'],
            distance_pct=self.hp['trailing_distance_pct'],
        )
        tsm.start(self.position.entry_price, side)
        self.vars['trailing_stop'] = tsm

        # Log AI analysis context if available
        analysis = self.vars.get('last_ai_analysis')
        if analysis:
            logger.info(
                f"Position opened ({side}) with AI context: "
                f"trend={analysis.get('trend')}, "
                f"confidence={analysis.get('confidence')}, "
                f"recommendation={analysis.get('recommendation')}"
            )

    def on_close_position(self, order, closed_trade):
        """Called when position closes."""
        gm = self._get_grid_manager()
        gm.reset()
        self.vars['filled_levels'] = set()
        self.vars['trailing_stop'] = None

    # ==================== AI Integration ====================

    def _run_ai_analysis(self):
        """Run AI market analysis and update grid direction if needed."""
        try:
            candle_data = self.candles.tolist() if self.candles is not None else []
            atr = ta.atr(self.candles, self.hp['atr_period']) if self.candles is not None else 0.0

            indicators = {
                'rsi': ta.rsi(self.candles) if self.candles is not None else 50.0,
                'atr': atr,
                'close': self.price,
            }

            # Enrich indicators with factors and sentiment context
            factors = self.vars.get('last_factors')
            if factors:
                indicators['factors_context'] = self._factors_mixin.factors_to_ai_context(factors)
                indicators['grid_suitability'] = self._factors_mixin.grid_suitability_score(factors)
                indicators['regime'] = self._factors_mixin.detect_regime(factors)

            sentiment = self.vars.get('last_sentiment')
            if sentiment:
                indicators['sentiment_context'] = self._sentiment_mixin.sentiment_to_ai_context()
                indicators['sentiment_score'] = sentiment.get('score', 0.0)
                indicators['sentiment_weight'] = self.hp.get('sentiment_weight', 0.3)

            analysis = self._ai_mixin.ai_analyze_market(candle_data, indicators)
            self.vars['last_ai_analysis'] = analysis

            # Apply AI-suggested direction if confidence is high enough
            grid_params = analysis.get('grid_params', {})
            if analysis.get('confidence', 0) > 0.5 and 'direction' in grid_params:
                gm = self._get_grid_manager()
                new_dir = grid_params['direction']
                if new_dir != gm.direction:
                    gm.reset()
                    gm.setup_grid(self.price, new_dir)
                    self.vars['filled_levels'] = set()
                    self.vars['prev_grid_direction'] = new_dir

            logger.info(
                f"AI analysis: trend={analysis.get('trend')}, "
                f"confidence={analysis.get('confidence'):.2f}, "
                f"recommendation={analysis.get('recommendation')}"
            )
        except Exception as e:
            logger.warning(f"AI analysis failed: {e}")

    def _run_ai_position_review(self):
        """Run AI position review and act on recommendation."""
        try:
            side = 'long' if self.is_long else 'short'
            entry = self.position.entry_price
            pnl_pct = (self.price - entry) / entry * 100
            if side == 'short':
                pnl_pct = -pnl_pct

            position_info = {
                'entry_price': entry,
                'current_price': self.price,
                'side': side,
                'qty': abs(self.position.qty),
                'pnl_pct': pnl_pct,
            }

            # Map grid_direction to trend label for AI
            direction = self.vars.get('prev_grid_direction', 'both')
            trend_map = {'long_only': 'uptrend', 'short_only': 'downtrend', 'both': 'neutral'}
            trend = trend_map.get(direction, 'neutral')

            market_data = {
                'rsi': ta.rsi(self.candles) if self.candles is not None else 50.0,
                'atr': ta.atr(self.candles, self.hp['atr_period']) if self.candles is not None else 0.0,
                'trend': trend,
            }

            decision = self._ai_mixin.ai_review_position(position_info, market_data)
            logger.info(f"AI position review: {decision}")

            if decision == 'STOP':
                self.liquidate()
        except Exception as e:
            logger.warning(f"AI position review failed: {e}")

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

    def _filter_grid_suitability(self) -> bool:
        """Reject trades when market is unsuitable for grid trading."""
        factors = self.vars.get('last_factors')
        if factors is None:
            return True  # No data yet — allow trades

        suitability = self._factors_mixin.grid_suitability_score(factors)
        threshold = self.hp.get('min_grid_suitability', 0.3)
        return suitability >= threshold
