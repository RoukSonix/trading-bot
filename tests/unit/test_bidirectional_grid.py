"""Unit tests for bi-directional grid trading (Sprint 20).

Tests long-only, short-only, and both-directions grid setups,
trend detection, grid bias allocation, and short position tracking.
"""

import pytest
import numpy as np
import pandas as pd

from binance_bot.strategies.base import Signal, SignalType, GridLevel
from binance_bot.strategies.grid import GridStrategy, GridConfig
from tests.conftest import make_ohlcv_df


class TestLongOnlyGrid:
    """Tests for long-only grid mode (backward-compatible)."""

    def test_long_only_grid_levels(self):
        """Long-only grid should create buy levels below and sell levels above."""
        config = GridConfig(grid_levels=5, grid_spacing_pct=1.0, direction="long")
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        levels = strategy.setup_grid(50000.0)

        assert len(levels) == 10  # 5 buy + 5 sell
        buy_levels = [l for l in levels if l.side == SignalType.BUY]
        sell_levels = [l for l in levels if l.side == SignalType.SELL]
        assert len(buy_levels) == 5
        assert len(sell_levels) == 5

        # All amounts should be positive (long side)
        for l in levels:
            assert l.amount > 0

        # Buy below, sell above
        for l in buy_levels:
            assert l.price < 50000.0
        for l in sell_levels:
            assert l.price > 50000.0

    def test_long_only_backward_compatible(self):
        """Default config with direction='both' should still create long levels."""
        strategy = GridStrategy(symbol="BTC/USDT")
        levels = strategy.setup_grid(50000.0, direction="long")

        buy_levels = [l for l in levels if l.side == SignalType.BUY and l.amount > 0]
        sell_levels = [l for l in levels if l.side == SignalType.SELL and l.amount > 0]
        assert len(buy_levels) == 10
        assert len(sell_levels) == 10

    def test_long_only_paper_trade_buy(self):
        """Long buy should increase paper holdings and long_holdings."""
        config = GridConfig(grid_levels=3, grid_spacing_pct=1.0, direction="long")
        strategy = GridStrategy(symbol="BTC/USDT", config=config)

        signal = Signal(type=SignalType.BUY, price=49500.0, amount=0.01, reason="Grid buy")
        result = strategy.execute_paper_trade(signal)

        assert result["status"] == "filled"
        assert strategy.paper_holdings == pytest.approx(0.01)
        assert strategy.long_holdings == pytest.approx(0.01)
        assert strategy.long_entry_price == pytest.approx(49500.0)
        assert strategy.short_holdings == 0.0


class TestShortOnlyGrid:
    """Tests for short-only grid mode."""

    def test_short_only_grid_levels(self):
        """Short-only grid: SELL above (open short), BUY below (cover)."""
        config = GridConfig(grid_levels=5, grid_spacing_pct=1.0, direction="short")
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        levels = strategy.setup_grid(50000.0)

        assert len(levels) == 10  # 5 short sell + 5 short buy

        # All amounts should be negative (short side)
        for l in levels:
            assert l.amount < 0

        sell_levels = [l for l in levels if l.side == SignalType.SELL]
        buy_levels = [l for l in levels if l.side == SignalType.BUY]
        assert len(sell_levels) == 5
        assert len(buy_levels) == 5

        # Short sells above center, short buys below
        for l in sell_levels:
            assert l.price > 50000.0
        for l in buy_levels:
            assert l.price < 50000.0

    def test_short_paper_trade_sell(self):
        """Short sell should increase short_holdings and add to balance."""
        config = GridConfig(grid_levels=3, grid_spacing_pct=1.0, direction="short")
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        initial_balance = strategy.paper_balance

        signal = Signal(type=SignalType.SELL, price=50500.0, amount=-0.01, reason="Short sell")
        result = strategy.execute_paper_trade(signal)

        assert result["status"] == "filled"
        assert result["is_short"] is True
        assert strategy.short_holdings == pytest.approx(0.01)
        assert strategy.short_entry_price == pytest.approx(50500.0)
        # Selling short adds cash
        assert strategy.paper_balance == pytest.approx(initial_balance + 50500.0 * 0.01)

    def test_short_paper_trade_cover(self):
        """Short buy (cover) should decrease short_holdings."""
        config = GridConfig(grid_levels=3, grid_spacing_pct=1.0, direction="short")
        strategy = GridStrategy(symbol="BTC/USDT", config=config)

        # First open short
        strategy.execute_paper_trade(
            Signal(type=SignalType.SELL, price=50500.0, amount=-0.01, reason="Open short")
        )
        balance_after_short = strategy.paper_balance

        # Then cover at lower price (profit)
        result = strategy.execute_paper_trade(
            Signal(type=SignalType.BUY, price=49500.0, amount=-0.01, reason="Cover short")
        )

        assert result["status"] == "filled"
        assert strategy.short_holdings == pytest.approx(0.0)
        # Profit from short: sold at 50500, bought back at 49500, on 0.01 units
        # Balance: after_short - 49500*0.01
        assert strategy.paper_balance == pytest.approx(balance_after_short - 49500.0 * 0.01)

    def test_short_position_tracking(self):
        """Multiple short sells should average the entry price."""
        strategy = GridStrategy(symbol="BTC/USDT")

        strategy.execute_paper_trade(
            Signal(type=SignalType.SELL, price=50000.0, amount=-0.01, reason="short 1")
        )
        strategy.execute_paper_trade(
            Signal(type=SignalType.SELL, price=52000.0, amount=-0.01, reason="short 2")
        )

        assert strategy.short_holdings == pytest.approx(0.02)
        # Average entry: (50000*0.01 + 52000*0.01) / 0.02 = 51000
        assert strategy.short_entry_price == pytest.approx(51000.0)


