"""Multi-channel alert system."""

from shared.alerts.telegram import TelegramAlerter, telegram
from shared.alerts.discord import DiscordAlert, get_discord_alert
from shared.alerts.email import EmailAlert, get_email_alert
from shared.alerts.manager import AlertManager, AlertConfig, AlertLevel, AlertType, get_alert_manager
from shared.alerts.rules import AlertRulesEngine, AlertRule, RuleType, get_rules_engine

__all__ = [
    "TelegramAlerter",
    "telegram",
    "DiscordAlert",
    "get_discord_alert",
    "EmailAlert",
    "get_email_alert",
    "AlertManager",
    "AlertConfig",
    "AlertLevel",
    "AlertType",
    "get_alert_manager",
    "AlertRulesEngine",
    "AlertRule",
    "RuleType",
    "get_rules_engine",
]
