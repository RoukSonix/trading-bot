"""Unit tests for bot daily summary data builder."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest


class TestGetDailySummaryData:
    """Tests for TradingBot._get_daily_summary_data."""

    def _make_bot(self, risk_limits=None, risk_metrics=None, strategy=None):
        """Create a minimal TradingBot-like object for testing _get_daily_summary_data."""
        from binance_bot.bot import TradingBot

        with patch.object(TradingBot, "__init__", lambda self, *a, **kw: None):
            bot = TradingBot.__new__(TradingBot)

        bot.symbol = "BTC/USDT"
        bot.risk_limits = risk_limits
        bot.risk_metrics = risk_metrics or MagicMock(
            max_drawdown=0.02,
            winning_trades=3,
            losing_trades=1,
        )
        bot.strategy = strategy
        return bot

    @pytest.mark.asyncio
    async def test_get_daily_summary_data_includes_current_balance(self):
        """Verify _get_daily_summary_data returns current_balance."""
        strategy = MagicMock()
        strategy.get_status.return_value = {
            "paper_trading": {"total_value": 10500.0, "trades_count": 5},
        }

        with patch("binance_bot.bot.settings") as mock_settings:
            mock_settings.paper_initial_balance = 10000.0
            bot = self._make_bot(strategy=strategy)
            data = await bot._get_daily_summary_data()

        assert "current_balance" in data
        assert data["current_balance"] == 10500.0

    @pytest.mark.asyncio
    async def test_get_daily_summary_data_today_pnl_from_risk_limits(self):
        """Verify today PnL uses DailyStats when available."""
        from shared.risk.limits import DailyStats

        daily_stats = DailyStats(
            date=date.today(),
            starting_balance=10200.0,
            current_balance=10500.0,
            high_water_mark=10500.0,
        )
        risk_limits = MagicMock()
        risk_limits.daily_stats = daily_stats

        strategy = MagicMock()
        strategy.get_status.return_value = {
            "paper_trading": {"total_value": 10500.0, "trades_count": 5},
        }

        with patch("binance_bot.bot.settings") as mock_settings:
            mock_settings.paper_initial_balance = 10000.0
            bot = self._make_bot(risk_limits=risk_limits, strategy=strategy)
            data = await bot._get_daily_summary_data()

        assert "today_pnl" in data
        assert data["today_pnl"] == pytest.approx(300.0)  # 10500 - 10200

    @pytest.mark.asyncio
    async def test_get_daily_summary_data_today_pnl_fallback(self):
        """Verify fallback when risk_limits not available."""
        strategy = MagicMock()
        strategy.get_status.return_value = {
            "paper_trading": {"total_value": 10500.0, "trades_count": 5},
        }

        with patch("binance_bot.bot.settings") as mock_settings:
            mock_settings.paper_initial_balance = 10000.0
            bot = self._make_bot(strategy=strategy)
            # Remove risk_limits to trigger fallback
            del bot.risk_limits
            data = await bot._get_daily_summary_data()

        assert "today_pnl" in data
        # Fallback: end_balance - start_balance = 10500 - 10000 = 500
        assert data["today_pnl"] == pytest.approx(500.0)
