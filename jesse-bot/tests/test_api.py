"""
API / Serialization tests for GridManager — Sprint M3.

Tests GridManager as a service interface: create, get state, update,
serialize/deserialize. Tests GridConfig validation with invalid values.
No Jesse/Redis dependency.
"""

import pytest
import sys
import os

# Add grid_logic module directly
grid_logic_path = os.path.join(os.path.dirname(__file__), '..', 'strategies', 'AIGridStrategy')
sys.path.insert(0, grid_logic_path)

from grid_logic import GridManager, GridConfig, TrailingStopManager


# ==============================================================================
# GridManager as a service interface
# ==============================================================================


class TestGridManagerService:
    """Test GridManager as a service: create → get state → update → serialize."""

    def test_create_and_get_state(self):
        """Create grid and verify state is accessible."""
        gm = GridManager(GridConfig(grid_levels_count=5, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0)

        assert gm.center == 100000.0
        assert len(gm.levels) == 10
        assert gm.filled_count == 0
        assert gm.unfilled_count == 10
        assert gm.direction == 'both'

    def test_update_grid_state(self):
        """Fill levels and verify state updates correctly."""
        gm = GridManager(GridConfig(grid_levels_count=5, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0)

        gm.check_buy_signal(98500.0)
        assert gm.filled_count == 1
        assert gm.unfilled_count == 9
        assert 'buy_1' in gm.filled_levels

        gm.check_sell_signal(101500.0)
        assert gm.filled_count == 2
        assert gm.unfilled_count == 8

    def test_re_setup_grid(self):
        """Re-setup grid at new center after reset."""
        gm = GridManager(GridConfig(grid_levels_count=5, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0)
        gm.check_buy_signal(98000.0)

        gm.reset()
        gm.setup_grid(110000.0)

        assert gm.center == 110000.0
        assert gm.filled_count == 0
        buy_prices = [l['price'] for l in gm.buy_levels]
        assert all(p < 110000.0 for p in buy_prices)


# ==============================================================================
# GridConfig validation
# ==============================================================================


class TestGridConfigValidation:
    """Test GridConfig with edge-case and invalid values."""

    def test_zero_grid_levels_produces_no_levels(self):
        """Zero grid levels should produce empty grid."""
        gm = GridManager(GridConfig(grid_levels_count=0))
        gm.setup_grid(100000.0)
        assert len(gm.levels) == 0

    def test_negative_spacing_produces_inverted_grid(self):
        """Negative spacing creates levels in wrong direction (edge case)."""
        gm = GridManager(GridConfig(grid_levels_count=3, grid_spacing_pct=-1.0))
        gm.setup_grid(100000.0)
        # Sell levels would be below center with negative spacing
        sell = gm.sell_levels
        if sell:
            assert sell[0]['price'] < 100000.0

    def test_very_large_spacing(self):
        """Large spacing creates widely spaced levels."""
        gm = GridManager(GridConfig(grid_levels_count=3, grid_spacing_pct=10.0))
        gm.setup_grid(100000.0)
        sell = gm.sell_levels
        # First sell level should be at +10% = 110000
        assert abs(sell[0]['price'] - 110000.0) < 0.01

    def test_single_level_grid(self):
        """Grid with 1 level per side."""
        gm = GridManager(GridConfig(grid_levels_count=1, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0)
        assert len(gm.buy_levels) == 1
        assert len(gm.sell_levels) == 1

    def test_max_cap_lower_than_requested_levels(self):
        """max_total_levels < grid_levels_count × 2 should cap."""
        gm = GridManager(GridConfig(grid_levels_count=20, max_total_levels=10))
        gm.setup_grid(100000.0)
        assert len(gm.levels) == 10  # 5 per side


# ==============================================================================
# Serialization: to_dict / from_dict
# ==============================================================================


class TestGridManagerSerialization:
    """Test GridManager serialization to dict and back."""

    def test_to_dict_structure(self):
        """Verify to_dict produces expected keys."""
        gm = GridManager(GridConfig(grid_levels_count=3, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0)

        d = gm.to_dict()
        assert 'config' in d
        assert 'levels' in d
        assert 'center' in d
        assert 'direction' in d
        assert 'filled_levels' in d

    def test_to_dict_config_fields(self):
        """Config section has all fields."""
        gm = GridManager(GridConfig(grid_levels_count=5, grid_spacing_pct=2.0))
        gm.setup_grid(100000.0)

        cfg = gm.to_dict()['config']
        assert cfg['grid_levels_count'] == 5
        assert cfg['grid_spacing_pct'] == 2.0
        assert cfg['max_total_levels'] == 40
        assert cfg['trailing_activation_pct'] == 1.0

    def test_to_dict_preserves_filled_state(self):
        """Filled levels are serialized correctly."""
        gm = GridManager(GridConfig(grid_levels_count=3, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0)
        gm.check_buy_signal(98500.0)

        d = gm.to_dict()
        assert 'buy_1' in d['filled_levels']
        # Find the filled level in levels list
        filled = [l for l in d['levels'] if l['id'] == 'buy_1']
        assert len(filled) == 1
        assert filled[0]['filled'] is True

    def test_from_dict_roundtrip(self):
        """to_dict → from_dict produces equivalent GridManager."""
        gm = GridManager(GridConfig(grid_levels_count=5, grid_spacing_pct=1.5))
        gm.setup_grid(100000.0, direction='long_only')
        gm.check_buy_signal(98000.0)

        d = gm.to_dict()
        gm2 = GridManager.from_dict(d)

        assert gm2.center == gm.center
        assert gm2.direction == gm.direction
        assert gm2.filled_levels == gm.filled_levels
        assert len(gm2.levels) == len(gm.levels)
        assert gm2.config.grid_levels_count == gm.config.grid_levels_count
        assert gm2.config.grid_spacing_pct == gm.config.grid_spacing_pct

    def test_from_dict_with_empty_grid(self):
        """Deserialize empty grid state."""
        gm = GridManager()
        d = gm.to_dict()
        gm2 = GridManager.from_dict(d)

        assert gm2.center is None
        assert gm2.levels == []
        assert gm2.filled_levels == set()

    def test_roundtrip_preserves_buy_sell_counts(self):
        """Level counts match after serialization roundtrip."""
        gm = GridManager(GridConfig(grid_levels_count=7, grid_spacing_pct=0.5))
        gm.setup_grid(50000.0, direction='both')
        gm.check_buy_signal(49500.0)
        gm.check_sell_signal(50300.0)

        d = gm.to_dict()
        gm2 = GridManager.from_dict(d)

        assert len(gm2.buy_levels) == len(gm.buy_levels)
        assert len(gm2.sell_levels) == len(gm.sell_levels)
        assert gm2.filled_count == gm.filled_count

    def test_from_dict_can_continue_operations(self):
        """Deserialized GridManager can still process signals."""
        gm = GridManager(GridConfig(grid_levels_count=5, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0)
        gm.check_buy_signal(98500.0)  # Fill buy_1

        d = gm.to_dict()
        gm2 = GridManager.from_dict(d)

        # buy_1 already filled, shouldn't retrigger
        assert gm2.check_buy_signal(98800.0) is False
        # but buy_2 at 98000 should trigger
        assert gm2.check_buy_signal(97500.0) is True
        assert gm2.filled_count == 2

    def test_serialization_to_json_compatible(self):
        """to_dict output is JSON-serializable."""
        import json
        gm = GridManager(GridConfig(grid_levels_count=3, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0)
        gm.check_buy_signal(98500.0)

        d = gm.to_dict()
        json_str = json.dumps(d)
        d2 = json.loads(json_str)

        gm2 = GridManager.from_dict(d2)
        assert gm2.center == gm.center
        assert gm2.filled_count == gm.filled_count

    def test_from_dict_handles_missing_config(self):
        """from_dict with empty config uses defaults."""
        gm = GridManager.from_dict({
            'config': {},
            'levels': [],
            'center': None,
            'direction': 'both',
            'filled_levels': [],
        })
        assert gm.config.grid_levels_count == 10
        assert gm.config.grid_spacing_pct == 1.5
