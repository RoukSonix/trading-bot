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

from shared.constants import MAX_ATR_VOLATILITY, JESSE_MIN_GRID_SUITABILITY

logger = logging.getLogger(__name__)

from .grid_logic import (
    GridManager, GridConfig,
    TrailingStopManager,
    calculate_tp, calculate_sl, detect_trend,
)
from .ai_mixin import AIMixin
from .factors_mixin import FactorsMixin
from .sentiment_mixin import SentimentMixin
from .alerts_mixin import AlertsMixin
from .safety import SafetyManager

# state_provider is at jesse-bot root, not in the strategy package
try:
    from state_provider import export_state
    _HAS_STATE_PROVIDER = True
except ImportError:
    export_state = None
    _HAS_STATE_PROVIDER = False


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
        self._alerts_mixin = AlertsMixin(is_live=False)  # Updated in _update_live_status()

        # Safety manager for live trading
        self._safety_manager = SafetyManager()
        self.vars['peak_equity'] = None
        self.vars['daily_starting_balance'] = None
        self.vars['daily_pnl'] = 0.0

        # Status alert counter
        self.vars['status_alert_counter'] = 0

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
        return self._grid_hyperparameters() + self._ai_hyperparameters()

    @staticmethod
    def _grid_hyperparameters():
        """Grid trading and risk hyperparameters."""
        # Trial 2861 ETH-USDT 1h (Sharpe 2.67 OOS, +4.19% full backtest 15mo)
        return [
            {'name': 'grid_levels_count', 'type': int, 'min': 3, 'max': 30, 'default': 4},
            {'name': 'grid_spacing_pct', 'type': float, 'min': 0.3, 'max': 5.0, 'default': 3.697},
            {'name': 'amount_pct', 'type': float, 'min': 1.0, 'max': 10.0, 'default': 9.988},
            {'name': 'atr_period', 'type': int, 'min': 7, 'max': 28, 'default': 25},
            {'name': 'tp_atr_mult', 'type': float, 'min': 1.0, 'max': 4.0, 'default': 3.465},
            {'name': 'sl_atr_mult', 'type': float, 'min': 0.5, 'max': 3.0, 'default': 2.744},
            {'name': 'trailing_activation_pct', 'type': float, 'min': 0.5, 'max': 5.0, 'default': 3.904},
            {'name': 'trailing_distance_pct', 'type': float, 'min': 0.3, 'max': 3.0, 'default': 0.765},
            {'name': 'trend_sma_fast', 'type': int, 'min': 5, 'max': 30, 'default': 28},
            {'name': 'trend_sma_slow', 'type': int, 'min': 20, 'max': 100, 'default': 63},
            {'name': 'max_total_levels', 'type': int, 'min': 10, 'max': 100, 'default': 21},
        ]

    @staticmethod
    def _ai_hyperparameters():
        """AI, sentiment, and integration hyperparameters."""
        return [
            {'name': 'ai_review_interval', 'type': int, 'min': 15, 'max': 240, 'default': 157},
            {'name': 'min_grid_suitability', 'type': float, 'min': 0.1, 'max': 0.9, 'default': 0.235},
            {'name': 'sentiment_weight', 'type': float, 'min': 0.0, 'max': 1.0, 'default': 0.708},
            {'name': 'state_export_interval', 'type': int, 'min': 5, 'max': 60, 'default': 17},
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
        filters = [
            self._filter_volatility,
            self._filter_max_grid_levels,
            self._filter_grid_suitability,
        ]
        # Add safety filter in live mode
        if self.is_live:
            filters.insert(0, self._filter_safety)
        return filters

    def before(self):
        """Called before strategy logic each candle."""
        self.vars['candle_count'] += 1

        if self.is_live:
            self._update_live_safety()

        self._update_factors_and_sentiment()
        self._update_trend_direction()
        self._maybe_periodic_alerts()

        if self.hp.get('ai_enabled', True):
            interval = self.hp.get('ai_review_interval', 60)
            if self.vars['candle_count'] % interval == 0:
                self._run_ai_analysis()

    def _update_live_safety(self):
        """Track equity and check emergency stop in live mode."""
        import os

        current_equity = self.balance
        if self.vars['peak_equity'] is None or current_equity > self.vars['peak_equity']:
            self.vars['peak_equity'] = current_equity
        if self.vars['daily_starting_balance'] is None:
            self.vars['daily_starting_balance'] = current_equity

        stop_file = os.environ.get('EMERGENCY_STOP_FILE', 'EMERGENCY_STOP')
        if self._safety_manager.emergency_stop_check(stop_file):
            logger.warning("EMERGENCY STOP triggered — liquidating all positions")
            if self.position.is_open:
                self.liquidate()
            if self.hp.get('alerts_enabled', True):
                self._alerts_mixin.send_error_alert(
                    "EMERGENCY STOP triggered", context="safety"
                )

    def _update_factors_and_sentiment(self):
        """Calculate factors and tick sentiment cache."""
        self._sentiment_mixin.tick()

        if self.candles is not None and len(self.candles) >= 20:
            factors = self._factors_mixin.calculate_factors(self.candles)
            self.vars['last_factors'] = factors

        self.vars['last_sentiment'] = self._sentiment_mixin.get_sentiment_detail()

    def _update_trend_direction(self):
        """Detect trend and update grid direction, rebuilding if changed."""
        try:
            candles_4h = self.get_candles(self.exchange, self.symbol, '4h')
            closes = list(candles_4h[:, 4])
        except Exception as e:
            logger.warning(f"4h candles unavailable, falling back to 1h: {e}")
            closes = list(self.candles[:, 4]) if self.candles is not None else []

        if not closes:
            return

        trend = detect_trend(
            closes,
            fast_period=self.hp['trend_sma_fast'],
            slow_period=self.hp['trend_sma_slow'],
        )
        direction_map = {'uptrend': 'long_only', 'downtrend': 'short_only'}
        new_direction = direction_map.get(trend, 'both')

        gm = self._get_grid_manager()
        prev_direction = self.vars.get('prev_grid_direction')

        if prev_direction is not None and new_direction != prev_direction:
            gm.reset()
            gm.setup_grid(self.price, new_direction)
            self.vars['filled_levels'] = set()

        gm.direction = new_direction
        self.vars['prev_grid_direction'] = new_direction

    def _maybe_periodic_alerts(self):
        """Send periodic status alerts."""
        if not self.hp.get('alerts_enabled', True):
            return

        self.vars['status_alert_counter'] += 1
        if self.vars['status_alert_counter'] >= 60:
            self.vars['status_alert_counter'] = 0
            self._alerts_mixin.send_status_alert({
                'status': 'running',
                'symbol': self.symbol,
                'current_price': self.price,
                'total_value': self.balance,
            })

    def after(self):
        """Called after strategy logic each candle. Exports state at configured interval."""
        if not _HAS_STATE_PROVIDER:
            return

        interval = self.hp.get('state_export_interval', 10)
        if interval > 0 and self.vars['candle_count'] % interval == 0:
            try:
                export_state(self)
            except Exception as e:
                logger.warning(f"State export failed: {e}")

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
        """Called when position opens. Initialize trailing stop, send alert, log AI context."""
        side = 'long' if self.is_long else 'short'
        tsm = TrailingStopManager(
            activation_pct=self.hp['trailing_activation_pct'],
            distance_pct=self.hp['trailing_distance_pct'],
        )
        tsm.start(self.position.entry_price, side)
        self.vars['trailing_stop'] = tsm

        # Trade alert
        if self.hp.get('alerts_enabled', True):
            self._alerts_mixin.send_trade_alert({
                'action': 'open',
                'symbol': self.symbol,
                'side': side,
                'price': self.position.entry_price,
                'amount': abs(self.position.qty),
            })

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
        """Called when position closes. Send trade alert with PnL."""
        # Trade alert with PnL
        if self.hp.get('alerts_enabled', True):
            pnl = getattr(closed_trade, 'pnl', 0.0)
            pnl_pct = getattr(closed_trade, 'pnl_percentage', 0.0)
            side = getattr(closed_trade, 'type', 'unknown')
            self._alerts_mixin.send_trade_alert({
                'action': 'close',
                'symbol': self.symbol,
                'side': side,
                'price': getattr(closed_trade, 'exit_price', self.price),
                'amount': abs(getattr(closed_trade, 'qty', 0.0)),
                'pnl': pnl,
                'pnl_pct': pnl_pct,
            })

        # Log trade in live mode
        if self.is_live:
            self._safety_manager.log_trade({
                'symbol': self.symbol,
                'side': side,
                'entry_price': getattr(closed_trade, 'entry_price', 0.0),
                'exit_price': getattr(closed_trade, 'exit_price', self.price),
                'qty': abs(getattr(closed_trade, 'qty', 0.0)),
                'pnl': pnl,
                'pnl_pct': pnl_pct,
            })

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

            ai_symbol = self.symbol.replace("-", "")  # "ETH-USDT" → "ETHUSDT"
            analysis = self._ai_mixin.ai_analyze_market(candle_data, indicators, symbol=ai_symbol)
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

            # Send AI decision alert
            if self.hp.get('alerts_enabled', True):
                self._alerts_mixin.send_ai_decision_alert(analysis)
        except Exception as e:
            logger.warning(f"AI analysis failed: {e}")
            if self.hp.get('alerts_enabled', True):
                self._alerts_mixin.send_error_alert(str(e), context="ai_analysis")

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

            ai_symbol = self.symbol.replace("-", "")  # "ETH-USDT" → "ETHUSDT"
            decision = self._ai_mixin.ai_review_position(
                position_info, market_data,
                symbol=ai_symbol,
                total_balance=self.balance,
            )
            logger.info(f"AI position review: {decision}")

            if decision == 'STOP':
                self.liquidate()
        except Exception as e:
            logger.warning(f"AI position review failed: {e}")
            if self.hp.get('alerts_enabled', True):
                self._alerts_mixin.send_error_alert(str(e), context="ai_position_review")

    # ==================== Helpers ====================

    def _calculate_position_size(self) -> float:
        """Calculate position size based on hp['amount_pct'] % of balance."""
        amount_pct = self.hp['amount_pct'] / 100
        return utils.size_to_qty(
            self.balance * amount_pct,
            self.price
        )

    # ==================== Filters ====================

    def _filter_safety(self) -> bool:
        """Safety filter for live mode — checks position size, daily loss, drawdown."""
        import os

        balance = self.balance
        qty = self._calculate_position_size()
        price = self.price

        max_pos_pct = float(os.environ.get('RISK_MAX_POSITION_PCT', '10'))
        daily_loss_pct = float(os.environ.get('RISK_DAILY_LOSS_LIMIT_PCT', '5'))
        max_dd_pct = float(os.environ.get('RISK_MAX_DRAWDOWN_PCT', '10'))

        peak_equity = self.vars.get('peak_equity', balance)
        starting_balance = self.vars.get('daily_starting_balance', balance)
        daily_pnl = balance - starting_balance

        results = self._safety_manager.run_all_checks(
            qty=qty,
            price=price,
            balance=balance,
            current_pnl=daily_pnl,
            peak_equity=peak_equity,
            current_equity=balance,
            starting_balance=starting_balance,
            max_position_pct=max_pos_pct,
            daily_loss_limit_pct=daily_loss_pct,
            max_drawdown_pct=max_dd_pct,
        )

        if not results['all_ok']:
            failed = [k for k, v in results.items() if k != 'all_ok' and not v]
            # emergency_stop is True when triggered, so check it separately
            if results['emergency_stop']:
                failed.append('emergency_stop')
            logger.warning(f"Safety check failed: {failed}")
            if self.hp.get('alerts_enabled', True):
                self._alerts_mixin.send_error_alert(
                    f"Safety check blocked trade: {failed}", context="safety"
                )
            return False

        return True

    def _filter_volatility(self) -> bool:
        """Reject trades in extreme volatility."""
        if self.candles is None or len(self.candles) < 20:
            return True

        atr = ta.atr(self.candles, self.hp['atr_period'])
        volatility = atr / self.price

        return volatility < MAX_ATR_VOLATILITY

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
        threshold = self.hp.get('min_grid_suitability', JESSE_MIN_GRID_SUITABILITY)
        return suitability >= threshold
