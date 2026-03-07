"""Unit tests for grid trading strategy."""

import pytest

from binance_bot.strategies.base import Signal, SignalType, GridLevel
from binance_bot.strategies.grid import GridStrategy, GridConfig
from tests.conftest import make_ohlcv_df


class TestGridLevelGeneration:
    """Tests for grid level setup."""

    def test_default_grid_setup(self):
        strategy = GridStrategy(symbol="BTC/USDT")
        levels = strategy.setup_grid(50000.0)
        # Default: 10 buy levels + 10 sell levels = 20 total
        assert len(levels) == 20

    def test_grid_levels_count(self):
        config = GridConfig(grid_levels=5)
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        levels = strategy.setup_grid(50000.0)
        assert len(levels) == 10  # 5 buy + 5 sell

    def test_buy_levels_below_price(self):
        strategy = GridStrategy(symbol="BTC/USDT")
        levels = strategy.setup_grid(50000.0)
        buy_levels = [l for l in levels if l.side == SignalType.BUY]
        for level in buy_levels:
            assert level.price < 50000.0

    def test_sell_levels_above_price(self):
        strategy = GridStrategy(symbol="BTC/USDT")
        levels = strategy.setup_grid(50000.0)
        sell_levels = [l for l in levels if l.side == SignalType.SELL]
        for level in sell_levels:
            assert level.price > 50000.0

    def test_levels_sorted_by_price(self):
        strategy = GridStrategy(symbol="BTC/USDT")
        levels = strategy.setup_grid(50000.0)
        prices = [l.price for l in levels]
        assert prices == sorted(prices)

    def test_grid_spacing(self):
        config = GridConfig(grid_levels=3, grid_spacing_pct=2.0)
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        levels = strategy.setup_grid(10000.0)
        buy_levels = sorted(
            [l for l in levels if l.side == SignalType.BUY],
            key=lambda l: l.price,
            reverse=True,
        )
        # Spacing should be 2% of 10000 = 200
        for i in range(len(buy_levels) - 1):
            diff = buy_levels[i].price - buy_levels[i + 1].price
            assert diff == pytest.approx(200.0, abs=0.01)

    def test_center_price_stored(self):
        strategy = GridStrategy(symbol="BTC/USDT")
        strategy.setup_grid(42000.0)
        assert strategy.center_price == 42000.0

    def test_grid_amount_per_level(self):
        config = GridConfig(amount_per_level=0.005)
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        levels = strategy.setup_grid(50000.0)
        for level in levels:
            assert level.amount == 0.005


class TestSignalDetection:
    """Tests for buy/sell signal detection."""

    def test_buy_signal_when_price_drops(self):
        config = GridConfig(grid_levels=3, grid_spacing_pct=1.0)
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        strategy.setup_grid(50000.0)
        df = make_ohlcv_df(30, base_price=50000.0)

        # Price drops to first buy level (50000 - 500 = 49500)
        signals = strategy.calculate_signals(df, 49400.0)
        assert len(signals) >= 1
        assert signals[0].type == SignalType.BUY

    def test_sell_signal_when_price_rises(self):
        config = GridConfig(grid_levels=3, grid_spacing_pct=1.0)
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        strategy.setup_grid(50000.0)
        df = make_ohlcv_df(30, base_price=50000.0)

        # Price rises to first sell level (50000 + 500 = 50500)
        signals = strategy.calculate_signals(df, 50600.0)
        assert len(signals) >= 1
        assert signals[0].type == SignalType.SELL

    def test_no_signal_at_center(self):
        config = GridConfig(grid_levels=3, grid_spacing_pct=1.0)
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        strategy.setup_grid(50000.0)
        df = make_ohlcv_df(30, base_price=50000.0)

        # Price at center should not trigger any signals
        signals = strategy.calculate_signals(df, 50000.0)
        assert len(signals) == 0

    def test_filled_level_not_retriggered(self):
        config = GridConfig(grid_levels=3, grid_spacing_pct=1.0)
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        strategy.setup_grid(50000.0)
        df = make_ohlcv_df(30, base_price=50000.0)

        # Trigger buy signal
        signals1 = strategy.calculate_signals(df, 49400.0)
        assert len(signals1) >= 1

        # Same price again should not retrigger the filled level
        signals2 = strategy.calculate_signals(df, 49400.0)
        # The filled level should not fire again
        filled_prices = {s.price for s in signals1}
        for s in signals2:
            assert s.price not in filled_prices

    def test_auto_setup_on_first_calculate(self):
        strategy = GridStrategy(symbol="BTC/USDT")
        df = make_ohlcv_df(30, base_price=50000.0)

        # Grid not set up yet - should auto-setup
        signals = strategy.calculate_signals(df, 50000.0)
        assert strategy.levels  # Grid should now be set up
        assert len(signals) == 0  # No signals on setup


class TestLevelFilling:
    """Tests for level filling logic."""

    def test_filled_level_creates_opposite(self):
        config = GridConfig(grid_levels=3, grid_spacing_pct=1.0)
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        strategy.setup_grid(50000.0)
        initial_count = len(strategy.levels)
        df = make_ohlcv_df(30, base_price=50000.0)

        # Trigger a buy signal
        strategy.calculate_signals(df, 49400.0)

        # Should have created a new opposite (sell) level
        assert len(strategy.levels) > initial_count

    def test_opposite_level_side(self):
        config = GridConfig(grid_levels=3, grid_spacing_pct=1.0)
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        strategy.setup_grid(50000.0)
        df = make_ohlcv_df(30, base_price=50000.0)

        # Get initial sell count
        initial_sells = len([l for l in strategy.levels if l.side == SignalType.SELL and not l.filled])

        # Trigger buy signal
        strategy.calculate_signals(df, 49400.0)

        # Should have added a sell level
        new_sells = len([l for l in strategy.levels if l.side == SignalType.SELL and not l.filled])
        assert new_sells > initial_sells


class TestGridStatus:
    """Tests for grid status reporting."""

    def test_status_fields(self):
        strategy = GridStrategy(symbol="BTC/USDT")
        strategy.setup_grid(50000.0)
        status = strategy.get_status()

        assert status["strategy"] == "GridStrategy"
        assert status["symbol"] == "BTC/USDT"
        assert status["center_price"] == 50000.0
        assert status["total_levels"] == 20
        assert "paper_trading" in status
        assert "config" in status

    def test_status_paper_trading(self):
        strategy = GridStrategy(symbol="BTC/USDT")
        strategy.setup_grid(50000.0)
        status = strategy.get_status()

        pt = status["paper_trading"]
        assert pt["balance_usdt"] == 10000.0
        assert pt["holdings_btc"] == 0.0
        assert pt["trades_count"] == 0

    def test_start_stop(self):
        strategy = GridStrategy(symbol="BTC/USDT")
        assert not strategy.is_active
        strategy.start()
        assert strategy.is_active
        strategy.stop()
        assert not strategy.is_active
