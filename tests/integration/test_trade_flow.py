"""Integration tests for the full trade flow.

Tests the end-to-end path: setup grid → detect signals → execute paper trade
→ verify DB records → check position state.
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
def strategy():
    """Pre-configured grid strategy for testing."""
    config = GridConfig(grid_levels=5, grid_spacing_pct=1.0, amount_per_level=0.01)
    s = GridStrategy(symbol="BTC/USDT", config=config)
    s.setup_grid(50000.0)
    return s


@pytest.mark.integration
class TestFullTradeFlow:
    """End-to-end: execute trade → check DB → verify position."""

    def test_buy_creates_trade_and_position(self, trade_db, strategy):
        """A filled buy should create Trade and Position rows in DB."""
        Session = trade_db

        with patch("binance_bot.strategies.grid.SessionLocal", Session):
            signal = Signal(
                type=SignalType.BUY,
                price=49500.0,
                amount=0.01,
                reason="Grid level hit",
            )
            result = strategy.execute_paper_trade(signal)

        assert result["status"] == "filled"

        session = Session()
        trades = session.query(Trade).all()
        assert len(trades) == 1
        assert trades[0].symbol == "BTC/USDT"
        assert trades[0].side == "buy"
        assert trades[0].price == 49500.0
        assert trades[0].amount == 0.01

        position = session.query(Position).filter_by(symbol="BTC/USDT").first()
        assert position is not None
        assert position.side == "long"
        assert position.entry_price == 49500.0
        assert position.amount == 0.01
        session.close()

    def test_buy_then_sell_updates_position(self, trade_db, strategy):
        """Buy then sell should update position and realize PnL."""
        Session = trade_db

        with patch("binance_bot.strategies.grid.SessionLocal", Session):
            # Buy
            buy_signal = Signal(
                type=SignalType.BUY,
                price=49500.0,
                amount=0.01,
                reason="Grid buy",
            )
            strategy.execute_paper_trade(buy_signal)

            # Sell at higher price
            sell_signal = Signal(
                type=SignalType.SELL,
                price=50500.0,
                amount=0.01,
                reason="Grid sell",
            )
            strategy.execute_paper_trade(sell_signal)

        session = Session()
        trades = session.query(Trade).all()
        assert len(trades) == 2

        position = session.query(Position).filter_by(symbol="BTC/USDT").first()
        assert position is not None
        assert position.side == "flat"
        assert position.amount == 0
        # PnL = (50500 - 49500) * 0.01 = 10.0
        assert position.realized_pnl == pytest.approx(10.0)
        session.close()

    def test_multiple_buys_average_entry(self, trade_db, strategy):
        """Multiple buys should average the entry price."""
        Session = trade_db

        with patch("binance_bot.strategies.grid.SessionLocal", Session):
            strategy.execute_paper_trade(
                Signal(type=SignalType.BUY, price=50000.0, amount=0.01, reason="buy1")
            )
            strategy.execute_paper_trade(
                Signal(type=SignalType.BUY, price=48000.0, amount=0.01, reason="buy2")
            )

        session = Session()
        position = session.query(Position).filter_by(symbol="BTC/USDT").first()
        assert position.amount == pytest.approx(0.02)
        # Average: (50000*0.01 + 48000*0.01) / 0.02 = 49000
        assert position.entry_price == pytest.approx(49000.0)
        assert position.side == "long"
        session.close()

    def test_signal_detection_to_execution(self, trade_db):
        """Full flow: grid setup → signal detection → paper execution → DB check."""
        Session = trade_db
        config = GridConfig(grid_levels=3, grid_spacing_pct=1.0, amount_per_level=0.01, direction="long")
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        strategy.setup_grid(50000.0)
        df = make_ohlcv_df(30, base_price=50000.0)

        with patch("binance_bot.strategies.grid.SessionLocal", Session):
            # Price drops to trigger buy signal
            signals = strategy.calculate_signals(df, 49400.0)
            assert len(signals) >= 1
            assert signals[0].type == SignalType.BUY

            # Execute the detected signal
            for signal in signals:
                result = strategy.execute_paper_trade(signal)
                assert result["status"] == "filled"

        # Verify paper state
        assert strategy.paper_holdings > 0
        assert strategy.paper_balance < 10000.0

        # Verify DB state
        session = Session()
        trade_count = session.query(Trade).count()
        assert trade_count == len(signals)

        position = session.query(Position).filter_by(symbol="BTC/USDT").first()
        assert position is not None
        assert position.side == "long"
        session.close()

    def test_partial_sell_keeps_position_long(self, trade_db, strategy):
        """Selling less than held should keep position as 'long'."""
        Session = trade_db

        with patch("binance_bot.strategies.grid.SessionLocal", Session):
            strategy.execute_paper_trade(
                Signal(type=SignalType.BUY, price=50000.0, amount=0.05, reason="big buy")
            )
            strategy.execute_paper_trade(
                Signal(type=SignalType.SELL, price=51000.0, amount=0.02, reason="partial sell")
            )

        session = Session()
        position = session.query(Position).filter_by(symbol="BTC/USDT").first()
        assert position.side == "long"
        assert position.amount == pytest.approx(0.03)
        session.close()

    def test_paper_balance_consistency(self, trade_db, strategy):
        """Paper balance should match expected values after buy+sell cycle."""
        Session = trade_db
        initial_balance = strategy.paper_balance

        with patch("binance_bot.strategies.grid.SessionLocal", Session):
            strategy.execute_paper_trade(
                Signal(type=SignalType.BUY, price=50000.0, amount=0.01, reason="buy")
            )
            strategy.execute_paper_trade(
                Signal(type=SignalType.SELL, price=52000.0, amount=0.01, reason="sell")
            )

        # Balance should be: initial - 50000*0.01 + 52000*0.01 = initial + 20
        expected = initial_balance - (50000.0 * 0.01) + (52000.0 * 0.01)
        assert strategy.paper_balance == pytest.approx(expected)
        assert strategy.paper_holdings == pytest.approx(0.0)
