"""Unit tests for paper trade execution."""

import pytest
from unittest.mock import patch, MagicMock

from binance_bot.strategies.base import Signal, SignalType
from binance_bot.strategies.grid import GridStrategy, GridConfig


class TestPaperTradeExecution:
    """Tests for paper trade execution."""

    def _make_strategy(self) -> GridStrategy:
        config = GridConfig(grid_levels=5, amount_per_level=0.01)
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        strategy.setup_grid(50000.0)
        return strategy

    @patch("binance_bot.strategies.grid.get_session")
    def test_buy_execution(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_session_cls.return_value = mock_session

        strategy = self._make_strategy()
        signal = Signal(
            type=SignalType.BUY,
            price=49500.0,
            amount=0.01,
            reason="Grid level hit",
        )

        result = strategy.execute_paper_trade(signal)
        assert result["status"] == "filled"
        assert strategy.paper_holdings == 0.01
        assert strategy.paper_balance < 10000.0

    @patch("binance_bot.strategies.grid.get_session")
    def test_sell_execution(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_session_cls.return_value = mock_session

        strategy = self._make_strategy()
        # First buy some holdings
        strategy.paper_holdings = 0.05
        signal = Signal(
            type=SignalType.SELL,
            price=50500.0,
            amount=0.01,
            reason="Grid level hit",
        )

        result = strategy.execute_paper_trade(signal)
        assert result["status"] == "filled"
        assert strategy.paper_holdings == 0.04

    @patch("binance_bot.strategies.grid.get_session")
    def test_insufficient_funds(self, mock_session_cls):
        strategy = self._make_strategy()
        strategy.paper_balance = 10.0  # Only $10

        signal = Signal(
            type=SignalType.BUY,
            price=50000.0,
            amount=1.0,  # Would cost $50,000
            reason="Grid level hit",
        )

        result = strategy.execute_paper_trade(signal)
        assert result["status"] == "insufficient_funds"

    @patch("binance_bot.strategies.grid.get_session")
    def test_insufficient_holdings(self, mock_session_cls):
        strategy = self._make_strategy()
        strategy.paper_holdings = 0.0  # No holdings

        signal = Signal(
            type=SignalType.SELL,
            price=50000.0,
            amount=0.01,
            reason="Grid level hit",
        )

        result = strategy.execute_paper_trade(signal)
        assert result["status"] == "insufficient_holdings"


class TestBalanceUpdate:
    """Tests for paper balance and holdings updates."""

    @patch("binance_bot.strategies.grid.get_session")
    def test_balance_decreases_on_buy(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_session_cls.return_value = mock_session

        strategy = GridStrategy(symbol="BTC/USDT")
        strategy.setup_grid(50000.0)
        initial_balance = strategy.paper_balance

        signal = Signal(type=SignalType.BUY, price=49500.0, amount=0.001, reason="test")
        strategy.execute_paper_trade(signal)

        expected_cost = 49500.0 * 0.001
        assert strategy.paper_balance == pytest.approx(initial_balance - expected_cost)

    @patch("binance_bot.strategies.grid.get_session")
    def test_balance_increases_on_sell(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_session_cls.return_value = mock_session

        strategy = GridStrategy(symbol="BTC/USDT")
        strategy.setup_grid(50000.0)
        strategy.paper_holdings = 0.01

        signal = Signal(type=SignalType.SELL, price=50500.0, amount=0.001, reason="test")
        initial_balance = strategy.paper_balance
        strategy.execute_paper_trade(signal)

        expected_revenue = 50500.0 * 0.001
        assert strategy.paper_balance == pytest.approx(initial_balance + expected_revenue)

    @patch("binance_bot.strategies.grid.get_session")
    def test_holdings_update_on_buy(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_session_cls.return_value = mock_session

        strategy = GridStrategy(symbol="BTC/USDT")
        strategy.setup_grid(50000.0)

        signal = Signal(type=SignalType.BUY, price=49500.0, amount=0.005, reason="test")
        strategy.execute_paper_trade(signal)
        assert strategy.paper_holdings == pytest.approx(0.005)

    @patch("binance_bot.strategies.grid.get_session")
    def test_multiple_trades(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_session_cls.return_value = mock_session

        strategy = GridStrategy(symbol="BTC/USDT")
        strategy.setup_grid(50000.0)

        # Buy 3 times
        for _ in range(3):
            signal = Signal(type=SignalType.BUY, price=49500.0, amount=0.001, reason="test")
            strategy.execute_paper_trade(signal)

        assert strategy.paper_holdings == pytest.approx(0.003)
        assert len(strategy.paper_trades) == 3


class TestTradeSavedToDB:
    """Tests that trades are saved to the database."""

    @patch("binance_bot.strategies.grid.get_session")
    def test_trade_saved_on_fill(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_session_cls.return_value = mock_session

        strategy = GridStrategy(symbol="BTC/USDT")
        strategy.setup_grid(50000.0)

        signal = Signal(type=SignalType.BUY, price=49500.0, amount=0.001, reason="test")
        strategy.execute_paper_trade(signal)

        # Verify db.add was called (Trade + Position)
        assert mock_session.add.call_count >= 1
        mock_session.commit.assert_called_once()

    @patch("binance_bot.strategies.grid.get_session")
    def test_no_db_on_insufficient_funds(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        strategy = GridStrategy(symbol="BTC/USDT")
        strategy.setup_grid(50000.0)
        strategy.paper_balance = 0  # No money

        signal = Signal(type=SignalType.BUY, price=49500.0, amount=0.001, reason="test")
        strategy.execute_paper_trade(signal)

        # Should not save to DB
        mock_session.commit.assert_not_called()


class TestPositionUpdatedInDB:
    """Tests that positions are properly updated in DB."""

    @patch("binance_bot.strategies.grid.get_session")
    def test_new_position_created(self, mock_session_cls):
        mock_session = MagicMock()
        # No existing position
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_session_cls.return_value = mock_session

        strategy = GridStrategy(symbol="BTC/USDT")
        strategy.setup_grid(50000.0)

        signal = Signal(type=SignalType.BUY, price=49500.0, amount=0.001, reason="test")
        strategy.execute_paper_trade(signal)

        # Should have added Trade and Position
        assert mock_session.add.call_count == 2

    @patch("binance_bot.strategies.grid.get_session")
    def test_existing_position_updated_on_buy(self, mock_session_cls):
        mock_position = MagicMock()
        mock_position.entry_price = 50000.0
        mock_position.amount = 0.01

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_position
        mock_session_cls.return_value = mock_session

        strategy = GridStrategy(symbol="BTC/USDT")
        strategy.setup_grid(50000.0)

        signal = Signal(type=SignalType.BUY, price=49000.0, amount=0.005, reason="test")
        strategy.execute_paper_trade(signal)

        # Position should be updated
        assert mock_position.amount == pytest.approx(0.015)
        assert mock_position.side == "long"

    @patch("binance_bot.strategies.grid.get_session")
    def test_db_error_handled_gracefully(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.commit.side_effect = Exception("DB error")
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_session_cls.return_value = mock_session

        strategy = GridStrategy(symbol="BTC/USDT")
        strategy.setup_grid(50000.0)

        signal = Signal(type=SignalType.BUY, price=49500.0, amount=0.001, reason="test")
        # Should not raise - DB errors are caught
        result = strategy.execute_paper_trade(signal)
        assert result["status"] == "filled"
