"""Unit tests for Sprint 21: Take-Profit / Stop-Loss per grid level.

Tests:
- TPSLCalculator (fixed, ATR-based, risk-reward)
- TrailingStopManager
- BreakEvenManager
- GridLevel TP/SL integration (fill → TP/SL set → hit → close)
"""

import pytest
import time

from binance_bot.strategies.base import Signal, SignalType, GridLevel
from binance_bot.strategies.grid import GridStrategy, GridConfig
from shared.risk.tp_sl import TPSLCalculator
from shared.risk.trailing_stop import TrailingStopManager
from shared.risk.break_even import BreakEvenManager
from tests.conftest import make_ohlcv_df


class TestTPSLCalculatorFixed:
    """Tests for fixed percentage TP/SL."""

    def test_fixed_tp_sl_long(self):
        """Long TP above entry, SL below entry."""
        tp, sl = TPSLCalculator.fixed_percentage(50000.0, "long", tp_pct=2.0, sl_pct=1.0)
        assert tp == pytest.approx(51000.0)  # 50000 * 1.02
        assert sl == pytest.approx(49500.0)  # 50000 * 0.99

    def test_fixed_tp_sl_short(self):
        """Short TP below entry, SL above entry."""
        tp, sl = TPSLCalculator.fixed_percentage(50000.0, "short", tp_pct=2.0, sl_pct=1.0)
        assert tp == pytest.approx(49000.0)  # 50000 * 0.98
        assert sl == pytest.approx(50500.0)  # 50000 * 1.01

    def test_fixed_custom_pct(self):
        """Custom percentages should be respected."""
        tp, sl = TPSLCalculator.fixed_percentage(10000.0, "long", tp_pct=5.0, sl_pct=3.0)
        assert tp == pytest.approx(10500.0)  # 10000 * 1.05
        assert sl == pytest.approx(9700.0)   # 10000 * 0.97

    def test_fixed_zero_entry(self):
        """Zero entry price returns zero TP/SL."""
        tp, sl = TPSLCalculator.fixed_percentage(0.0, "long")
        assert tp == 0.0
        assert sl == 0.0


class TestTPSLCalculatorATR:
    """Tests for ATR-based TP/SL."""

    def test_atr_based_tp_sl(self):
        """ATR-based TP/SL uses ATR * multiplier as distance."""
        atr = 500.0
        tp, sl = TPSLCalculator.atr_based(50000.0, "long", atr, tp_multiplier=2.0, sl_multiplier=1.0)
        assert tp == pytest.approx(51000.0)  # 50000 + 500*2
        assert sl == pytest.approx(49500.0)  # 50000 - 500*1

    def test_atr_based_short(self):
        """ATR-based short: TP below, SL above."""
        atr = 500.0
        tp, sl = TPSLCalculator.atr_based(50000.0, "short", atr, tp_multiplier=2.0, sl_multiplier=1.0)
        assert tp == pytest.approx(49000.0)  # 50000 - 500*2
        assert sl == pytest.approx(50500.0)  # 50000 + 500*1

    def test_atr_based_custom_multipliers(self):
        """Custom ATR multipliers."""
        atr = 200.0
        tp, sl = TPSLCalculator.atr_based(10000.0, "long", atr, tp_multiplier=3.0, sl_multiplier=1.5)
        assert tp == pytest.approx(10600.0)  # 10000 + 200*3
        assert sl == pytest.approx(9700.0)   # 10000 - 200*1.5


class TestTPSLCalculatorRiskReward:
    """Tests for risk-reward ratio TP calculation."""

    def test_risk_reward_ratio(self):
        """TP from risk-reward ratio and SL distance."""
        tp = TPSLCalculator.risk_reward_ratio(50000.0, "long", 49500.0, rr_ratio=2.0)
        # Risk = 50000 - 49500 = 500, reward = 500*2 = 1000
        assert tp == pytest.approx(51000.0)

    def test_risk_reward_ratio_short(self):
        """Short RR: TP below entry."""
        tp = TPSLCalculator.risk_reward_ratio(50000.0, "short", 50500.0, rr_ratio=2.0)
        # Risk = 50500 - 50000 = 500, reward = 500*2 = 1000
        assert tp == pytest.approx(49000.0)

    def test_risk_reward_ratio_3_to_1(self):
        """3:1 risk-reward ratio."""
        tp = TPSLCalculator.risk_reward_ratio(100.0, "long", 95.0, rr_ratio=3.0)
        # Risk = 5, reward = 15
        assert tp == pytest.approx(115.0)


