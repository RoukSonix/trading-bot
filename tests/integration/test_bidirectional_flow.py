"""Integration tests for bi-directional grid trading flow (Sprint 20).

Tests end-to-end: grid setup with direction → signal detection → execute
paper trade → verify DB records → check long/short position state.
"""

import pytest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.core.database import Base, Trade, Position
from binance_bot.strategies.base import Signal, SignalType
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


@pytest.fixture
def long_strategy():
    """Grid strategy configured for long-only."""
    config = GridConfig(grid_levels=5, grid_spacing_pct=1.0, amount_per_level=0.01, direction="long")
    s = GridStrategy(symbol="BTC/USDT", config=config)
    s.setup_grid(50000.0)
    return s


@pytest.fixture
def short_strategy():
    """Grid strategy configured for short-only."""
    config = GridConfig(grid_levels=5, grid_spacing_pct=1.0, amount_per_level=0.01, direction="short")
    s = GridStrategy(symbol="BTC/USDT", config=config)
    s.setup_grid(50000.0)
    return s


@pytest.fixture
def both_strategy():
    """Grid strategy configured for both directions."""
    config = GridConfig(grid_levels=5, grid_spacing_pct=1.0, amount_per_level=0.01, direction="both")
    s = GridStrategy(symbol="BTC/USDT", config=config)
    s.setup_grid(50000.0)
    return s


@pytest.mark.integration
class TestFullBidirectionalTradeFlow:
    """End-to-end bi-directional trading cycle."""

    def test_full_bidirectional_trade_cycle(self, trade_db, both_strategy):
        """Full cycle: long buy → long sell → short sell → short cover."""
        Session = trade_db
        strategy = both_strategy

        with patch("binance_bot.strategies.grid.SessionLocal", Session):
            # 1. Long buy
            long_buy = Signal(type=SignalType.BUY, price=49500.0, amount=0.01, reason="Long buy")
            result = strategy.execute_paper_trade(long_buy)
            assert result["status"] == "filled"
            assert strategy.long_holdings == pytest.approx(0.01)

            # 2. Long sell (take profit)
            long_sell = Signal(type=SignalType.SELL, price=50500.0, amount=0.01, reason="Long sell")
            result = strategy.execute_paper_trade(long_sell)
            assert result["status"] == "filled"
            assert strategy.long_holdings == pytest.approx(0.0)

            # 3. Short sell (open short)
            short_sell = Signal(type=SignalType.SELL, price=51000.0, amount=-0.01, reason="Short sell")
            result = strategy.execute_paper_trade(short_sell)
            assert result["status"] == "filled"
            assert strategy.short_holdings == pytest.approx(0.01)

            # 4. Short buy (cover)
            short_cover = Signal(type=SignalType.BUY, price=49000.0, amount=-0.01, reason="Short cover")
            result = strategy.execute_paper_trade(short_cover)
            assert result["status"] == "filled"
            assert strategy.short_holdings == pytest.approx(0.0)

        # Verify DB records
        session = Session()
        trades = session.query(Trade).all()
        assert len(trades) == 4

        # Verify all sides recorded
        sides = [t.side for t in trades]
        assert sides.count("buy") == 2
        assert sides.count("sell") == 2
        session.close()

    def test_long_trade_creates_position(self, trade_db, long_strategy):
        """Long buy should create a position with side='long'."""
        Session = trade_db

        with patch("binance_bot.strategies.grid.SessionLocal", Session):
            signal = Signal(type=SignalType.BUY, price=49500.0, amount=0.01, reason="Grid buy")
            strategy = long_strategy
            result = strategy.execute_paper_trade(signal)

        assert result["status"] == "filled"

        session = Session()
        position = session.query(Position).filter_by(symbol="BTC/USDT").first()
        assert position is not None
        assert position.side == "long"
        assert float(position.amount) == pytest.approx(0.01)
        assert float(position.entry_price) == pytest.approx(49500.0)
        session.close()

    def test_short_trade_creates_position(self, trade_db, short_strategy):
        """Short sell should create a position with short fields."""
        Session = trade_db

        with patch("binance_bot.strategies.grid.SessionLocal", Session):
            signal = Signal(type=SignalType.SELL, price=50500.0, amount=-0.01, reason="Short sell")
            strategy = short_strategy
            result = strategy.execute_paper_trade(signal)

        assert result["status"] == "filled"

        session = Session()
        position = session.query(Position).filter_by(symbol="BTC/USDT").first()
        assert position is not None
        assert position.side == "short"
        assert float(position.short_amount) == pytest.approx(0.01)
        assert float(position.short_entry) == pytest.approx(50500.0)
        session.close()

    def test_signal_detection_to_short_execution(self, trade_db):
        """Full flow: short grid setup → signal → execute → verify."""
        Session = trade_db
        config = GridConfig(grid_levels=3, grid_spacing_pct=1.0, amount_per_level=0.01, direction="short")
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        strategy.setup_grid(50000.0)
        df = make_ohlcv_df(30, base_price=50000.0)

        with patch("binance_bot.strategies.grid.SessionLocal", Session):
            # Price rises to trigger short sell
            signals = strategy.calculate_signals(df, 50600.0)
            assert len(signals) >= 1
            assert signals[0].amount < 0  # Short indicator

            for signal in signals:
                result = strategy.execute_paper_trade(signal)
                assert result["status"] == "filled"

        assert strategy.short_holdings > 0
        assert strategy.long_holdings == 0

        session = Session()
        trade_count = session.query(Trade).count()
        assert trade_count == len(signals)
        session.close()

    def test_paper_balance_consistency_bidirectional(self, trade_db, both_strategy):
        """Paper balance should be consistent after bidirectional trades."""
        Session = trade_db
        strategy = both_strategy
        initial_balance = strategy.paper_balance

        with patch("binance_bot.strategies.grid.SessionLocal", Session):
            # Long cycle: buy low, sell high
            strategy.execute_paper_trade(
                Signal(type=SignalType.BUY, price=49000.0, amount=0.01, reason="buy")
            )
            strategy.execute_paper_trade(
                Signal(type=SignalType.SELL, price=51000.0, amount=0.01, reason="sell")
            )

            # Short cycle: sell high, cover low
            strategy.execute_paper_trade(
                Signal(type=SignalType.SELL, price=52000.0, amount=-0.01, reason="short")
            )
            strategy.execute_paper_trade(
                Signal(type=SignalType.BUY, price=50000.0, amount=-0.01, reason="cover")
            )

        # Long profit: (51000 - 49000) * 0.01 = 20
        # Short profit: (52000 - 50000) * 0.01 = 20
        expected = initial_balance + 20.0 + 20.0
        assert strategy.paper_balance == pytest.approx(expected)
        assert strategy.long_holdings == pytest.approx(0.0)
        assert strategy.short_holdings == pytest.approx(0.0)


