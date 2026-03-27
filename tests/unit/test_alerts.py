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


class TestTradeAlertValueField:
    """Tests for trade alert Value field (price * amount)."""

    @pytest.mark.asyncio
    async def test_trade_alert_value_field(self):
        """Verify send_trade_alert embed includes Value field with price * amount."""
        alert = DiscordAlert(webhook_url="https://fake.webhook.url/test")

        with patch.object(alert, "_get_session") as mock_get_session:
            mock_resp = AsyncMock()
            mock_resp.status = 204
            mock_session = AsyncMock()
            mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_session.post.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_get_session.return_value = mock_session

            await alert.send_trade_alert(
                symbol="BTC/USDT", side="buy", price=67500.0, amount=0.001,
            )

            call_args = mock_session.post.call_args
            payload = call_args.kwargs.get("json", call_args[1].get("json", {}))
            fields = payload["embeds"][0]["fields"]
            value_fields = [f for f in fields if f["name"] == "Value"]
            assert len(value_fields) == 1
            assert "$67.50" in value_fields[0]["value"]

    @pytest.mark.asyncio
    async def test_trade_alert_value_zero_amount(self):
        """Edge case: amount=0 should show $0.00 value."""
        alert = DiscordAlert(webhook_url="https://fake.webhook.url/test")

        with patch.object(alert, "_get_session") as mock_get_session:
            mock_resp = AsyncMock()
            mock_resp.status = 204
            mock_session = AsyncMock()
            mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_session.post.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_get_session.return_value = mock_session

            await alert.send_trade_alert(
                symbol="BTC/USDT", side="buy", price=50000.0, amount=0.0,
            )

            call_args = mock_session.post.call_args
            payload = call_args.kwargs.get("json", call_args[1].get("json", {}))
            fields = payload["embeds"][0]["fields"]
            value_fields = [f for f in fields if f["name"] == "Value"]
            assert len(value_fields) == 1
            assert "$0.00" in value_fields[0]["value"]


class TestDailySummaryNewFields:
    """Tests for daily summary current_balance and today_pnl fields."""

    @pytest.mark.asyncio
    async def test_daily_summary_current_balance_field(self):
        """Verify send_daily_summary embed includes Current Balance when provided."""
        alert = DiscordAlert(webhook_url="https://fake.webhook.url/test")

        with patch.object(alert, "_get_session") as mock_get_session:
            mock_resp = AsyncMock()
            mock_resp.status = 204
            mock_session = AsyncMock()
            mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_session.post.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_get_session.return_value = mock_session

            await alert.send_daily_summary(
                symbol="BTC/USDT",
                start_balance=10000, end_balance=10350,
                total_trades=12, winning_trades=8, losing_trades=4,
                total_pnl=350, max_drawdown=2.1,
                current_balance=10350.0,
            )

            call_args = mock_session.post.call_args
            payload = call_args.kwargs.get("json", call_args[1].get("json", {}))
            fields = payload["embeds"][0]["fields"]
            balance_fields = [f for f in fields if "Current Balance" in f["name"]]
            assert len(balance_fields) == 1
            assert "$10,350.00" in balance_fields[0]["value"]

    @pytest.mark.asyncio
    async def test_daily_summary_today_pnl_field(self):
        """Verify send_daily_summary embed includes Today PnL when provided."""
        alert = DiscordAlert(webhook_url="https://fake.webhook.url/test")

        with patch.object(alert, "_get_session") as mock_get_session:
            mock_resp = AsyncMock()
            mock_resp.status = 204
            mock_session = AsyncMock()
            mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_session.post.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_get_session.return_value = mock_session

            await alert.send_daily_summary(
                symbol="BTC/USDT",
                start_balance=10000, end_balance=10350,
                total_trades=12, winning_trades=8, losing_trades=4,
                total_pnl=350, max_drawdown=2.1,
                current_balance=10350.0, today_pnl=150.0,
            )

            call_args = mock_session.post.call_args
            payload = call_args.kwargs.get("json", call_args[1].get("json", {}))
            fields = payload["embeds"][0]["fields"]
            today_fields = [f for f in fields if f["name"] == "Today PnL"]
            assert len(today_fields) == 1
            assert "$+150.00" in today_fields[0]["value"]
            assert "+1.47%" in today_fields[0]["value"]

    @pytest.mark.asyncio
    async def test_daily_summary_today_pnl_percentage(self):
        """Verify percentage calculation handles zero starting balance."""
        alert = DiscordAlert(webhook_url="https://fake.webhook.url/test")

        with patch.object(alert, "_get_session") as mock_get_session:
            mock_resp = AsyncMock()
            mock_resp.status = 204
            mock_session = AsyncMock()
            mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_session.post.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_get_session.return_value = mock_session

            # today_pnl == current_balance means starting was 0 — no percentage
            await alert.send_daily_summary(
                symbol="BTC/USDT",
                start_balance=0, end_balance=100,
                total_trades=1, winning_trades=1, losing_trades=0,
                total_pnl=100, max_drawdown=0,
                current_balance=100.0, today_pnl=100.0,
            )

            call_args = mock_session.post.call_args
            payload = call_args.kwargs.get("json", call_args[1].get("json", {}))
            fields = payload["embeds"][0]["fields"]
            today_fields = [f for f in fields if f["name"] == "Today PnL"]
            assert len(today_fields) == 1
            # starting_balance = 100 - 100 = 0 → no percentage
            assert "%" not in today_fields[0]["value"]

    @pytest.mark.asyncio
    async def test_daily_summary_backward_compat(self):
        """Verify send_daily_summary works without new optional params."""
        alert = DiscordAlert(webhook_url="")
        result = await alert.send_daily_summary(
            symbol="BTC/USDT",
            start_balance=10000, end_balance=10100,
            total_trades=5, winning_trades=3, losing_trades=2,
            total_pnl=100, max_drawdown=1.5,
        )
        assert result is False  # Disabled, but should not error


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


