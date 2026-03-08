"""
Integration tests for AIGridStrategy — Sprint M3.

Tests the full grid lifecycle, AI mixin with mocked LLM responses,
AI fallback, and error handling. No Jesse/Redis dependency.
"""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock, AsyncMock

# Add grid_logic module directly
grid_logic_path = os.path.join(os.path.dirname(__file__), '..', 'strategies', 'AIGridStrategy')
sys.path.insert(0, grid_logic_path)

from grid_logic import GridManager, GridConfig, TrailingStopManager, calculate_tp, calculate_sl, detect_trend
from ai_fallback import AIFallback


# ==============================================================================
# Integration: Full grid lifecycle
# ==============================================================================


class TestGridLifecycle:
    """Test complete grid lifecycle: setup → signals → trailing → close → reset."""

    def test_full_long_lifecycle(self, grid_manager_with_levels):
        """Setup → buy signal → trailing stop → close → reset."""
        gm = grid_manager_with_levels

        # 1. Grid is set up with levels
        assert len(gm.levels) == 10
        assert gm.filled_count == 0

        # 2. Price drops → buy signal
        assert gm.check_buy_signal(98500.0) is True
        assert gm.filled_count == 1

        # 3. Calculate TP/SL for the position
        entry_price = gm.get_crossed_buy_level_price()
        assert entry_price is not None
        tp = calculate_tp(entry_price, 'long', atr=500.0, tp_mult=2.0)
        sl = calculate_sl(entry_price, 'long', atr=500.0, sl_mult=1.5)
        assert tp > entry_price
        assert sl < entry_price

        # 4. Trailing stop activates as price rises
        tsm = TrailingStopManager(activation_pct=1.0, distance_pct=0.5)
        tsm.start(entry_price, 'long')
        # Price rises 2% above entry
        new_stop = tsm.update(entry_price * 1.02)
        assert new_stop is not None
        assert tsm.activated is True

        # 5. Price rises more → stop tightens
        stop2 = tsm.update(entry_price * 1.03)
        assert stop2 is not None
        assert stop2 > new_stop

        # 6. Reset grid (simulates position close)
        gm.reset()
        assert gm.levels == []
        assert gm.filled_count == 0
        tsm.reset()
        assert tsm.activated is False

    def test_full_short_lifecycle(self, grid_manager_with_levels):
        """Setup → sell signal → trailing stop → close → reset."""
        gm = grid_manager_with_levels

        # Sell signal
        assert gm.check_sell_signal(101500.0) is True
        assert gm.filled_count == 1

        entry_price = gm.get_crossed_sell_level_price()
        assert entry_price is not None
        tp = calculate_tp(entry_price, 'short', atr=500.0, tp_mult=2.0)
        sl = calculate_sl(entry_price, 'short', atr=500.0, sl_mult=1.5)
        assert tp < entry_price
        assert sl > entry_price

        # Trailing stop for short
        tsm = TrailingStopManager(activation_pct=1.0, distance_pct=0.5)
        tsm.start(entry_price, 'short')
        new_stop = tsm.update(entry_price * 0.98)
        assert new_stop is not None
        assert tsm.activated is True

        # Reset
        gm.reset()
        tsm.reset()
        assert gm.levels == []
        assert tsm.activated is False

    def test_multiple_signals_sequential(self, grid_manager_with_levels):
        """Multiple buy signals at progressively lower prices."""
        gm = grid_manager_with_levels

        # First buy at 99000 level
        assert gm.check_buy_signal(98500.0) is True
        assert gm.filled_count == 1

        # Second buy at 98000 level
        assert gm.check_buy_signal(97500.0) is True
        assert gm.filled_count == 2

        # Third buy at 97000 level
        assert gm.check_buy_signal(96500.0) is True
        assert gm.filled_count == 3

    def test_grid_with_tp_sl_and_trailing(self):
        """Full integration of grid + TP/SL + trailing stop."""
        gm = GridManager(GridConfig(grid_levels_count=3, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0)

        # Buy signal
        gm.check_buy_signal(98500.0)
        entry = gm.get_crossed_buy_level_price()

        # TP/SL
        atr = 500.0
        tp = calculate_tp(entry, 'long', atr, 2.0)
        sl = calculate_sl(entry, 'long', atr, 1.5)

        # Trailing stop
        tsm = TrailingStopManager(activation_pct=1.0, distance_pct=0.5)
        tsm.start(entry, 'long')

        # Price moves up toward TP
        prices = [entry * 1.005, entry * 1.01, entry * 1.015, entry * 1.02]
        stops = []
        for p in prices:
            result = tsm.update(p)
            if result is not None:
                stops.append(result)

        # Trailing stop should have activated and tightened
        assert tsm.activated is True
        assert len(stops) > 0
        # Stops should be monotonically increasing for long
        for i in range(1, len(stops)):
            assert stops[i] >= stops[i - 1]


# ==============================================================================
# Integration: AI Fallback (rule-based)
# ==============================================================================


class TestAIFallbackIntegration:
    """Test AI fallback produces valid results in various market conditions."""

    def test_fallback_analyze_neutral_market(self):
        fb = AIFallback()
        result = fb.analyze_market([], {
            'rsi': 50.0, 'atr': 500.0, 'sma_fast': 100000.0,
            'sma_slow': 100000.0, 'close': 100000.0,
        })
        assert result['trend'] == 'neutral'
        assert result['recommendation'] in ('TRADE', 'WAIT')
        assert 0 <= result['confidence'] <= 1.0
        assert 'reasoning' in result

    def test_fallback_analyze_bullish_market(self):
        fb = AIFallback()
        result = fb.analyze_market([], {
            'rsi': 60.0, 'atr': 500.0, 'sma_fast': 105000.0,
            'sma_slow': 100000.0, 'close': 105000.0,
        })
        assert result['trend'] == 'uptrend'
        assert result['grid_params']['direction'] == 'long_only'

    def test_fallback_analyze_bearish_market(self):
        fb = AIFallback()
        result = fb.analyze_market([], {
            'rsi': 40.0, 'atr': 500.0, 'sma_fast': 95000.0,
            'sma_slow': 100000.0, 'close': 95000.0,
        })
        assert result['trend'] == 'downtrend'
        assert result['grid_params']['direction'] == 'short_only'

    def test_fallback_analyze_extreme_rsi_high(self):
        fb = AIFallback()
        result = fb.analyze_market([], {
            'rsi': 85.0, 'atr': 500.0, 'sma_fast': 100000.0,
            'sma_slow': 100000.0, 'close': 100000.0,
        })
        assert result['recommendation'] == 'WAIT'

    def test_fallback_analyze_extreme_rsi_low(self):
        fb = AIFallback()
        result = fb.analyze_market([], {
            'rsi': 15.0, 'atr': 500.0, 'sma_fast': 100000.0,
            'sma_slow': 100000.0, 'close': 100000.0,
        })
        assert result['recommendation'] == 'WAIT'

    def test_fallback_analyze_high_volatility(self):
        fb = AIFallback()
        result = fb.analyze_market([], {
            'rsi': 50.0, 'atr': 10000.0, 'sma_fast': 100000.0,
            'sma_slow': 100000.0, 'close': 100000.0,
        })
        # 10% ATR → very volatile → low confidence
        assert result['confidence'] < 0.5

    def test_fallback_review_position_continue(self):
        fb = AIFallback()
        result = fb.review_position(
            {'pnl_pct': 1.0, 'side': 'long'},
            {'rsi': 50.0, 'trend': 'uptrend'},
        )
        assert result == 'CONTINUE'

    def test_fallback_review_position_stop_on_large_loss(self):
        fb = AIFallback()
        result = fb.review_position(
            {'pnl_pct': -6.0, 'side': 'long'},
            {'rsi': 50.0, 'trend': 'downtrend'},
        )
        assert result == 'STOP'

    def test_fallback_review_position_adjust_on_rsi_extreme(self):
        fb = AIFallback()
        result = fb.review_position(
            {'pnl_pct': 1.0, 'side': 'long'},
            {'rsi': 90.0, 'trend': 'neutral'},
        )
        assert result == 'ADJUST'

    def test_fallback_review_position_pause_on_trend_reversal(self):
        fb = AIFallback()
        result = fb.review_position(
            {'pnl_pct': -0.5, 'side': 'long'},
            {'rsi': 50.0, 'trend': 'downtrend'},
        )
        assert result == 'PAUSE'

    def test_fallback_optimize_grid_uptrend(self, mock_ai_response_bullish):
        fb = AIFallback()
        result = fb.optimize_grid(
            {'spacing_pct': 1.5, 'levels_count': 10, 'direction': 'both'},
            mock_ai_response_bullish,
        )
        assert result['direction'] == 'long_only'
        assert result['spacing_pct'] > 0
        assert result['levels_count'] > 0

    def test_fallback_optimize_grid_low_confidence(self):
        fb = AIFallback()
        result = fb.optimize_grid(
            {'spacing_pct': 1.5, 'levels_count': 10, 'direction': 'both'},
            {'trend': 'neutral', 'confidence': 0.2},
        )
        # Low confidence → wider spacing, fewer levels
        assert result['spacing_pct'] > 1.5
        assert result['levels_count'] < 10

    def test_fallback_optimize_grid_high_confidence(self):
        fb = AIFallback()
        result = fb.optimize_grid(
            {'spacing_pct': 1.5, 'levels_count': 10, 'direction': 'both'},
            {'trend': 'neutral', 'confidence': 0.9},
        )
        # High confidence → tighter spacing, more levels
        assert result['spacing_pct'] < 1.5
        assert result['levels_count'] > 10


# ==============================================================================
# Integration: AI Mixin with mocked responses
# ==============================================================================


class TestAIMixinMocked:
    """Test AIMixin behavior with mocked LLM/TradingAgent."""

    def test_mixin_uses_fallback_when_no_shared_ai(self):
        """When shared/ai import fails, mixin should use fallback."""
        from ai_mixin import AIMixin

        # Patch _HAS_SHARED_AI to False
        with patch('ai_mixin._HAS_SHARED_AI', False):
            mixin = AIMixin()
            assert not mixin.ai_available

            result = mixin.ai_analyze_market([], {
                'rsi': 50.0, 'atr': 500.0, 'sma_fast': 100000.0,
                'sma_slow': 100000.0, 'close': 100000.0,
            })
            assert 'recommendation' in result
            assert 'confidence' in result

    def test_mixin_review_uses_fallback(self):
        """Position review falls back when AI unavailable."""
        from ai_mixin import AIMixin

        with patch('ai_mixin._HAS_SHARED_AI', False):
            mixin = AIMixin()
            result = mixin.ai_review_position(
                {'pnl_pct': -6.0, 'side': 'long'},
                {'rsi': 50.0, 'trend': 'downtrend'},
            )
            assert result == 'STOP'

    def test_mixin_optimize_uses_fallback(self):
        """Grid optimization falls back when AI unavailable."""
        from ai_mixin import AIMixin

        with patch('ai_mixin._HAS_SHARED_AI', False):
            mixin = AIMixin()
            result = mixin.ai_optimize_grid(
                {'spacing_pct': 1.5, 'levels_count': 10, 'direction': 'both'},
                {'trend': 'uptrend', 'confidence': 0.8},
            )
            assert 'spacing_pct' in result
            assert 'levels_count' in result
            assert result['direction'] == 'long_only'

    def test_ai_disabled_skips_all_calls(self):
        """When ai_enabled=False, mixin has no AI agent → uses fallback."""
        from ai_mixin import AIMixin

        with patch('ai_mixin._HAS_SHARED_AI', False):
            mixin = AIMixin()
            # All three methods should return valid fallback results
            analysis = mixin.ai_analyze_market([], {
                'rsi': 50.0, 'atr': 500.0, 'close': 100000.0,
                'sma_fast': 100000.0, 'sma_slow': 100000.0,
            })
            review = mixin.ai_review_position(
                {'pnl_pct': 0.0, 'side': 'long'},
                {'rsi': 50.0, 'trend': 'neutral'},
            )
            optimize = mixin.ai_optimize_grid(
                {'spacing_pct': 1.5, 'levels_count': 10, 'direction': 'both'},
                analysis,
            )
            assert analysis['recommendation'] in ('TRADE', 'WAIT')
            assert review in ('CONTINUE', 'PAUSE', 'ADJUST', 'STOP')
            assert optimize['levels_count'] > 0

    def test_mixin_handles_ai_timeout_gracefully(self):
        """Timeout on AI call → falls back, doesn't crash."""
        from ai_mixin import AIMixin

        mixin = AIMixin()
        # Force an exception in _run_ai_with_timeout
        mixin._ai_agent = MagicMock()
        mixin._ai_agent.is_available = True
        with patch.object(mixin, '_run_ai_with_timeout', side_effect=TimeoutError("timeout")):
            result = mixin.ai_analyze_market([], {
                'rsi': 50.0, 'atr': 500.0, 'close': 100000.0,
                'sma_fast': 100000.0, 'sma_slow': 100000.0,
            })
            # Should fall back gracefully
            assert 'recommendation' in result

    def test_mixin_handles_ai_error_gracefully(self):
        """Generic error on AI call → falls back, doesn't crash."""
        from ai_mixin import AIMixin

        mixin = AIMixin()
        mixin._ai_agent = MagicMock()
        mixin._ai_agent.is_available = True
        with patch.object(mixin, '_run_ai_with_timeout', side_effect=RuntimeError("LLM error")):
            result = mixin.ai_review_position(
                {'pnl_pct': 1.0, 'side': 'long'},
                {'rsi': 50.0, 'trend': 'neutral'},
            )
            assert result in ('CONTINUE', 'PAUSE', 'ADJUST', 'STOP')


# ==============================================================================
# Integration: Bidirectional grid with trend changes
# ==============================================================================


class TestBidirectionalTrendChanges:
    """Test grid behavior when trend changes direction."""

    def test_long_only_to_both(self):
        """Trend change: long_only → both should allow sell signals after re-setup."""
        gm = GridManager(GridConfig(grid_levels_count=5, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0, direction='long_only')
        assert len(gm.sell_levels) == 0

        # Trend changes to neutral → re-setup as 'both'
        gm.reset()
        gm.setup_grid(100000.0, direction='both')
        assert len(gm.sell_levels) == 5
        assert len(gm.buy_levels) == 5

        # Now sell signals work
        assert gm.check_sell_signal(101500.0) is True

    def test_both_to_short_only(self):
        """Trend change: both → short_only removes buy levels."""
        gm = GridManager(GridConfig(grid_levels_count=5, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0, direction='both')

        # Trend changes to downtrend
        gm.reset()
        gm.setup_grid(100000.0, direction='short_only')
        assert len(gm.buy_levels) == 0
        assert len(gm.sell_levels) == 5
        assert gm.check_buy_signal(90000.0) is False

    def test_short_only_to_long_only(self):
        """Full direction reversal."""
        gm = GridManager(GridConfig(grid_levels_count=5, grid_spacing_pct=1.0))
        gm.setup_grid(100000.0, direction='short_only')
        assert gm.check_sell_signal(101500.0) is True

        gm.reset()
        gm.setup_grid(100000.0, direction='long_only')
        assert len(gm.sell_levels) == 0
        assert gm.check_buy_signal(98500.0) is True

    def test_trend_detection_drives_direction(self):
        """detect_trend() output correctly maps to grid direction."""
        # Uptrend → long_only
        prices_up = list(range(1, 101))
        assert detect_trend(prices_up) == 'uptrend'

        # Downtrend → short_only
        prices_down = list(range(100, 0, -1))
        assert detect_trend(prices_down) == 'downtrend'

        # Flat → neutral (both)
        prices_flat = [100.0] * 100
        assert detect_trend(prices_flat) == 'neutral'