@pytest.mark.integration
class TestTrendChangeGridAdjustment:
    """Tests for grid adjustment on trend change."""

    def test_trend_change_grid_adjustment(self):
        """Grid should be reconfigurable when trend changes."""
        config = GridConfig(grid_levels=10, grid_spacing_pct=1.0, direction="both", trend_bias=True)
        strategy = GridStrategy(symbol="BTC/USDT", config=config)

        # Setup with uptrend data
        uptrend_df = make_ohlcv_df(100, base_price=50000.0, trend=0.01, seed=10)
        levels1 = strategy.setup_grid_with_trend(50000.0, uptrend_df)
        long_count_1 = len([l for l in levels1 if l.amount > 0])
        short_count_1 = len([l for l in levels1 if l.amount < 0])

        # Reset and setup with downtrend data
        downtrend_df = make_ohlcv_df(100, base_price=50000.0, trend=-0.01, seed=20)
        levels2 = strategy.setup_grid_with_trend(50000.0, downtrend_df)
        long_count_2 = len([l for l in levels2 if l.amount > 0])
        short_count_2 = len([l for l in levels2 if l.amount < 0])

        # Both setups should have levels
        assert len(levels1) > 0
        assert len(levels2) > 0
        # Trend data used — exact ratios depend on trend detection
        # but both should have at least some levels of each type
        assert long_count_1 > 0
        assert short_count_1 > 0
        assert long_count_2 > 0
        assert short_count_2 > 0

    def test_grid_can_be_rebuilt(self):
        """Grid can be torn down and rebuilt with new direction."""
        config = GridConfig(grid_levels=5, grid_spacing_pct=1.0, direction="long")
        strategy = GridStrategy(symbol="BTC/USDT", config=config)

        # Initially long-only
        levels1 = strategy.setup_grid(50000.0, direction="long")
        assert all(l.amount > 0 for l in levels1)

        # Switch to short-only
        levels2 = strategy.setup_grid(50000.0, direction="short")
        assert all(l.amount < 0 for l in levels2)

        # Switch to both
        levels3 = strategy.setup_grid(50000.0, direction="both")
        long_levels = [l for l in levels3 if l.amount > 0]
        short_levels = [l for l in levels3 if l.amount < 0]
        assert len(long_levels) > 0
        assert len(short_levels) > 0
