"""
Tests for AIGridStrategy grid logic — Sprint M1 + M2 validation.

Tests use GridManager (pure Python) to avoid Jesse/Redis dependency.
Jesse integration is validated via backtest in Docker.
"""

import pytest
import sys
import os

# Add grid_logic module directly (avoid __init__.py which imports Jesse/Redis)
grid_logic_path = os.path.join(os.path.dirname(__file__), '..', 'strategies', 'AIGridStrategy')
sys.path.insert(0, grid_logic_path)

from grid_logic import (
    GridManager, GridConfig,
    TrailingStopManager,
    calculate_tp, calculate_sl, detect_trend,
)


# ==============================================================================
# Sprint M1 — Original 28 tests (regression)
# ==============================================================================


class TestGridConfig:
    """Test GridConfig defaults and validation."""

    def test_default_config(self):
        config = GridConfig()
        assert config.grid_levels_count == 10
        assert config.grid_spacing_pct == 1.5
        assert config.amount_pct == 5.0
        assert config.atr_period == 14
        assert config.tp_atr_mult == 2.0
        assert config.sl_atr_mult == 1.5

    def test_custom_config(self):
        config = GridConfig(grid_levels_count=5, grid_spacing_pct=2.0)
        assert config.grid_levels_count == 5
        assert config.grid_spacing_pct == 2.0


