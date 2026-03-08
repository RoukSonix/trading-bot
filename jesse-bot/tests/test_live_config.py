"""
Tests for live_config.py — Jesse live mode configuration.

Tests exchange config, risk config, notification config, trading mode,
testnet detection, and config validation from environment variables.
"""

import os

import pytest


# Add jesse-bot root to path
import sys
jesse_bot_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if jesse_bot_dir not in sys.path:
    sys.path.insert(0, jesse_bot_dir)

from live_config import (
    get_exchange_config,
    get_risk_config,
    get_notification_config,
    get_trading_mode,
    is_testnet,
    validate_config,
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Clean relevant env vars before each test."""
    env_vars = [
        'BINANCE_API_KEY', 'BINANCE_API_SECRET',
        'JESSE_EXCHANGE_TYPE', 'JESSE_LEVERAGE', 'JESSE_LEVERAGE_MODE',
        'JESSE_STARTING_BALANCE',
        'RISK_MAX_POSITION_PCT', 'RISK_DAILY_LOSS_LIMIT_PCT',
        'RISK_MAX_DRAWDOWN_PCT', 'EMERGENCY_STOP_FILE',
        'DISCORD_WEBHOOK_URL', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID',
        'ALERTS_ENABLED', 'TRADING_MODE', 'BINANCE_TESTNET',
    ]
    for var in env_vars:
        monkeypatch.delenv(var, raising=False)


# ── get_exchange_config ──────────────────────────────────────────────


class TestGetExchangeConfig:
    """Tests for get_exchange_config."""

    def test_default_config(self):
        """Should return futures config with defaults."""
        config = get_exchange_config()
        assert 'Binance Perpetual Futures' in config
        futures = config['Binance Perpetual Futures']
        assert futures['fee'] == 0.0004
        assert futures['type'] == 'futures'
        assert futures['futures_leverage'] == 1
        assert futures['futures_leverage_mode'] == 'cross'
        assert futures['balance'] == 10000

    def test_api_keys_from_env(self, monkeypatch):
        """Should read API keys from environment."""
        monkeypatch.setenv('BINANCE_API_KEY', 'test_key_123')
        monkeypatch.setenv('BINANCE_API_SECRET', 'test_secret_456')
        config = get_exchange_config()
        futures = config['Binance Perpetual Futures']
        assert futures['api_key'] == 'test_key_123'
        assert futures['api_secret'] == 'test_secret_456'

    def test_custom_leverage(self, monkeypatch):
        """Should respect custom leverage from env."""
        monkeypatch.setenv('JESSE_LEVERAGE', '5')
        config = get_exchange_config()
        assert config['Binance Perpetual Futures']['futures_leverage'] == 5

    def test_isolated_margin_mode(self, monkeypatch):
        """Should respect isolated margin mode."""
        monkeypatch.setenv('JESSE_LEVERAGE_MODE', 'isolated')
        config = get_exchange_config()
        assert config['Binance Perpetual Futures']['futures_leverage_mode'] == 'isolated'

    def test_custom_starting_balance(self, monkeypatch):
        """Should respect custom starting balance."""
        monkeypatch.setenv('JESSE_STARTING_BALANCE', '50000')
        config = get_exchange_config()
        assert config['Binance Perpetual Futures']['balance'] == 50000

    def test_spot_exchange_type(self, monkeypatch):
        """Should add spot config when exchange type is spot."""
        monkeypatch.setenv('JESSE_EXCHANGE_TYPE', 'spot')
        config = get_exchange_config()
        assert 'Binance Spot' in config
        assert config['Binance Spot']['type'] == 'spot'
        assert config['Binance Spot']['fee'] == 0.001

    def test_futures_no_spot(self):
        """Default futures mode should not include spot config."""
        config = get_exchange_config()
        assert 'Binance Spot' not in config


# ── get_risk_config ──────────────────────────────────────────────────


class TestGetRiskConfig:
    """Tests for get_risk_config."""

    def test_default_values(self):
        """Should return sensible defaults."""
        risk = get_risk_config()
        assert risk['max_position_pct'] == 10.0
        assert risk['daily_loss_limit_pct'] == 5.0
        assert risk['max_drawdown_pct'] == 10.0
        assert risk['emergency_stop_file'] == 'EMERGENCY_STOP'

    def test_custom_values(self, monkeypatch):
        """Should read custom values from env."""
        monkeypatch.setenv('RISK_MAX_POSITION_PCT', '20')
        monkeypatch.setenv('RISK_DAILY_LOSS_LIMIT_PCT', '3')
        monkeypatch.setenv('RISK_MAX_DRAWDOWN_PCT', '15')
        monkeypatch.setenv('EMERGENCY_STOP_FILE', 'HALT')
        risk = get_risk_config()
        assert risk['max_position_pct'] == 20.0
        assert risk['daily_loss_limit_pct'] == 3.0
        assert risk['max_drawdown_pct'] == 15.0
        assert risk['emergency_stop_file'] == 'HALT'


# ── get_notification_config ──────────────────────────────────────────


class TestGetNotificationConfig:
    """Tests for get_notification_config."""

    def test_default_empty(self):
        """Should return empty strings and True for alerts_enabled by default."""
        notif = get_notification_config()
        assert notif['discord_webhook_url'] == ''
        assert notif['telegram_bot_token'] == ''
        assert notif['telegram_chat_id'] == ''
        assert notif['alerts_enabled'] is True

    def test_alerts_disabled(self, monkeypatch):
        """Should parse 'false' as False."""
        monkeypatch.setenv('ALERTS_ENABLED', 'false')
        notif = get_notification_config()
        assert notif['alerts_enabled'] is False

    def test_alerts_enabled_case_insensitive(self, monkeypatch):
        """Should handle case-insensitive 'True'."""
        monkeypatch.setenv('ALERTS_ENABLED', 'True')
        notif = get_notification_config()
        assert notif['alerts_enabled'] is True

    def test_webhook_from_env(self, monkeypatch):
        """Should read webhook URL from env."""
        monkeypatch.setenv('DISCORD_WEBHOOK_URL', 'https://discord.com/api/webhooks/123/abc')
        notif = get_notification_config()
        assert notif['discord_webhook_url'] == 'https://discord.com/api/webhooks/123/abc'


# ── get_trading_mode ─────────────────────────────────────────────────


class TestGetTradingMode:
    """Tests for get_trading_mode."""

    def test_default_paper(self):
        """Default should be paper mode."""
        assert get_trading_mode() == 'paper'

    def test_paper_mode(self, monkeypatch):
        """Should return 'paper' when set."""
        monkeypatch.setenv('TRADING_MODE', 'paper')
        assert get_trading_mode() == 'paper'

    def test_live_mode(self, monkeypatch):
        """Should return 'live' when set."""
        monkeypatch.setenv('TRADING_MODE', 'live')
        assert get_trading_mode() == 'live'


# ── is_testnet ───────────────────────────────────────────────────────


class TestIsTestnet:
    """Tests for is_testnet."""

    def test_default_true(self):
        """Default should be testnet (safe default)."""
        assert is_testnet() is True

    def test_true_values(self, monkeypatch):
        """Should recognize various true values."""
        for val in ('true', 'True', 'TRUE', '1', 'yes'):
            monkeypatch.setenv('BINANCE_TESTNET', val)
            assert is_testnet() is True, f"Failed for BINANCE_TESTNET={val}"

    def test_false_values(self, monkeypatch):
        """Should return False for non-true values."""
        for val in ('false', 'False', '0', 'no', 'production'):
            monkeypatch.setenv('BINANCE_TESTNET', val)
            assert is_testnet() is False, f"Failed for BINANCE_TESTNET={val}"


# ── validate_config ──────────────────────────────────────────────────


class TestValidateConfig:
    """Tests for validate_config."""

    def test_missing_api_key(self):
        """Should error when API key is missing."""
        errors = validate_config()
        assert any('BINANCE_API_KEY' in e for e in errors)

    def test_placeholder_api_key(self, monkeypatch):
        """Should error when API key is placeholder."""
        monkeypatch.setenv('BINANCE_API_KEY', 'your_api_key_here')
        monkeypatch.setenv('BINANCE_API_SECRET', 'real_secret')
        errors = validate_config()
        assert any('BINANCE_API_KEY' in e for e in errors)

    def test_missing_api_secret(self, monkeypatch):
        """Should error when API secret is missing."""
        monkeypatch.setenv('BINANCE_API_KEY', 'real_key')
        errors = validate_config()
        assert any('BINANCE_API_SECRET' in e for e in errors)

    def test_valid_keys(self, monkeypatch):
        """Should not have key errors with valid keys."""
        monkeypatch.setenv('BINANCE_API_KEY', 'real_key')
        monkeypatch.setenv('BINANCE_API_SECRET', 'real_secret')
        errors = validate_config()
        assert not any('BINANCE_API_KEY' in e for e in errors)
        assert not any('BINANCE_API_SECRET' in e for e in errors)

    def test_invalid_trading_mode(self, monkeypatch):
        """Should error for invalid trading mode."""
        monkeypatch.setenv('BINANCE_API_KEY', 'key')
        monkeypatch.setenv('BINANCE_API_SECRET', 'secret')
        monkeypatch.setenv('TRADING_MODE', 'yolo')
        errors = validate_config()
        assert any('TRADING_MODE' in e for e in errors)

    def test_live_without_testnet_warning(self, monkeypatch):
        """Should warn when live mode without testnet."""
        monkeypatch.setenv('BINANCE_API_KEY', 'key')
        monkeypatch.setenv('BINANCE_API_SECRET', 'secret')
        monkeypatch.setenv('TRADING_MODE', 'live')
        monkeypatch.setenv('BINANCE_TESTNET', 'false')
        errors = validate_config()
        assert any('DANGER' in e for e in errors)

    def test_live_with_testnet_no_warning(self, monkeypatch):
        """Should not warn when live mode with testnet."""
        monkeypatch.setenv('BINANCE_API_KEY', 'key')
        monkeypatch.setenv('BINANCE_API_SECRET', 'secret')
        monkeypatch.setenv('TRADING_MODE', 'live')
        monkeypatch.setenv('BINANCE_TESTNET', 'true')
        errors = validate_config()
        assert not any('DANGER' in e for e in errors)

    def test_dangerous_position_size(self, monkeypatch):
        """Should warn when max position > 50%."""
        monkeypatch.setenv('BINANCE_API_KEY', 'key')
        monkeypatch.setenv('BINANCE_API_SECRET', 'secret')
        monkeypatch.setenv('RISK_MAX_POSITION_PCT', '60')
        errors = validate_config()
        assert any('dangerously high' in e and 'RISK_MAX_POSITION_PCT' in e for e in errors)

    def test_dangerous_daily_loss(self, monkeypatch):
        """Should warn when daily loss limit > 20%."""
        monkeypatch.setenv('BINANCE_API_KEY', 'key')
        monkeypatch.setenv('BINANCE_API_SECRET', 'secret')
        monkeypatch.setenv('RISK_DAILY_LOSS_LIMIT_PCT', '25')
        errors = validate_config()
        assert any('dangerously high' in e and 'RISK_DAILY_LOSS_LIMIT_PCT' in e for e in errors)

    def test_dangerous_drawdown(self, monkeypatch):
        """Should warn when max drawdown > 30%."""
        monkeypatch.setenv('BINANCE_API_KEY', 'key')
        monkeypatch.setenv('BINANCE_API_SECRET', 'secret')
        monkeypatch.setenv('RISK_MAX_DRAWDOWN_PCT', '40')
        errors = validate_config()
        assert any('dangerously high' in e and 'RISK_MAX_DRAWDOWN_PCT' in e for e in errors)

    def test_all_valid(self, monkeypatch):
        """Should return empty list when all config is valid."""
        monkeypatch.setenv('BINANCE_API_KEY', 'real_key_abc')
        monkeypatch.setenv('BINANCE_API_SECRET', 'real_secret_def')
        monkeypatch.setenv('TRADING_MODE', 'paper')
        monkeypatch.setenv('BINANCE_TESTNET', 'true')
        errors = validate_config()
        assert errors == []