class TestTradeAlertDirectionPassthrough:
    """Tests for direction/net_exposure passthrough via AlertManager."""

    @pytest.mark.asyncio
    async def test_manager_passes_direction_to_discord(self):
        """AlertManager.send_trade_alert should forward direction to discord."""
        config = AlertConfig(alerts_enabled=True, discord_enabled=True)
        manager = AlertManager(config=config)
        manager._discord = MagicMock()
        manager._discord.send_trade_alert = AsyncMock(return_value=True)

        await manager.send_trade_alert(
            symbol="BTC/USDT", side="buy", price=67500, amount=0.001,
            direction="long", net_exposure=0.005,
        )

        manager._discord.send_trade_alert.assert_called_once()
        call_kwargs = manager._discord.send_trade_alert.call_args.kwargs
        assert call_kwargs["direction"] == "long"
        assert call_kwargs["net_exposure"] == 0.005

    @pytest.mark.asyncio
    async def test_manager_passes_strategy_regime_to_discord(self):
        """AlertManager.send_trade_alert should forward strategy_name/regime."""
        config = AlertConfig(alerts_enabled=True, discord_enabled=True)
        manager = AlertManager(config=config)
        manager._discord = MagicMock()
        manager._discord.send_trade_alert = AsyncMock(return_value=True)

        await manager.send_trade_alert(
            symbol="BTC/USDT", side="buy", price=67500, amount=0.001,
            strategy_name="GridStrategy", regime="ranging",
        )

        call_kwargs = manager._discord.send_trade_alert.call_args.kwargs
        assert call_kwargs["strategy_name"] == "GridStrategy"
        assert call_kwargs["regime"] == "ranging"

    @pytest.mark.asyncio
    async def test_manager_trade_alert_backward_compat(self):
        """Existing callers without new params should still work."""
        config = AlertConfig(alerts_enabled=True, discord_enabled=True)
        manager = AlertManager(config=config)
        manager._discord = MagicMock()
        manager._discord.send_trade_alert = AsyncMock(return_value=True)

        await manager.send_trade_alert(
            symbol="BTC/USDT", side="buy", price=67500, amount=0.001,
        )

        call_kwargs = manager._discord.send_trade_alert.call_args.kwargs
        assert call_kwargs["direction"] is None
        assert call_kwargs["net_exposure"] is None
        assert call_kwargs["strategy_name"] is None
        assert call_kwargs["regime"] is None