class TestTrailingStopUpdate:
    """Tests for trailing stop price tracking and updates."""

    def test_trailing_stop_update_long(self):
        """Long trailing: updates high, no trigger when price rising."""
        mgr = TrailingStopManager(trail_pct=1.0, activation_pct=0.5)
        level = GridLevel(
            price=50000.0, side=SignalType.BUY, amount=0.01,
            filled=True, fill_price=50000.0, trailing_high=50000.0,
        )
        # Price rises — no trigger
        assert mgr.update(level, 50500.0) is False
        assert level.trailing_high == 50500.0

    def test_trailing_stop_update_short(self):
        """Short trailing: updates low, no trigger when price falling."""
        mgr = TrailingStopManager(trail_pct=1.0, activation_pct=0.5)
        level = GridLevel(
            price=50000.0, side=SignalType.SELL, amount=-0.01,
            filled=True, fill_price=50000.0, trailing_low=50000.0,
        )
        # Price falls — no trigger
        assert mgr.update(level, 49500.0) is False
        assert level.trailing_low == 49500.0

    def test_trailing_stop_not_active_before_threshold(self):
        """Trailing stop should not activate before activation_pct profit."""
        mgr = TrailingStopManager(trail_pct=1.0, activation_pct=2.0)
        level = GridLevel(
            price=50000.0, side=SignalType.BUY, amount=0.01,
            filled=True, fill_price=50000.0, trailing_high=50000.0,
        )
        # Only 0.2% profit — below 2% activation threshold
        assert mgr.update(level, 50100.0) is False
        # Now 0.1% drop — should still not trigger since activation not met
        assert mgr.update(level, 50050.0) is False


class TestTrailingStopTrigger:
    """Tests for trailing stop trigger conditions."""

    def test_trailing_stop_trigger_long(self):
        """Long trailing stop triggers when price drops below trail price."""
        mgr = TrailingStopManager(trail_pct=1.0, activation_pct=0.5)
        level = GridLevel(
            price=50000.0, side=SignalType.BUY, amount=0.01,
            filled=True, fill_price=50000.0, trailing_high=50000.0,
        )
        # Push price up above activation threshold (0.5%)
        mgr.update(level, 50500.0)  # +1% from fill
        assert level.trailing_high == 50500.0

        # Now drop below trail: 50500 * (1 - 0.01) = 49995
        triggered = mgr.update(level, 49990.0)
        assert triggered is True

    def test_trailing_stop_trigger_short(self):
        """Short trailing stop triggers when price rises above trail price."""
        mgr = TrailingStopManager(trail_pct=1.0, activation_pct=0.5)
        level = GridLevel(
            price=50000.0, side=SignalType.SELL, amount=-0.01,
            filled=True, fill_price=50000.0, trailing_low=50000.0,
        )
        # Push price down past activation threshold
        mgr.update(level, 49500.0)  # -1% from fill
        assert level.trailing_low == 49500.0

        # Now rise above trail: 49500 * (1 + 0.01) = 49995
        triggered = mgr.update(level, 50000.0)
        assert triggered is True

    def test_trailing_stop_no_trigger_when_unfilled(self):
        """Unfilled level should never trigger trailing stop."""
        mgr = TrailingStopManager(trail_pct=1.0, activation_pct=0.5)
        level = GridLevel(price=50000.0, side=SignalType.BUY, amount=0.01, filled=False)
        assert mgr.update(level, 49000.0) is False


class TestBreakEvenActivation:
    """Tests for break-even stop activation."""

    def test_break_even_activation_long(self):
        """Break-even activates when long profit reaches threshold."""
        mgr = BreakEvenManager(activation_pct=1.0, offset_pct=0.1)
        level = GridLevel(
            price=50000.0, side=SignalType.BUY, amount=0.01,
            filled=True, fill_price=50000.0, stop_loss=49500.0,
        )
        # Price at +1.5% — should activate
        activated = mgr.check_and_activate(level, 50750.0)
        assert activated is True
        assert level.break_even_triggered is True
        # SL moved to fill_price * (1 + 0.1%) = 50050
        assert level.stop_loss == pytest.approx(50050.0)

    def test_break_even_activation_short(self):
        """Break-even activates when short profit reaches threshold."""
        mgr = BreakEvenManager(activation_pct=1.0, offset_pct=0.1)
        level = GridLevel(
            price=50000.0, side=SignalType.SELL, amount=-0.01,
            filled=True, fill_price=50000.0, stop_loss=50500.0,
        )
        # Price at -1.5% — should activate for short
        activated = mgr.check_and_activate(level, 49250.0)
        assert activated is True
        assert level.break_even_triggered is True
        # SL moved to fill_price * (1 - 0.1%) = 49950
        assert level.stop_loss == pytest.approx(49950.0)

    def test_break_even_not_activated_below_threshold(self):
        """Break-even should not activate before profit threshold."""
        mgr = BreakEvenManager(activation_pct=2.0, offset_pct=0.1)
        level = GridLevel(
            price=50000.0, side=SignalType.BUY, amount=0.01,
            filled=True, fill_price=50000.0, stop_loss=49500.0,
        )
        # Only +0.5% profit
        activated = mgr.check_and_activate(level, 50250.0)
        assert activated is False
        assert level.break_even_triggered is False
        assert level.stop_loss == 49500.0  # Unchanged

    def test_break_even_not_activated_twice(self):
        """Break-even should only activate once."""
        mgr = BreakEvenManager(activation_pct=1.0, offset_pct=0.1)
        level = GridLevel(
            price=50000.0, side=SignalType.BUY, amount=0.01,
            filled=True, fill_price=50000.0, stop_loss=49500.0,
        )
        mgr.check_and_activate(level, 50750.0)
        new_sl = level.stop_loss

        # Second call should return False
        activated = mgr.check_and_activate(level, 51000.0)
        assert activated is False
        assert level.stop_loss == new_sl  # Unchanged


