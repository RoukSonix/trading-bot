"""Integration tests for Trade -> DB -> Position flow."""

import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch

from shared.core.database import Base, Trade, Position
from binance_bot.strategies.base import Signal, SignalType
from binance_bot.strategies.grid import GridStrategy, GridConfig
from tests.conftest import make_ohlcv_df


@pytest.fixture
def trade_db():
    """Set up in-memory DB for trade flow tests."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    yield engine, Session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.mark.integration
class TestTradeFlow:
    """Integration: Execute paper trade -> Verify trade in DB -> Verify position updated."""

    def test_buy_trade_persisted(self, trade_db):
        engine, Session = trade_db
        session = Session()

        config = GridConfig(grid_levels=3, amount_per_level=0.01)
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        strategy.setup_grid(50000.0)

        with patch("binance_bot.strategies.grid.SessionLocal", Session):
            signal = Signal(type=SignalType.BUY, price=49500.0, amount=0.01, reason="Grid hit")
            result = strategy.execute_paper_trade(signal)

        assert result["status"] == "filled"

        # Verify trade in DB
        trades = session.query(Trade).all()
        assert len(trades) == 1
        assert trades[0].symbol == "BTC/USDT"
        assert trades[0].side == "buy"
        assert trades[0].price == 49500.0
        assert trades[0].amount == 0.01

        # Verify position created
        position = session.query(Position).filter_by(symbol="BTC/USDT").first()
        assert position is not None
        assert position.side == "long"
        assert position.entry_price == 49500.0
        assert position.amount == 0.01

        session.close()

    def test_sell_trade_updates_position(self, trade_db):
        engine, Session = trade_db
        session = Session()

        # Create initial position
        position = Position(
            symbol="BTC/USDT",
            side="long",
            entry_price=49000.0,
            amount=0.05,
            unrealized_pnl=0,
            realized_pnl=0,
        )
        session.add(position)
        session.commit()

        config = GridConfig(grid_levels=3, amount_per_level=0.01)
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        strategy.setup_grid(50000.0)
        strategy.paper_holdings = 0.05

        with patch("binance_bot.strategies.grid.SessionLocal", Session):
            signal = Signal(type=SignalType.SELL, price=50500.0, amount=0.01, reason="Grid hit")
            result = strategy.execute_paper_trade(signal)

        assert result["status"] == "filled"

        # Verify trade in DB
        trades = session.query(Trade).all()
        assert len(trades) == 1
        assert trades[0].side == "sell"

        # Verify position updated
        session.refresh(position)
        assert position.amount == pytest.approx(0.04)
        assert position.realized_pnl > 0  # Sold at 50500 with entry at 49000

        session.close()

    def test_multiple_trades_flow(self, trade_db):
        engine, Session = trade_db
        session = Session()

        config = GridConfig(grid_levels=5, amount_per_level=0.001)
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        strategy.setup_grid(50000.0)

        with patch("binance_bot.strategies.grid.SessionLocal", Session):
            # Execute 3 buy trades
            for price in [49500.0, 49000.0, 48500.0]:
                signal = Signal(type=SignalType.BUY, price=price, amount=0.001, reason="Grid hit")
                result = strategy.execute_paper_trade(signal)
                assert result["status"] == "filled"

        # Verify all trades in DB
        trades = session.query(Trade).all()
        assert len(trades) == 3

        # Verify position accumulated
        position = session.query(Position).filter_by(symbol="BTC/USDT").first()
        assert position is not None
        assert position.amount == pytest.approx(0.003)
        assert position.side == "long"

        session.close()

    def test_full_round_trip(self, trade_db):
        """Buy then sell - verify complete round trip."""
        engine, Session = trade_db
        session = Session()

        config = GridConfig(grid_levels=3, amount_per_level=0.01)
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        strategy.setup_grid(50000.0)

        with patch("binance_bot.strategies.grid.SessionLocal", Session):
            # Buy
            buy_signal = Signal(type=SignalType.BUY, price=49500.0, amount=0.01, reason="Buy")
            strategy.execute_paper_trade(buy_signal)

            # Sell all
            sell_signal = Signal(type=SignalType.SELL, price=50500.0, amount=0.01, reason="Sell")
            strategy.execute_paper_trade(sell_signal)

        trades = session.query(Trade).all()
        assert len(trades) == 2
        assert trades[0].side in ("buy", "sell")
        assert trades[1].side in ("buy", "sell")

        position = session.query(Position).filter_by(symbol="BTC/USDT").first()
        assert position is not None
        assert position.amount == pytest.approx(0.0)
        assert position.side == "flat"
        assert position.realized_pnl > 0  # Profit from buy low sell high

        session.close()

    def test_grid_signal_to_trade_flow(self, trade_db):
        """Integration: Grid detects signal -> executes paper trade -> DB updated."""
        engine, Session = trade_db
        session = Session()

        config = GridConfig(grid_levels=3, grid_spacing_pct=1.0, amount_per_level=0.001)
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        strategy.setup_grid(50000.0)
        df = make_ohlcv_df(30, base_price=50000.0)

        with patch("binance_bot.strategies.grid.SessionLocal", Session):
            # Price drops below first buy level
            signals = strategy.calculate_signals(df, 49400.0)
            assert len(signals) >= 1

            for signal in signals:
                result = strategy.execute_paper_trade(signal)
                assert result["status"] == "filled"

        # Verify DB state
        trades = session.query(Trade).all()
        assert len(trades) >= 1

        position = session.query(Position).filter_by(symbol="BTC/USDT").first()
        assert position is not None
        assert position.amount > 0

        session.close()
