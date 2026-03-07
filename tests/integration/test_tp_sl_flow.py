"""Integration tests for Sprint 21: TP/SL per grid level flow.

Tests end-to-end: grid setup → fill level → TP/SL set → price moves → TP/SL hit
→ level closed → PnL recorded → paper balance updated.
"""

import pytest
import time
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.core.database import Base, Trade, Position
from binance_bot.strategies.base import Signal, SignalType, GridLevel
from binance_bot.strategies.grid import GridStrategy, GridConfig
from tests.conftest import make_ohlcv_df


@pytest.fixture
def trade_db():
    """In-memory SQLite database for integration tests."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    yield Session
    Base.metadata.drop_all(engine)
    engine.dispose()


def _make_strategy_with_filled_level(
    direction: str = "long",
    tp_mode: str = "fixed",
    sl_mode: str = "fixed",
    tp_pct: float = 2.0,
    sl_pct: float = 1.0,
    trailing_enabled: bool = False,
    break_even_enabled: bool = False,
) -> tuple[GridStrategy, GridLevel]:
    """Helper: create strategy, fill a level, set TP/SL, return (strategy, level)."""
    config = GridConfig(
        grid_levels=3, grid_spacing_pct=1.0, amount_per_level=0.01,
        direction=direction,
        tp_mode=tp_mode, sl_mode=sl_mode,
        tp_pct=tp_pct, sl_pct=sl_pct,
        trailing_enabled=trailing_enabled,
        break_even_enabled=break_even_enabled,
        trailing_pct=1.0,
        break_even_pct=1.0,
    )
    strategy = GridStrategy(symbol="BTC/USDT", config=config)
    strategy.setup_grid(50000.0)

    # Find the first buy level (for long) or sell level (for short)
    if direction == "long":
        level = next(l for l in strategy.levels if l.side == SignalType.BUY and not l.filled)
    else:
        level = next(l for l in strategy.levels if l.side == SignalType.SELL and not l.filled)

    # Fill the level
    level.filled = True
    level.fill_price = level.price
    level.fill_time = int(time.time() * 1000)
    level.trailing_high = level.price
    level.trailing_low = level.price
    strategy._set_tp_sl_for_level(level)

    # Set paper holdings to match
    abs_amount = abs(level.amount)
    if direction == "long":
        strategy.paper_holdings = abs_amount
        strategy.long_holdings = abs_amount
        strategy.long_entry_price = level.price
    else:
        strategy.short_holdings = abs_amount
        strategy.short_entry_price = level.price

    return strategy, level


@pytest.mark.integration
class TestFullTradeWithTP:
    """End-to-end: fill → TP hit → close → PnL recorded."""

    def test_full_trade_with_tp(self):
        """Long level fills, price rises to TP, level closes with profit."""
        strategy, level = _make_strategy_with_filled_level(direction="long")
        initial_balance = strategy.paper_balance

        # TP should be set
        assert level.take_profit > level.fill_price

        # Price hits TP
        events = strategy.check_tp_sl(level.take_profit + 1)
        assert len(events) == 1
        assert events[0]["type"] == "take_profit"
        assert events[0]["pnl"] > 0

        # Position closed
        assert strategy.long_holdings == 0.0
        # Balance increased
        assert strategy.paper_balance > initial_balance

    def test_full_trade_with_tp_short(self):
        """Short level fills, price drops to TP, level closes with profit."""
        strategy, level = _make_strategy_with_filled_level(direction="short")

        # TP for short should be below fill
        assert level.take_profit < level.fill_price

        events = strategy.check_tp_sl(level.take_profit - 1)
        assert len(events) == 1
        assert events[0]["type"] == "take_profit"
        assert events[0]["pnl"] > 0
        assert strategy.short_holdings == 0.0


@pytest.mark.integration
class TestFullTradeWithSL:
    """End-to-end: fill → SL hit → close → loss recorded."""

    def test_full_trade_with_sl(self):
        """Long level fills, price drops to SL, level closes with loss."""
        strategy, level = _make_strategy_with_filled_level(direction="long")
        initial_balance = strategy.paper_balance

        # SL should be set below fill
        assert level.stop_loss < level.fill_price

        # Price hits SL
        events = strategy.check_tp_sl(level.stop_loss - 1)
        assert len(events) == 1
        assert events[0]["type"] == "stop_loss"
        assert events[0]["pnl"] < 0

        # Position closed
        assert strategy.long_holdings == 0.0

    def test_full_trade_with_sl_short(self):
        """Short level fills, price rises to SL, level closes with loss."""
        strategy, level = _make_strategy_with_filled_level(direction="short")

        # SL for short should be above fill
        assert level.stop_loss > level.fill_price

        events = strategy.check_tp_sl(level.stop_loss + 1)
        assert len(events) == 1
        assert events[0]["type"] == "stop_loss"
        assert events[0]["pnl"] < 0
        assert strategy.short_holdings == 0.0


@pytest.mark.integration
class TestTrailingStopFlow:
    """End-to-end trailing stop flow."""

    def test_trailing_stop_flow(self):
        """Price rises, trailing activates, then price drops → trailing stop hits."""
        strategy, level = _make_strategy_with_filled_level(
            direction="long", trailing_enabled=True,
            tp_pct=10.0,  # Set TP far away so trailing triggers first
        )

        fill = level.fill_price

        # Price rises +2% — past activation (0.5%) but below TP (10%)
        high_price = fill * 1.02
        events = strategy.check_tp_sl(high_price)
        # Should not trigger yet (above trail)
        assert len([e for e in events if e.get("type") == "trailing_stop"]) == 0
        assert level.trailing_high == high_price

        # Price drops below trail price: high * (1 - 1%) = high * 0.99
        trail_trigger = high_price * 0.985  # Well below trail
        events = strategy.check_tp_sl(trail_trigger)
        trailing_events = [e for e in events if e.get("type") == "trailing_stop"]
        assert len(trailing_events) == 1
        assert trailing_events[0]["pnl"] > 0  # Still profit (above fill)

    def test_trailing_stop_short_flow(self):
        """Short: price drops, trailing activates, then rebounds → stop hits."""
        strategy, level = _make_strategy_with_filled_level(
            direction="short", trailing_enabled=True,
            tp_pct=10.0,  # Set TP far away so trailing triggers first
        )

        fill = level.fill_price

        # Price drops -2% (below TP which is at -10%)
        low_price = fill * 0.98
        events = strategy.check_tp_sl(low_price)
        assert len([e for e in events if e.get("type") == "trailing_stop"]) == 0
        assert level.trailing_low == low_price

        # Price rebounds above trail: low * (1 + 1%) * extra
        trail_trigger = low_price * 1.015
        events = strategy.check_tp_sl(trail_trigger)
        trailing_events = [e for e in events if e.get("type") == "trailing_stop"]
        assert len(trailing_events) == 1


@pytest.mark.integration
class TestBreakEvenThenTrail:
    """Break-even activates, then trailing stop takes over."""

    def test_break_even_then_trail(self):
        """Break-even moves SL to entry, then trailing takes profit."""
        strategy, level = _make_strategy_with_filled_level(
            direction="long", trailing_enabled=True, break_even_enabled=True,
            tp_pct=10.0,  # Set TP far away so trailing triggers first
        )

        fill = level.fill_price
        original_sl = level.stop_loss

        # Price rises +1.5% — triggers break-even (threshold = 1%)
        events = strategy.check_tp_sl(fill * 1.015)
        assert level.break_even_triggered is True
        # SL should now be near entry (fill_price * 1.001)
        assert level.stop_loss > original_sl
        assert level.stop_loss >= fill

        # Price continues up +3%
        events = strategy.check_tp_sl(fill * 1.03)
        assert level.trailing_high == fill * 1.03

        # Price drops — but not below trail price from 1.03 peak
        # Trail price = 1.03 * fill * (1 - 0.01)
        trail_price = fill * 1.03 * 0.99
        # Just above trail — no trigger
        events = strategy.check_tp_sl(trail_price + 1)
        assert len([e for e in events if e.get("type") == "trailing_stop"]) == 0

        # Below trail — triggers
        events = strategy.check_tp_sl(trail_price - 10)
        trailing_events = [e for e in events if e.get("type") == "trailing_stop"]
        assert len(trailing_events) == 1
        assert trailing_events[0]["pnl"] > 0


@pytest.mark.integration
class TestCalculateSignalsSetsTPSL:
    """Test that calculate_signals sets TP/SL on newly filled levels."""

    def test_signal_fill_sets_tp_sl(self):
        """When a level is triggered via calculate_signals, TP/SL should be set."""
        config = GridConfig(
            grid_levels=3, grid_spacing_pct=1.0, amount_per_level=0.01,
            direction="long",
            tp_mode="fixed", sl_mode="fixed",
            tp_pct=2.0, sl_pct=1.0,
            trailing_enabled=False, break_even_enabled=False,
        )
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        strategy.setup_grid(50000.0)
        df = make_ohlcv_df(30, base_price=50000.0)

        # Trigger a buy level
        signals = strategy.calculate_signals(df, 49400.0)
        assert len(signals) >= 1

        # Find the filled level
        filled = [l for l in strategy.levels if l.filled and l.fill_price > 0]
        assert len(filled) >= 1
        level = filled[0]
        assert level.take_profit > 0
        assert level.stop_loss > 0
        assert level.fill_price > 0
        assert level.fill_time > 0


@pytest.mark.integration
class TestMultipleLevelsTPSL:
    """Test multiple levels with TP/SL interactions."""

    def test_multiple_levels_independent_tp_sl(self):
        """Each filled level should have its own independent TP/SL."""
        config = GridConfig(
            grid_levels=5, grid_spacing_pct=1.0, amount_per_level=0.01,
            direction="long",
            tp_mode="fixed", sl_mode="fixed",
            tp_pct=2.0, sl_pct=1.0,
            trailing_enabled=False, break_even_enabled=False,
        )
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        strategy.setup_grid(50000.0)

        # Manually fill two levels at different prices
        buy_levels = [l for l in strategy.levels if l.side == SignalType.BUY and not l.filled]
        for i, level in enumerate(buy_levels[:2]):
            level.filled = True
            level.fill_price = level.price
            level.fill_time = int(time.time() * 1000)
            level.trailing_high = level.price
            level.trailing_low = level.price
            strategy._set_tp_sl_for_level(level)

        # Each should have different TP/SL based on fill price
        assert buy_levels[0].take_profit != buy_levels[1].take_profit
        assert buy_levels[0].stop_loss != buy_levels[1].stop_loss