class TestGridSetup:
    """Test grid initialization."""

    def test_setup_creates_correct_level_count(self):
        gm = GridManager(GridConfig(grid_levels_count=5))
        gm.setup_grid(100000.0)
        assert len(gm.levels) == 10  # 5 buy + 5 sell

    def test_setup_creates_buy_and_sell_levels(self):
        gm = GridManager(GridConfig(grid_levels_count=5))
        gm.setup_grid(100000.0)
        assert len(gm.buy_levels) == 5
        assert len(gm.sell_levels) == 5

    def test_sell_levels_above_center(self):
        gm = GridManager(GridConfig(grid_levels_count=3, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0)
        for level in gm.sell_levels:
            assert level['price'] > 100000.0

    def test_buy_levels_below_center(self):
        gm = GridManager(GridConfig(grid_levels_count=3, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0)
        for level in gm.buy_levels:
            assert level['price'] < 100000.0

    def test_level_spacing_correct(self):
        gm = GridManager(GridConfig(grid_levels_count=3, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0)

        sell = gm.sell_levels
        assert abs(sell[0]['price'] - 101000.0) < 0.01  # +1%
        assert abs(sell[1]['price'] - 102000.0) < 0.01  # +2%
        assert abs(sell[2]['price'] - 103000.0) < 0.01  # +3%

        buy = gm.buy_levels
        assert abs(buy[0]['price'] - 99000.0) < 0.01  # -1%
        assert abs(buy[1]['price'] - 98000.0) < 0.01  # -2%
        assert abs(buy[2]['price'] - 97000.0) < 0.01  # -3%

    def test_center_price_stored(self):
        gm = GridManager()
        gm.setup_grid(50000.0)
        assert gm.center == 50000.0

    def test_all_levels_initially_unfilled(self):
        gm = GridManager(GridConfig(grid_levels_count=5))
        gm.setup_grid(100000.0)
        assert all(not l['filled'] for l in gm.levels)
        assert gm.filled_count == 0
        assert gm.unfilled_count == 10

    def test_levels_have_unique_ids(self):
        gm = GridManager(GridConfig(grid_levels_count=5))
        gm.setup_grid(100000.0)
        ids = [l['id'] for l in gm.levels]
        assert len(ids) == len(set(ids))


class TestBuySignals:
    """Test buy signal detection."""

    def test_buy_signal_triggers_when_price_below_level(self):
        gm = GridManager(GridConfig(grid_levels_count=5, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0)
        # Price drops to 98500 (below first buy level at 99000)
        assert gm.check_buy_signal(98500.0) is True

    def test_buy_signal_triggers_at_exact_level(self):
        gm = GridManager(GridConfig(grid_levels_count=5, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0)
        # Price exactly at buy level (99000)
        assert gm.check_buy_signal(99000.0) is True

    def test_no_buy_signal_when_price_above_all_levels(self):
        gm = GridManager(GridConfig(grid_levels_count=5, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0)
        assert gm.check_buy_signal(99500.0) is False

    def test_no_buy_signal_on_empty_grid(self):
        gm = GridManager()
        assert gm.check_buy_signal(50000.0) is False

    def test_filled_buy_level_not_retriggered(self):
        gm = GridManager(GridConfig(grid_levels_count=5, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0)

        # First trigger at 98500
        assert gm.check_buy_signal(98500.0) is True
        assert 'buy_1' in gm.filled_levels

        # Same level should not trigger again at 98800
        # (but buy_2 at 98000 won't trigger at 98800 either)
        gm_levels_before = gm.filled_count
        result = gm.check_buy_signal(98800.0)
        # buy_1 is filled, buy_2 is at 98000 (not crossed at 98800)
        assert result is False

    def test_multiple_buy_levels_trigger_sequentially(self):
        gm = GridManager(GridConfig(grid_levels_count=5, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0)

        # First drop
        assert gm.check_buy_signal(98500.0) is True
        assert gm.filled_count == 1

        # Second drop
        assert gm.check_buy_signal(97500.0) is True
        assert gm.filled_count == 2


class TestSellSignals:
    """Test sell signal detection."""

    def test_sell_signal_triggers_when_price_above_level(self):
        gm = GridManager(GridConfig(grid_levels_count=5, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0)
        assert gm.check_sell_signal(101500.0) is True

    def test_sell_signal_triggers_at_exact_level(self):
        gm = GridManager(GridConfig(grid_levels_count=5, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0)
        assert gm.check_sell_signal(101000.0) is True

    def test_no_sell_signal_when_price_below_all_levels(self):
        gm = GridManager(GridConfig(grid_levels_count=5, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0)
        assert gm.check_sell_signal(100500.0) is False

    def test_no_sell_signal_on_empty_grid(self):
        gm = GridManager()
        assert gm.check_sell_signal(150000.0) is False


class TestGridReset:
    """Test grid reset on position close."""

    def test_reset_clears_levels(self):
        gm = GridManager(GridConfig(grid_levels_count=5))
        gm.setup_grid(100000.0)
        gm.check_buy_signal(98000.0)

        gm.reset()
        assert gm.levels == []
        assert gm.center is None
        assert gm.filled_levels == set()

    def test_reset_allows_new_setup(self):
        gm = GridManager(GridConfig(grid_levels_count=5))
        gm.setup_grid(100000.0)
        gm.reset()
        gm.setup_grid(50000.0)
        assert gm.center == 50000.0
        assert len(gm.levels) == 10


class TestFilters:
    """Test pre-trade filters."""

    def test_max_levels_filter_passes_when_few_filled(self):
        gm = GridManager(GridConfig(grid_levels_count=5))
        gm.setup_grid(100000.0)
        gm.filled_levels = {'buy_1', 'sell_1'}
        assert gm.filter_max_levels() is True

    def test_max_levels_filter_blocks_when_many_filled(self):
        gm = GridManager(GridConfig(grid_levels_count=5))
        gm.setup_grid(100000.0)
        gm.filled_levels = {
            'buy_1', 'buy_2', 'buy_3', 'buy_4',
            'sell_1', 'sell_2', 'sell_3',
        }
        assert gm.filter_max_levels() is False

    def test_max_levels_filter_custom_threshold(self):
        gm = GridManager(GridConfig(grid_levels_count=5))
        gm.setup_grid(100000.0)
        gm.filled_levels = {'buy_1', 'buy_2', 'buy_3'}
        # 3 filled out of 10 total, 50% threshold = 5
        assert gm.filter_max_levels(max_fill_pct=0.5) is True
        # 3 filled out of 10, 25% threshold = 2.5
        assert gm.filter_max_levels(max_fill_pct=0.25) is False


class TestCrossedLevelPrices:
    """Test getting prices of crossed levels."""

    def test_get_crossed_buy_level_price(self):
        gm = GridManager(GridConfig(grid_levels_count=5, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0)
        gm.check_buy_signal(98500.0)
        price = gm.get_crossed_buy_level_price()
        assert price is not None
        assert abs(price - 99000.0) < 0.01

    def test_get_crossed_sell_level_price(self):
        gm = GridManager(GridConfig(grid_levels_count=5, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0)
        gm.check_sell_signal(101500.0)
        price = gm.get_crossed_sell_level_price()
        assert price is not None
        assert abs(price - 101000.0) < 0.01

    def test_no_crossed_level_returns_none(self):
        gm = GridManager(GridConfig(grid_levels_count=5))
        gm.setup_grid(100000.0)
        assert gm.get_crossed_buy_level_price() is None
        assert gm.get_crossed_sell_level_price() is None


# ==============================================================================
# Sprint M2 — New tests (22+ new tests)
# ==============================================================================


class TestGridConfigM2:
    """Test new GridConfig fields added in M2."""

    def test_default_config_has_m2_fields(self):
        config = GridConfig()
        assert config.max_total_levels == 40
        assert config.trailing_activation_pct == 1.0
        assert config.trailing_distance_pct == 0.5
        assert config.trend_sma_fast == 10
        assert config.trend_sma_slow == 50

    def test_custom_m2_config(self):
        config = GridConfig(
            max_total_levels=20,
            trailing_activation_pct=2.0,
            trailing_distance_pct=1.0,
            trend_sma_fast=15,
            trend_sma_slow=60,
        )
        assert config.max_total_levels == 20
        assert config.trailing_activation_pct == 2.0
        assert config.trailing_distance_pct == 1.0
        assert config.trend_sma_fast == 15
        assert config.trend_sma_slow == 60


class TestBidirectionalGrid:
    """Test bidirectional grid support."""

    def test_long_only_creates_only_buy_levels(self):
        gm = GridManager(GridConfig(grid_levels_count=5))
        gm.setup_grid(100000.0, direction='long_only')
        assert len(gm.buy_levels) == 5
        assert len(gm.sell_levels) == 0
        assert gm.direction == 'long_only'

    def test_short_only_creates_only_sell_levels(self):
        gm = GridManager(GridConfig(grid_levels_count=5))
        gm.setup_grid(100000.0, direction='short_only')
        assert len(gm.buy_levels) == 0
        assert len(gm.sell_levels) == 5
        assert gm.direction == 'short_only'

    def test_both_creates_buy_and_sell_levels(self):
        gm = GridManager(GridConfig(grid_levels_count=5))
        gm.setup_grid(100000.0, direction='both')
        assert len(gm.buy_levels) == 5
        assert len(gm.sell_levels) == 5
        assert gm.direction == 'both'

    def test_default_direction_is_both(self):
        gm = GridManager(GridConfig(grid_levels_count=5))
        gm.setup_grid(100000.0)
        assert gm.direction == 'both'
        assert len(gm.buy_levels) == 5
        assert len(gm.sell_levels) == 5

    def test_long_only_no_sell_signals(self):
        gm = GridManager(GridConfig(grid_levels_count=5, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0, direction='long_only')
        # No sell levels exist, so sell signal should never trigger
        assert gm.check_sell_signal(110000.0) is False

    def test_short_only_no_buy_signals(self):
        gm = GridManager(GridConfig(grid_levels_count=5, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0, direction='short_only')
        # No buy levels exist, so buy signal should never trigger
        assert gm.check_buy_signal(90000.0) is False

    def test_direction_via_setup_overrides_default(self):
        gm = GridManager(GridConfig(grid_levels_count=5))
        gm.direction = 'both'
        gm.setup_grid(100000.0, direction='long_only')
        assert gm.direction == 'long_only'
        assert len(gm.sell_levels) == 0

    def test_direction_preserved_when_none(self):
        gm = GridManager(GridConfig(grid_levels_count=5))
        gm.direction = 'short_only'
        gm.setup_grid(100000.0)  # direction=None, uses self.direction
        assert gm.direction == 'short_only'
        assert len(gm.buy_levels) == 0
        assert len(gm.sell_levels) == 5


class TestMaxGridLevelsCap:
    """Test max grid levels cap prevents unbounded growth."""

    def test_levels_capped_at_max_total(self):
        # grid_levels_count=30 but max_total_levels=20 → 10 per side
        gm = GridManager(GridConfig(grid_levels_count=30, max_total_levels=20))
        gm.setup_grid(100000.0)
        assert len(gm.buy_levels) == 10
        assert len(gm.sell_levels) == 10
        assert len(gm.levels) == 20

    def test_levels_not_capped_when_under_max(self):
        gm = GridManager(GridConfig(grid_levels_count=5, max_total_levels=40))
        gm.setup_grid(100000.0)
        assert len(gm.levels) == 10  # 5+5, well under 40

    def test_max_cap_with_long_only(self):
        gm = GridManager(GridConfig(grid_levels_count=30, max_total_levels=20))
        gm.setup_grid(100000.0, direction='long_only')
        # max_per_side = 10, so only 10 buy levels
        assert len(gm.buy_levels) == 10
        assert len(gm.sell_levels) == 0

    def test_small_max_total_levels(self):
        gm = GridManager(GridConfig(grid_levels_count=10, max_total_levels=10))
        gm.setup_grid(100000.0)
        # max_per_side = 5, so 5 buy + 5 sell = 10
        assert len(gm.levels) == 10
        assert len(gm.buy_levels) == 5
        assert len(gm.sell_levels) == 5


class TestCalculateTP:
    """Test take-profit calculation."""

    def test_tp_long(self):
        tp = calculate_tp(100000.0, 'long', atr=500.0, tp_mult=2.0)
        assert abs(tp - 101000.0) < 0.01

    def test_tp_short(self):
        tp = calculate_tp(100000.0, 'short', atr=500.0, tp_mult=2.0)
        assert abs(tp - 99000.0) < 0.01

    def test_tp_long_large_atr(self):
        tp = calculate_tp(50000.0, 'long', atr=2000.0, tp_mult=3.0)
        assert abs(tp - 56000.0) < 0.01

    def test_tp_short_small_atr(self):
        tp = calculate_tp(50000.0, 'short', atr=100.0, tp_mult=1.5)
        assert abs(tp - 49850.0) < 0.01


class TestCalculateSL:
    """Test stop-loss calculation."""

    def test_sl_long(self):
        sl = calculate_sl(100000.0, 'long', atr=500.0, sl_mult=1.5)
        assert abs(sl - 99250.0) < 0.01

    def test_sl_short(self):
        sl = calculate_sl(100000.0, 'short', atr=500.0, sl_mult=1.5)
        assert abs(sl - 100750.0) < 0.01

    def test_sl_long_large_atr(self):
        sl = calculate_sl(50000.0, 'long', atr=2000.0, sl_mult=2.0)
        assert abs(sl - 46000.0) < 0.01

    def test_sl_short_small_atr(self):
        sl = calculate_sl(50000.0, 'short', atr=100.0, sl_mult=1.0)
        assert abs(sl - 50100.0) < 0.01


class TestTrendDetection:
    """Test SMA crossover trend detection."""

    def test_uptrend_detected(self):
        # Rising prices → fast SMA > slow SMA
        prices = list(range(1, 101))  # 1, 2, ..., 100
        trend = detect_trend(prices, fast_period=10, slow_period=50)
        assert trend == 'uptrend'

    def test_downtrend_detected(self):
        # Falling prices → fast SMA < slow SMA
        prices = list(range(100, 0, -1))  # 100, 99, ..., 1
        trend = detect_trend(prices, fast_period=10, slow_period=50)
        assert trend == 'downtrend'

    def test_neutral_when_insufficient_data(self):
        prices = [100.0] * 10
        trend = detect_trend(prices, fast_period=10, slow_period=50)
        assert trend == 'neutral'

    def test_neutral_when_sma_equal(self):
        # Flat prices → fast SMA == slow SMA
        prices = [100.0] * 100
        trend = detect_trend(prices, fast_period=10, slow_period=50)
        assert trend == 'neutral'

    def test_custom_periods(self):
        prices = list(range(1, 201))
        trend = detect_trend(prices, fast_period=20, slow_period=100)
        assert trend == 'uptrend'


class TestTrailingStopManagerLong:
    """Test trailing stop for long positions."""

    def test_not_activated_below_threshold(self):
        tsm = TrailingStopManager(activation_pct=2.0, distance_pct=1.0)
        tsm.start(100000.0, 'long')
        # Price up 1% (below 2% activation)
        result = tsm.update(101000.0)
        assert result is None
        assert tsm.activated is False

    def test_activates_at_threshold(self):
        tsm = TrailingStopManager(activation_pct=2.0, distance_pct=1.0)
        tsm.start(100000.0, 'long')
        # Price up 2% (at activation threshold)
        result = tsm.update(102000.0)
        assert result is not None
        assert tsm.activated is True

    def test_stop_tightens_as_price_rises(self):
        tsm = TrailingStopManager(activation_pct=1.0, distance_pct=1.0)
        tsm.start(100000.0, 'long')

        # Price up 2% → activated
        stop1 = tsm.update(102000.0)
        assert stop1 is not None

        # Price up 3% → stop should tighten
        stop2 = tsm.update(103000.0)
        assert stop2 is not None
        assert stop2 > stop1

    def test_stop_never_loosens(self):
        tsm = TrailingStopManager(activation_pct=1.0, distance_pct=1.0)
        tsm.start(100000.0, 'long')

        # Activate and set stop
        tsm.update(103000.0)
        old_stop = tsm.current_stop

        # Price drops → stop should NOT move down
        result = tsm.update(101500.0)
        assert result is None
        assert tsm.current_stop == old_stop

    def test_stop_distance_correct(self):
        tsm = TrailingStopManager(activation_pct=1.0, distance_pct=2.0)
        tsm.start(100000.0, 'long')

        tsm.update(105000.0)
        # Stop should be 2% below peak (105000)
        expected_stop = 105000.0 * (1 - 2.0 / 100)
        assert abs(tsm.current_stop - expected_stop) < 0.01

    def test_no_update_without_start(self):
        tsm = TrailingStopManager()
        result = tsm.update(100000.0)
        assert result is None


class TestTrailingStopManagerShort:
    """Test trailing stop for short positions."""

    def test_short_activates_when_price_drops(self):
        tsm = TrailingStopManager(activation_pct=2.0, distance_pct=1.0)
        tsm.start(100000.0, 'short')
        # Price down 2% → activated
        result = tsm.update(98000.0)
        assert result is not None
        assert tsm.activated is True

    def test_short_not_activated_when_price_rises(self):
        tsm = TrailingStopManager(activation_pct=2.0, distance_pct=1.0)
        tsm.start(100000.0, 'short')
        # Price up → no profit for short
        result = tsm.update(101000.0)
        assert result is None
        assert tsm.activated is False

    def test_short_stop_tightens_as_price_drops(self):
        tsm = TrailingStopManager(activation_pct=1.0, distance_pct=1.0)
        tsm.start(100000.0, 'short')

        stop1 = tsm.update(98000.0)
        assert stop1 is not None

        stop2 = tsm.update(97000.0)
        assert stop2 is not None
        assert stop2 < stop1  # Tighter for short = lower

    def test_short_stop_never_loosens(self):
        tsm = TrailingStopManager(activation_pct=1.0, distance_pct=1.0)
        tsm.start(100000.0, 'short')

        tsm.update(97000.0)
        old_stop = tsm.current_stop

        # Price bounces up → stop should NOT move up
        result = tsm.update(98500.0)
        assert result is None
        assert tsm.current_stop == old_stop

    def test_short_stop_distance_correct(self):
        tsm = TrailingStopManager(activation_pct=1.0, distance_pct=2.0)
        tsm.start(100000.0, 'short')

        tsm.update(95000.0)
        # Stop should be 2% above peak low (95000)
        expected_stop = 95000.0 * (1 + 2.0 / 100)
        assert abs(tsm.current_stop - expected_stop) < 0.01


class TestTrailingStopReset:
    """Test trailing stop reset."""

    def test_reset_clears_state(self):
        tsm = TrailingStopManager(activation_pct=1.0, distance_pct=1.0)
        tsm.start(100000.0, 'long')
        tsm.update(105000.0)

        tsm.reset()
        assert tsm.entry_price is None
        assert tsm.peak_price is None
        assert tsm.current_stop is None
        assert tsm.activated is False

    def test_reset_allows_restart(self):
        tsm = TrailingStopManager(activation_pct=1.0, distance_pct=1.0)
        tsm.start(100000.0, 'long')
        tsm.update(105000.0)
        tsm.reset()

        # Start new position
        tsm.start(50000.0, 'short')
        assert tsm.entry_price == 50000.0
        assert tsm.activated is False