class TestBothDirectionsGrid:
    """Tests for bi-directional (both) grid mode."""

    def test_both_directions_grid(self):
        """Both directions should create long AND short levels."""
        config = GridConfig(grid_levels=5, grid_spacing_pct=1.0, direction="both")
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        levels = strategy.setup_grid(50000.0)

        # 5 long buy + 5 long sell + 5 short sell + 5 short buy = 20
        assert len(levels) == 20

        long_levels = [l for l in levels if l.amount > 0]
        short_levels = [l for l in levels if l.amount < 0]
        assert len(long_levels) == 10  # 5 buy + 5 sell
        assert len(short_levels) == 10  # 5 sell + 5 buy

    def test_both_directions_sorted(self):
        """All levels should be sorted by price regardless of direction."""
        config = GridConfig(grid_levels=5, grid_spacing_pct=1.0, direction="both")
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        levels = strategy.setup_grid(50000.0)

        prices = [l.price for l in levels]
        assert prices == sorted(prices)

    def test_default_direction_is_both(self):
        """Default GridConfig should use direction='both'."""
        config = GridConfig()
        assert config.direction == "both"

    def test_status_includes_long_short_counts(self):
        """Status should show long_levels and short_levels counts."""
        config = GridConfig(grid_levels=5, grid_spacing_pct=1.0, direction="both")
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        strategy.setup_grid(50000.0)

        status = strategy.get_status()
        assert "long_levels" in status
        assert "short_levels" in status
        assert status["long_levels"] == 10
        assert status["short_levels"] == 10
        assert status["config"]["direction"] == "both"

    def test_net_exposure_calculation(self):
        """Net exposure should be long_holdings - short_holdings."""
        strategy = GridStrategy(symbol="BTC/USDT")

        # Open long
        strategy.execute_paper_trade(
            Signal(type=SignalType.BUY, price=50000.0, amount=0.05, reason="buy")
        )
        # Open short
        strategy.execute_paper_trade(
            Signal(type=SignalType.SELL, price=51000.0, amount=-0.03, reason="short")
        )

        assert strategy.long_holdings == pytest.approx(0.05)
        assert strategy.short_holdings == pytest.approx(0.03)
        assert strategy.get_net_exposure() == pytest.approx(0.02)

    def test_status_paper_trading_fields(self):
        """Status paper_trading should include long/short/net exposure."""
        strategy = GridStrategy(symbol="BTC/USDT")
        strategy.setup_grid(50000.0)

        status = strategy.get_status()
        pt = status["paper_trading"]
        assert "long_holdings" in pt
        assert "short_holdings" in pt
        assert "net_exposure" in pt
        assert "long_entry_price" in pt
        assert "short_entry_price" in pt


class TestTrendDetection:
    """Tests for market trend detection."""

    def test_trend_detection_bullish(self):
        """Strong uptrend should be detected as bullish."""
        strategy = GridStrategy(symbol="BTC/USDT")
        df = make_ohlcv_df(100, base_price=50000.0, trend=0.01, seed=42)
        trend = strategy.detect_trend(df)
        assert trend in ("bullish", "sideways")  # Strong uptrend

    def test_trend_detection_bearish(self):
        """Strong downtrend should be detected as bearish."""
        strategy = GridStrategy(symbol="BTC/USDT")
        df = make_ohlcv_df(100, base_price=50000.0, trend=-0.01, seed=42)
        trend = strategy.detect_trend(df)
        assert trend in ("bearish", "sideways")  # Strong downtrend

    def test_trend_detection_sideways(self):
        """No trend should be detected as sideways."""
        strategy = GridStrategy(symbol="BTC/USDT")
        df = make_ohlcv_df(100, base_price=50000.0, trend=0.0, seed=42)
        trend = strategy.detect_trend(df)
        assert trend == "sideways"

    def test_trend_detection_insufficient_data(self):
        """Less than 50 candles should return sideways."""
        strategy = GridStrategy(symbol="BTC/USDT")
        df = make_ohlcv_df(30, base_price=50000.0, trend=0.01, seed=42)
        trend = strategy.detect_trend(df)
        assert trend == "sideways"


