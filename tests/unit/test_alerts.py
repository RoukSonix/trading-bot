"""Unit tests for alert system."""

import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.alerts.discord import DiscordAlert
from shared.alerts.manager import AlertConfig, AlertLevel, AlertManager


class TestDiscordPayloadFormatting:
    """Tests for Discord webhook payload formatting."""

    def test_trade_alert_buy_payload(self):
        alert = DiscordAlert(webhook_url="")  # Disabled, just test formatting
        # We can't easily test the payload without sending, so test the class setup
        assert alert.COLOR_SUCCESS == 0x00FF00
        assert alert.COLOR_ERROR == 0xFF0000
        assert alert.COLOR_INFO == 0x0099FF

    @pytest.mark.asyncio
    async def test_send_webhook_disabled(self):
        alert = DiscordAlert(webhook_url="")
        assert not alert.enabled
        result = await alert.send_trade_alert(
            symbol="BTC/USDT", side="buy", price=50000.0, amount=0.001,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_trade_alert_with_pnl(self):
        alert = DiscordAlert(webhook_url="")
        result = await alert.send_trade_alert(
            symbol="BTC/USDT", side="sell", price=51000.0, amount=0.001,
            pnl=1.0, pnl_pct=2.0,
        )
        assert result is False  # Disabled, but should not error

    @pytest.mark.asyncio
    async def test_error_alert_disabled(self):
        alert = DiscordAlert(webhook_url="")
        result = await alert.send_error_alert(
            error="Test error", context="unit_test",
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_status_alert_disabled(self):
        alert = DiscordAlert(webhook_url="")
        result = await alert.send_status_alert(
            status="started", symbol="BTC/USDT",
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_daily_summary_disabled(self):
        alert = DiscordAlert(webhook_url="")
        result = await alert.send_daily_summary(
            symbol="BTC/USDT",
            start_balance=10000, end_balance=10100,
            total_trades=5, winning_trades=3, losing_trades=2,
            total_pnl=100, max_drawdown=1.5,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_custom_alert_disabled(self):
        alert = DiscordAlert(webhook_url="")
        result = await alert.send_custom(
            title="Test", description="Test message",
        )
        assert result is False


class TestSilentFlag:
    """Tests for silent/suppress notifications flag."""

    @pytest.mark.asyncio
    async def test_silent_flag_default(self):
        """Default silent=True should add suppress flag to payload."""
        alert = DiscordAlert(webhook_url="https://fake.webhook.url/test")

        with patch.object(alert, "_get_session") as mock_get_session:
            mock_resp = AsyncMock()
            mock_resp.status = 204
            mock_session = AsyncMock()
            mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_session.post.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_get_session.return_value = mock_session

            await alert._send_webhook({"content": "test"}, silent=True)

            # Verify the payload includes flags=4096
            call_args = mock_session.post.call_args
            payload = call_args.kwargs.get("json", call_args[1].get("json", {}))
            assert payload.get("flags") == 4096

    @pytest.mark.asyncio
    async def test_non_silent_no_flag(self):
        """silent=False should not add suppress flag."""
        alert = DiscordAlert(webhook_url="https://fake.webhook.url/test")

        with patch.object(alert, "_get_session") as mock_get_session:
            mock_resp = AsyncMock()
            mock_resp.status = 204
            mock_session = AsyncMock()
            mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_session.post.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_get_session.return_value = mock_session

            await alert._send_webhook({"content": "test"}, silent=False)

            call_args = mock_session.post.call_args
            payload = call_args.kwargs.get("json", call_args[1].get("json", {}))
            assert "flags" not in payload


class TestRateLimiting:
    """Tests for alert rate limiting."""

    def test_rate_limit_global(self):
        config = AlertConfig(rate_limit_per_minute=3)
        manager = AlertManager(config=config)

        # First 3 should pass
        for i in range(3):
            assert manager._check_rate_limit(f"alert_{i}")
            manager._record_alert(f"alert_{i}")

        # 4th should be blocked
        assert not manager._check_rate_limit("alert_4")

    def test_rate_limit_same_type_interval(self):
        config = AlertConfig(min_alert_interval_seconds=10)
        manager = AlertManager(config=config)

        # First should pass
        assert manager._check_rate_limit("test_alert")
        manager._record_alert("test_alert")

        # Same type immediately should be blocked
        assert not manager._check_rate_limit("test_alert")

    def test_rate_limit_different_types_ok(self):
        config = AlertConfig(min_alert_interval_seconds=10)
        manager = AlertManager(config=config)

        assert manager._check_rate_limit("type_a")
        manager._record_alert("type_a")

        # Different type should pass
        assert manager._check_rate_limit("type_b")

    def test_alerts_blocked_counter(self):
        config = AlertConfig(rate_limit_per_minute=1)
        manager = AlertManager(config=config)

        manager._check_rate_limit("test")
        manager._record_alert("test")

        manager._check_rate_limit("test2")  # Blocked
        assert manager.alerts_blocked == 1

    def test_alerts_sent_counter(self):
        manager = AlertManager()
        manager._record_alert("test1")
        manager._record_alert("test2")
        assert manager.alerts_sent == 2


class TestAlertConfig:
    """Tests for AlertConfig."""

    def test_default_config(self):
        config = AlertConfig()
        assert config.alerts_enabled is True
        assert config.discord_enabled is True
        assert config.email_enabled is False
        assert config.rate_limit_per_minute == 10
        assert config.min_alert_interval_seconds == 5

    def test_custom_config(self):
        config = AlertConfig(
            alerts_enabled=False,
            rate_limit_per_minute=5,
        )
        assert config.alerts_enabled is False
        assert config.rate_limit_per_minute == 5

    def test_config_to_dict(self):
        config = AlertConfig()
        d = config.to_dict()
        assert "alerts_enabled" in d
        assert "rate_limit_per_minute" in d
        assert d["alerts_enabled"] is True

    def test_config_from_dict(self):
        data = {
            "alerts_enabled": False,
            "discord_enabled": False,
            "rate_limit_per_minute": 20,
        }
        config = AlertConfig.from_dict(data)
        assert config.alerts_enabled is False
        assert config.rate_limit_per_minute == 20


class TestAlertManager:
    """Tests for AlertManager."""

    @pytest.mark.asyncio
    async def test_trade_alert_disabled(self):
        config = AlertConfig(alerts_enabled=False)
        manager = AlertManager(config=config)
        result = await manager.send_trade_alert(
            symbol="BTC/USDT", side="buy", price=50000, amount=0.001,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_trade_alert_off(self):
        config = AlertConfig(alert_on_trade=False)
        manager = AlertManager(config=config)
        result = await manager.send_trade_alert(
            symbol="BTC/USDT", side="buy", price=50000, amount=0.001,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_error_alert_disabled(self):
        config = AlertConfig(alert_on_error=False)
        manager = AlertManager(config=config)
        result = await manager.send_error_alert(error="test")
        assert result is False

    def test_get_stats(self):
        manager = AlertManager()
        stats = manager.get_stats()
        assert "alerts_sent" in stats
        assert "alerts_blocked" in stats
        assert "config" in stats
