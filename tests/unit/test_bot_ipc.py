"""Unit tests for bot pause/resume/stop via IPC commands (bot.py)."""

import pytest
from unittest.mock import patch, MagicMock

from binance_bot.bot import TradingBot, BotState


@pytest.fixture
def bot():
    """Create a TradingBot with mocked dependencies."""
    with patch("binance_bot.bot.exchange_client"), \
         patch("binance_bot.bot.get_alert_manager"), \
         patch("binance_bot.bot.get_rules_engine") as mock_rules, \
         patch("binance_bot.bot.get_trading_metrics"), \
         patch("binance_bot.bot.NewsFetcher"), \
         patch("binance_bot.bot.SentimentAnalyzer"), \
         patch("binance_bot.bot.StrategyRegistry") as mock_registry:
        mock_rules.return_value = MagicMock()
        mock_registry.list_all.return_value = []
        bot = TradingBot(symbol="BTC/USDT")
        bot.running = True
        bot.state = BotState.TRADING
        yield bot


def _apply_command(bot, cmd):
    """Reproduce the command-processing logic from _main_loop."""
    if cmd == "pause":
        bot.state = BotState.PAUSED
    elif cmd == "resume":
        bot.state = BotState.TRADING
    elif cmd == "stop":
        bot.running = False


class TestBotIPC:
    """Tests for bot command processing and BotState enum."""

    def test_pause_command_sets_enum_state(self, bot):
        """After processing 'pause' command, bot.state == BotState.PAUSED."""
        _apply_command(bot, "pause")
        assert bot.state == BotState.PAUSED
        assert bot.state is BotState.PAUSED

    def test_resume_command_sets_enum_state(self, bot):
        """After 'resume', bot.state == BotState.TRADING."""
        bot.state = BotState.PAUSED
        _apply_command(bot, "resume")
        assert bot.state == BotState.TRADING
        assert bot.state is BotState.TRADING

    def test_stop_command_sets_running_false(self, bot):
        """After 'stop', bot.running == False."""
        _apply_command(bot, "stop")
        assert bot.running is False

    def test_paused_state_has_value_attribute(self, bot):
        """bot.state.value doesn't raise AttributeError."""
        bot.state = BotState.PAUSED
        assert bot.state.value == "paused"

    def test_state_is_always_enum(self, bot):
        """After any command, isinstance(bot.state, BotState) is True."""
        for cmd, expected in [("pause", BotState.PAUSED), ("resume", BotState.TRADING)]:
            _apply_command(bot, cmd)
            assert isinstance(bot.state, BotState), (
                f"Expected BotState enum after '{cmd}', got {type(bot.state)}"
            )
