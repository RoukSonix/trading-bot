"""Alerts module for trading bot notifications."""

from trading_bot.alerts.telegram import TelegramAlerter, telegram
from trading_bot.alerts.discord import DiscordAlert, get_discord_alert
from trading_bot.alerts.email import EmailAlert, get_email_alert
from trading_bot.alerts.manager import (
    AlertManager,
    AlertConfig,
    AlertLevel,
    AlertType,
    get_alert_manager,
)
from trading_bot.alerts.rules import (
    AlertRulesEngine,
    AlertRule,
    RuleType,
    get_rules_engine,
)

__all__ = [
    # Telegram
    "TelegramAlerter",
    "telegram",
    # Discord
    "DiscordAlert",
    "get_discord_alert",
    # Email
    "EmailAlert",
    "get_email_alert",
    # Manager
    "AlertManager",
    "AlertConfig",
    "AlertLevel",
    "AlertType",
    "get_alert_manager",
    # Rules
    "AlertRulesEngine",
    "AlertRule",
    "RuleType",
    "get_rules_engine",
]
