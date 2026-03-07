"""Unit tests for database models and operations."""

import time
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.core.database import Base, OHLCV, Trade, Position, TradeLog


class TestTradeModel:
    """Tests for Trade model creation."""

    def test_create_trade(self, db_session):
        ts = int(time.time() * 1000)
        trade = Trade(
            symbol="BTC/USDT",
            side="buy",
            price=50000.0,
            amount=0.001,
            cost=50.0,
            fee=0.05,
            order_id="test_001",
            timestamp=ts,
        )
        db_session.add(trade)
        db_session.commit()

        result = db_session.query(Trade).first()
        assert result is not None
        assert result.symbol == "BTC/USDT"
        assert result.side == "buy"
        assert result.price == 50000.0
        assert result.amount == 0.001
        assert result.cost == 50.0
        assert result.fee == 0.05
        assert result.order_id == "test_001"

    def test_trade_repr(self):
        trade = Trade(
            symbol="BTC/USDT",
            side="buy",
            price=50000.0,
            amount=0.001,
            cost=50.0,
            timestamp=int(time.time() * 1000),
        )
        r = repr(trade)
        assert "buy" in r
        assert "BTC/USDT" in r

    def test_multiple_trades(self, db_session):
        for i in range(5):
            trade = Trade(
                symbol="BTC/USDT",
                side="buy" if i % 2 == 0 else "sell",
                price=50000.0 + i * 100,
                amount=0.001,
                cost=50.0,
                timestamp=int(time.time() * 1000) + i,
            )
            db_session.add(trade)
        db_session.commit()

        trades = db_session.query(Trade).all()
        assert len(trades) == 5


class TestPositionModel:
    """Tests for Position model creation and update."""

    def test_create_position(self, db_session):
        position = Position(
            symbol="BTC/USDT",
            side="long",
            entry_price=50000.0,
            amount=0.01,
            unrealized_pnl=0,
            realized_pnl=0,
        )
        db_session.add(position)
        db_session.commit()

        result = db_session.query(Position).first()
        assert result is not None
        assert result.symbol == "BTC/USDT"
        assert result.side == "long"
        assert result.entry_price == 50000.0
        assert result.amount == 0.01

    def test_update_position(self, db_session):
        position = Position(
            symbol="BTC/USDT",
            side="long",
            entry_price=50000.0,
            amount=0.01,
        )
        db_session.add(position)
        db_session.commit()

        # Update position
        position.amount = 0.02
        position.entry_price = 49500.0
        position.unrealized_pnl = 100.0
        db_session.commit()

        result = db_session.query(Position).filter_by(symbol="BTC/USDT").first()
        assert result.amount == 0.02
        assert result.entry_price == 49500.0
        assert result.unrealized_pnl == 100.0

    def test_position_repr(self):
        position = Position(
            symbol="BTC/USDT",
            side="long",
            entry_price=50000.0,
            amount=0.01,
        )
        r = repr(position)
        assert "long" in r
        assert "BTC/USDT" in r

    def test_position_unique_symbol(self, db_session):
        """Position symbol should be unique."""
        p1 = Position(symbol="BTC/USDT", side="long", entry_price=50000, amount=0.01)
        db_session.add(p1)
        db_session.commit()

        p2 = Position(symbol="BTC/USDT", side="long", entry_price=51000, amount=0.02)
        db_session.add(p2)
        with pytest.raises(Exception):
            db_session.commit()


class TestOHLCVModel:
    """Tests for OHLCV storage."""

    def test_create_ohlcv(self, db_session):
        candle = OHLCV(
            symbol="BTC/USDT",
            timeframe="1h",
            timestamp=1700000000000,
            open=50000.0,
            high=50500.0,
            low=49800.0,
            close=50200.0,
            volume=1234.56,
        )
        db_session.add(candle)
        db_session.commit()

        result = db_session.query(OHLCV).first()
        assert result is not None
        assert result.symbol == "BTC/USDT"
        assert result.timeframe == "1h"
        assert result.close == 50200.0
        assert result.volume == 1234.56

    def test_ohlcv_datetime_property(self, db_session):
        ts_ms = 1700000000000
        candle = OHLCV(
            symbol="BTC/USDT",
            timeframe="1h",
            timestamp=ts_ms,
            open=50000, high=50500, low=49800, close=50200, volume=100,
        )
        dt = candle.datetime
        assert isinstance(dt, datetime)
        assert dt.tzinfo == timezone.utc

    def test_ohlcv_repr(self):
        candle = OHLCV(
            symbol="BTC/USDT",
            timeframe="1h",
            timestamp=1700000000000,
            open=50000, high=50500, low=49800, close=50200, volume=100,
        )
        r = repr(candle)
        assert "BTC/USDT" in r
        assert "1h" in r

    def test_bulk_insert_ohlcv(self, db_session):
        base_ts = 1700000000000
        for i in range(100):
            candle = OHLCV(
                symbol="BTC/USDT",
                timeframe="1h",
                timestamp=base_ts + i * 3600000,
                open=50000 + i, high=50100 + i, low=49900 + i,
                close=50050 + i, volume=100 + i,
            )
            db_session.add(candle)
        db_session.commit()

        count = db_session.query(OHLCV).count()
        assert count == 100


class TestTradeLog:
    """Tests for TradeLog model."""

    def test_create_trade_log(self, db_session):
        log = TradeLog(
            timestamp=int(time.time() * 1000),
            symbol="BTC/USDT",
            side="buy",
            price=50000.0,
            amount=0.001,
            pnl=0,
            fees=0.05,
            strategy="grid",
            notes="test trade",
        )
        db_session.add(log)
        db_session.commit()

        result = db_session.query(TradeLog).first()
        assert result is not None
        assert result.strategy == "grid"

    def test_trade_log_to_dict(self, db_session):
        ts = int(time.time() * 1000)
        log = TradeLog(
            timestamp=ts,
            symbol="BTC/USDT",
            side="sell",
            price=51000.0,
            amount=0.001,
            pnl=1.0,
            fees=0.05,
            order_id="order_123",
            strategy="grid",
            notes="profit taking",
        )
        db_session.add(log)
        db_session.commit()

        d = log.to_dict()
        assert d["symbol"] == "BTC/USDT"
        assert d["side"] == "sell"
        assert d["price"] == 51000.0
        assert d["pnl"] == 1.0
        assert d["strategy"] == "grid"
        assert "datetime" in d

    def test_trade_log_datetime_utc(self):
        ts = 1700000000000
        log = TradeLog(
            timestamp=ts,
            symbol="BTC/USDT",
            side="buy",
            price=50000.0,
            amount=0.001,
        )
        dt = log.datetime_utc
        assert isinstance(dt, datetime)
        assert dt.tzinfo == timezone.utc
