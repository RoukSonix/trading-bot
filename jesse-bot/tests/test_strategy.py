"""
Tests for AIGridStrategy grid logic — Sprint M1 validation.

Tests use GridManager (pure Python) to avoid Jesse/Redis dependency.
Jesse integration is validated via backtest in Docker.
"""

import pytest
import sys
import os

# Add grid_logic module directly (avoid __init__.py which imports Jesse/Redis)
grid_logic_path = os.path.join(os.path.dirname(__file__), '..', 'strategies', 'AIGridStrategy')
sys.path.insert(0, grid_logic_path)

from grid_logic import GridManager, GridConfig


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