class TestTradeAlertStrategyRegimeFields:
    """Tests for strategy/regime fields in Discord trade alert embed."""

    @pytest.mark.asyncio
    async def test_trade_alert_strategy_field(self):
        """Verify send_trade_alert embed includes Strategy field."""
        alert = DiscordAlert(webhook_url="https://fake.webhook.url/test")

        with patch.object(alert, "_get_session") as mock_get_session:
            mock_resp = AsyncMock()
            mock_resp.status = 204
            mock_session = AsyncMock()
            mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_session.post.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_get_session.return_value = mock_session

            await alert.send_trade_alert(
                symbol="BTC/USDT", side="buy", price=67500.0, amount=0.001,
                strategy_name="GridStrategy",
            )

            call_args = mock_session.post.call_args
            payload = call_args.kwargs.get("json", call_args[1].get("json", {}))
            fields = payload["embeds"][0]["fields"]
            strategy_fields = [f for f in fields if f["name"] == "Strategy"]
            assert len(strategy_fields) == 1
            assert "GridStrategy" in strategy_fields[0]["value"]

    @pytest.mark.asyncio
    async def test_trade_alert_regime_field(self):
        """Verify send_trade_alert embed includes Regime field."""
        alert = DiscordAlert(webhook_url="https://fake.webhook.url/test")

        with patch.object(alert, "_get_session") as mock_get_session:
            mock_resp = AsyncMock()
            mock_resp.status = 204
            mock_session = AsyncMock()
            mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_session.post.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_get_session.return_value = mock_session

            await alert.send_trade_alert(
                symbol="BTC/USDT", side="buy", price=67500.0, amount=0.001,
                regime="trending",
            )

            call_args = mock_session.post.call_args
            payload = call_args.kwargs.get("json", call_args[1].get("json", {}))
            fields = payload["embeds"][0]["fields"]
            regime_fields = [f for f in fields if f["name"] == "Regime"]
            assert len(regime_fields) == 1
            assert "trending" in regime_fields[0]["value"]

    @pytest.mark.asyncio
    async def test_trade_alert_no_strategy_no_field(self):
        """No Strategy field when strategy_name is None."""
        alert = DiscordAlert(webhook_url="https://fake.webhook.url/test")

        with patch.object(alert, "_get_session") as mock_get_session:
            mock_resp = AsyncMock()
            mock_resp.status = 204
            mock_session = AsyncMock()
            mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_session.post.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_get_session.return_value = mock_session

            await alert.send_trade_alert(
                symbol="BTC/USDT", side="buy", price=67500.0, amount=0.001,
            )

            call_args = mock_session.post.call_args
            payload = call_args.kwargs.get("json", call_args[1].get("json", {}))
            fields = payload["embeds"][0]["fields"]
            strategy_fields = [f for f in fields if f["name"] == "Strategy"]
            assert len(strategy_fields) == 0


class TestFillTimeGuard:
    """Test fill_time == 0 guard in check_tp_sl."""

    def test_fill_time_zero_skipped(self):
        """Level with fill_price > 0 but fill_time == 0 should be skipped."""
        from binance_bot.strategies.base import GridLevel, SignalType
        from binance_bot.strategies.grid import GridStrategy, GridConfig

        config = GridConfig(grid_levels=3, grid_spacing_pct=1.0)
        strategy = GridStrategy("BTC/USDT", config)

        # Manually create a level with fill_price set but fill_time == 0 (invalid state)
        level = GridLevel(
            price=50000.0, side=SignalType.BUY, amount=0.001,
            filled=True, fill_price=50000.0, fill_time=0,
            take_profit=51000.0, stop_loss=49000.0,
        )
        strategy.levels = [level]

        # Even though TP should trigger at 51500, fill_time==0 should skip it
        events = strategy.check_tp_sl(51500.0)
        assert len(events) == 0

    def test_fill_time_nonzero_processed(self):
        """Level with valid fill_time should be processed normally."""
        import time
        from binance_bot.strategies.base import GridLevel, SignalType
        from binance_bot.strategies.grid import GridStrategy, GridConfig

        config = GridConfig(grid_levels=3, grid_spacing_pct=1.0)
        strategy = GridStrategy("BTC/USDT", config)

        level = GridLevel(
            price=50000.0, side=SignalType.BUY, amount=0.001,
            filled=True, fill_price=50000.0,
            fill_time=int(time.time() * 1000),
            take_profit=51000.0, stop_loss=49000.0,
        )
        strategy.levels = [level]

        events = strategy.check_tp_sl(51500.0)
        assert len(events) == 1
        assert events[0]["type"] == "take_profit"