class TestTPHitClosesLevel:
    """Tests for TP hitting and closing a grid level."""

    def test_tp_hit_closes_level(self):
        """When price hits TP, the level should be closed with positive PnL."""
        config = GridConfig(
            grid_levels=3, grid_spacing_pct=1.0, direction="long",
            tp_mode="fixed", sl_mode="fixed", tp_pct=2.0, sl_pct=1.0,
            trailing_enabled=False, break_even_enabled=False,
        )
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        strategy.setup_grid(50000.0)

        # Manually fill a level with TP/SL set
        level = strategy.levels[0]  # Lowest buy level
        level.filled = True
        level.fill_price = level.price
        level.fill_time = int(time.time() * 1000)
        level.trailing_high = level.price
        level.trailing_low = level.price
        strategy._set_tp_sl_for_level(level)

        # Simulate owning the position
        abs_amount = abs(level.amount)
        strategy.paper_holdings = abs_amount
        strategy.long_holdings = abs_amount

        # TP should be above fill
        assert level.take_profit > level.fill_price

        # Price reaches TP
        events = strategy.check_tp_sl(level.take_profit + 1)
        assert len(events) == 1
        assert events[0]["type"] == "take_profit"
        assert events[0]["pnl"] > 0


class TestSLHitClosesLevel:
    """Tests for SL hitting and closing a grid level."""

    def test_sl_hit_closes_level(self):
        """When price hits SL, the level should be closed with negative PnL."""
        config = GridConfig(
            grid_levels=3, grid_spacing_pct=1.0, direction="long",
            tp_mode="fixed", sl_mode="fixed", tp_pct=2.0, sl_pct=1.0,
            trailing_enabled=False, break_even_enabled=False,
        )
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        strategy.setup_grid(50000.0)

        # Manually fill a level
        level = strategy.levels[0]
        level.filled = True
        level.fill_price = level.price
        level.fill_time = int(time.time() * 1000)
        level.trailing_high = level.price
        level.trailing_low = level.price
        strategy._set_tp_sl_for_level(level)

        abs_amount = abs(level.amount)
        strategy.paper_holdings = abs_amount
        strategy.long_holdings = abs_amount

        # SL should be below fill
        assert level.stop_loss < level.fill_price

        # Price drops to SL
        events = strategy.check_tp_sl(level.stop_loss - 1)
        assert len(events) == 1
        assert events[0]["type"] == "stop_loss"
        assert events[0]["pnl"] < 0


class TestGridConfigTPSLDefaults:
    """Tests for Sprint 21 GridConfig defaults."""

    def test_default_tp_mode(self):
        config = GridConfig()
        assert config.tp_mode == "atr"

    def test_default_sl_mode(self):
        config = GridConfig()
        assert config.sl_mode == "atr"

    def test_default_trailing_enabled(self):
        config = GridConfig()
        assert config.trailing_enabled is True

    def test_default_break_even_enabled(self):
        config = GridConfig()
        assert config.break_even_enabled is True

    def test_custom_tp_sl_config(self):
        config = GridConfig(
            tp_mode="fixed", sl_mode="fixed",
            tp_pct=3.0, sl_pct=2.0,
            trailing_enabled=False,
            break_even_enabled=False,
        )
        assert config.tp_mode == "fixed"
        assert config.tp_pct == 3.0
        assert config.sl_pct == 2.0
        assert config.trailing_enabled is False


class TestGridStatusTPSL:
    """Tests for TP/SL info in grid status."""

    def test_status_includes_tp_sl_section(self):
        strategy = GridStrategy(symbol="BTC/USDT")
        strategy.setup_grid(50000.0)
        status = strategy.get_status()

        assert "tp_sl" in status
        assert "current_atr" in status["tp_sl"]
        assert "levels_with_tp" in status["tp_sl"]
        assert "levels_with_sl" in status["tp_sl"]
        assert "break_even_active" in status["tp_sl"]
        assert "closed_by_tp_sl" in status["tp_sl"]
        assert "total_tp_sl_pnl" in status["tp_sl"]

    def test_status_config_includes_tp_sl_fields(self):
        strategy = GridStrategy(symbol="BTC/USDT")
        strategy.setup_grid(50000.0)
        status = strategy.get_status()

        assert "tp_mode" in status["config"]
        assert "sl_mode" in status["config"]
        assert "trailing_enabled" in status["config"]
        assert "break_even_enabled" in status["config"]

    def test_status_paper_trading_includes_realized_pnl(self):
        strategy = GridStrategy(symbol="BTC/USDT")
        strategy.setup_grid(50000.0)
        status = strategy.get_status()

        assert "realized_pnl" in status["paper_trading"]