class TestGridBiasAllocation:
    """Tests for trend-based grid bias."""

    def test_grid_bias_bullish(self):
        """Bullish trend should bias toward long."""
        strategy = GridStrategy(symbol="BTC/USDT")
        long_ratio, short_ratio = strategy.get_grid_bias("bullish")
        assert long_ratio == pytest.approx(0.7)
        assert short_ratio == pytest.approx(0.3)
        assert long_ratio + short_ratio == pytest.approx(1.0)

    def test_grid_bias_bearish(self):
        """Bearish trend should bias toward short."""
        strategy = GridStrategy(symbol="BTC/USDT")
        long_ratio, short_ratio = strategy.get_grid_bias("bearish")
        assert long_ratio == pytest.approx(0.3)
        assert short_ratio == pytest.approx(0.7)

    def test_grid_bias_sideways(self):
        """Sideways market should be 50/50."""
        strategy = GridStrategy(symbol="BTC/USDT")
        long_ratio, short_ratio = strategy.get_grid_bias("sideways")
        assert long_ratio == pytest.approx(0.5)
        assert short_ratio == pytest.approx(0.5)

    def test_grid_setup_with_trend_creates_biased_levels(self):
        """setup_grid_with_trend should create levels even with no trend data."""
        config = GridConfig(grid_levels=10, grid_spacing_pct=1.0, direction="both", trend_bias=True)
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        df = make_ohlcv_df(100, base_price=50000.0, trend=0.0, seed=42)
        levels = strategy.setup_grid_with_trend(50000.0, df)

        assert len(levels) > 0
        # Should have both long and short levels
        long_levels = [l for l in levels if l.amount > 0]
        short_levels = [l for l in levels if l.amount < 0]
        assert len(long_levels) > 0
        assert len(short_levels) > 0


class TestShortSignalDetection:
    """Tests for signal detection with short levels."""

    def test_short_sell_signal(self):
        """Price rising above short-sell level should trigger signal."""
        config = GridConfig(grid_levels=3, grid_spacing_pct=1.0, direction="short")
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        strategy.setup_grid(50000.0)
        df = make_ohlcv_df(30, base_price=50000.0)

        # Price rises to first short sell level (50500)
        signals = strategy.calculate_signals(df, 50600.0)
        assert len(signals) >= 1
        assert signals[0].type == SignalType.SELL
        assert signals[0].amount < 0  # Short indicator

    def test_short_cover_signal(self):
        """Price dropping to short-buy level should trigger cover signal."""
        config = GridConfig(grid_levels=3, grid_spacing_pct=1.0, direction="short")
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        strategy.setup_grid(50000.0)
        df = make_ohlcv_df(30, base_price=50000.0)

        # Price drops to first short buy (cover) level (49500)
        signals = strategy.calculate_signals(df, 49400.0)
        assert len(signals) >= 1
        assert signals[0].type == SignalType.BUY
        assert signals[0].amount < 0  # Short indicator

    def test_short_signal_reason(self):
        """Short signals should have descriptive reason."""
        config = GridConfig(grid_levels=3, grid_spacing_pct=1.0, direction="short")
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        strategy.setup_grid(50000.0)
        df = make_ohlcv_df(30, base_price=50000.0)

        signals = strategy.calculate_signals(df, 50600.0)
        assert len(signals) >= 1
        assert "Short" in signals[0].reason or "short" in signals[0].reason.lower()


class TestConfigDefaults:
    """Tests for Sprint 20 config defaults."""

    def test_default_direction(self):
        config = GridConfig()
        assert config.direction == "both"

    def test_default_leverage(self):
        config = GridConfig()
        assert config.leverage == 1.0

    def test_default_trend_bias(self):
        config = GridConfig()
        assert config.trend_bias is True

    def test_custom_direction(self):
        config = GridConfig(direction="short")
        assert config.direction == "short"

    def test_custom_leverage(self):
        config = GridConfig(leverage=2.0)
        assert config.leverage == 2.0
