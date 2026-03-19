"""Alert rules engine for automatic alert triggering."""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional, Callable, Awaitable, Any

from loguru import logger


class RuleType(str, Enum):
    """Types of alert rules."""
    PRICE_MOVEMENT = "price_movement"
    PNL_THRESHOLD = "pnl_threshold"
    CONSECUTIVE_LOSSES = "consecutive_losses"
    BOT_STATUS = "bot_status"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    CONNECTION_ISSUE = "connection_issue"
    CUSTOM = "custom"


@dataclass
class AlertRule:
    """Definition of an alert rule."""
    
    name: str
    rule_type: RuleType
    enabled: bool = True
    
    # Price movement rule
    price_change_pct: Optional[float] = None  # e.g., 5.0 for 5%
    price_window_minutes: Optional[int] = None  # e.g., 15 minutes
    
    # PnL threshold rule
    profit_target: Optional[float] = None  # e.g., 500.0 USD
    stop_loss: Optional[float] = None  # e.g., -200.0 USD
    
    # Consecutive losses rule
    max_consecutive_losses: Optional[int] = None  # e.g., 5
    
    # Daily loss limit rule
    daily_loss_limit_pct: Optional[float] = None  # e.g., 5.0 for 5%
    
    # Connection issue rule
    connection_timeout_seconds: Optional[int] = None  # e.g., 60
    
    # Cooldown to prevent spam
    cooldown_minutes: int = 30
    last_triggered: Optional[datetime] = None
    
    def can_trigger(self) -> bool:
        """Check if rule can trigger (cooldown elapsed)."""
        if not self.enabled:
            return False
        if self.last_triggered is None:
            return True
        elapsed = datetime.now(timezone.utc) - self.last_triggered
        return elapsed >= timedelta(minutes=self.cooldown_minutes)
    
    def mark_triggered(self):
        """Mark rule as triggered."""
        self.last_triggered = datetime.now(timezone.utc)


@dataclass
class PricePoint:
    """Price data point for tracking."""
    price: float
    timestamp: datetime


class AlertRulesEngine:
    """Engine for evaluating alert rules."""
    
    def __init__(self):
        """Initialize rules engine."""
        self.rules: list[AlertRule] = []
        self._price_history: deque[PricePoint] = deque(maxlen=1000)
        self._consecutive_losses: int = 0
        self._daily_pnl: float = 0.0
        self._daily_start_balance: float = 0.0
        self._last_connection_time: datetime = datetime.now(timezone.utc)
        self._current_pnl: float = 0.0
        
        # Callback for sending alerts
        self._alert_callback: Optional[Callable[..., Awaitable[Any]]] = None
        
        # Initialize default rules
        self._init_default_rules()
    
    def _init_default_rules(self):
        """Initialize default alert rules."""
        self.rules = [
            AlertRule(
                name="Large Price Movement",
                rule_type=RuleType.PRICE_MOVEMENT,
                price_change_pct=5.0,
                price_window_minutes=15,
                cooldown_minutes=30,
            ),
            AlertRule(
                name="Profit Target Reached",
                rule_type=RuleType.PNL_THRESHOLD,
                profit_target=1000.0,
                cooldown_minutes=60,
            ),
            AlertRule(
                name="Stop Loss Alert",
                rule_type=RuleType.PNL_THRESHOLD,
                stop_loss=-500.0,
                cooldown_minutes=30,
            ),
            AlertRule(
                name="Consecutive Losses",
                rule_type=RuleType.CONSECUTIVE_LOSSES,
                max_consecutive_losses=5,
                cooldown_minutes=60,
            ),
            AlertRule(
                name="Daily Loss Limit",
                rule_type=RuleType.DAILY_LOSS_LIMIT,
                daily_loss_limit_pct=5.0,
                cooldown_minutes=120,
            ),
            AlertRule(
                name="Connection Lost",
                rule_type=RuleType.CONNECTION_ISSUE,
                connection_timeout_seconds=60,
                cooldown_minutes=5,
            ),
        ]
    
    def set_alert_callback(self, callback: Callable[..., Awaitable[Any]]):
        """Set callback for sending alerts.
        
        Args:
            callback: Async function to call when alert triggers.
                      Should accept (title: str, message: str, level: str)
        """
        self._alert_callback = callback
    
    def add_rule(self, rule: AlertRule):
        """Add a new rule."""
        self.rules.append(rule)
        logger.info(f"Alert rule added: {rule.name}")
    
    def remove_rule(self, name: str) -> bool:
        """Remove a rule by name."""
        for i, rule in enumerate(self.rules):
            if rule.name == name:
                self.rules.pop(i)
                logger.info(f"Alert rule removed: {name}")
                return True
        return False
    
    def enable_rule(self, name: str, enabled: bool = True) -> bool:
        """Enable or disable a rule."""
        for rule in self.rules:
            if rule.name == name:
                rule.enabled = enabled
                logger.info(f"Alert rule {'enabled' if enabled else 'disabled'}: {name}")
                return True
        return False
    
    def get_rules(self) -> list[dict]:
        """Get all rules as dicts."""
        return [
            {
                "name": r.name,
                "type": r.rule_type.value,
                "enabled": r.enabled,
                "cooldown_minutes": r.cooldown_minutes,
                "last_triggered": r.last_triggered.isoformat() if r.last_triggered else None,
                "config": {
                    "price_change_pct": r.price_change_pct,
                    "price_window_minutes": r.price_window_minutes,
                    "profit_target": r.profit_target,
                    "stop_loss": r.stop_loss,
                    "max_consecutive_losses": r.max_consecutive_losses,
                    "daily_loss_limit_pct": r.daily_loss_limit_pct,
                    "connection_timeout_seconds": r.connection_timeout_seconds,
                },
            }
            for r in self.rules
        ]
    
    # Update methods
    
    def update_price(self, price: float):
        """Update price history.
        
        Args:
            price: Current price
        """
        self._price_history.append(PricePoint(price=price, timestamp=datetime.now(timezone.utc)))
    
    def record_trade(self, pnl: float):
        """Record a trade result.
        
        Args:
            pnl: Trade profit/loss
        """
        self._current_pnl += pnl
        self._daily_pnl += pnl
        
        if pnl < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0
    
    def reset_daily_stats(self, current_balance: float):
        """Reset daily statistics.
        
        Args:
            current_balance: Current account balance
        """
        self._daily_pnl = 0.0
        self._daily_start_balance = current_balance
        logger.info("Daily stats reset")
    
    def update_connection(self):
        """Update last successful connection time."""
        self._last_connection_time = datetime.now(timezone.utc)
    
    def set_pnl(self, pnl: float):
        """Set current PnL directly.
        
        Args:
            pnl: Current unrealized + realized PnL
        """
        self._current_pnl = pnl
    
    # Evaluation methods
    
    async def evaluate_all(self) -> list[dict]:
        """Evaluate all rules and return triggered alerts.
        
        Returns:
            List of triggered alert info dicts
        """
        triggered = []
        
        for rule in self.rules:
            if not rule.can_trigger():
                continue
            
            result = self._evaluate_rule(rule)
            if result:
                rule.mark_triggered()
                triggered.append(result)
                
                # Send alert if callback set
                if self._alert_callback:
                    try:
                        await self._alert_callback(
                            title=result["title"],
                            message=result["message"],
                            level=result["level"],
                        )
                    except Exception as e:
                        logger.error(f"Alert callback error: {e}")
        
        return triggered
    
    def _evaluate_rule(self, rule: AlertRule) -> Optional[dict]:
        """Evaluate a single rule.
        
        Returns:
            Alert info dict if triggered, None otherwise
        """
        if rule.rule_type == RuleType.PRICE_MOVEMENT:
            return self._eval_price_movement(rule)
        elif rule.rule_type == RuleType.PNL_THRESHOLD:
            return self._eval_pnl_threshold(rule)
        elif rule.rule_type == RuleType.CONSECUTIVE_LOSSES:
            return self._eval_consecutive_losses(rule)
        elif rule.rule_type == RuleType.DAILY_LOSS_LIMIT:
            return self._eval_daily_loss_limit(rule)
        elif rule.rule_type == RuleType.CONNECTION_ISSUE:
            return self._eval_connection_issue(rule)
        
        return None
    
    def _eval_price_movement(self, rule: AlertRule) -> Optional[dict]:
        """Evaluate price movement rule."""
        if not rule.price_change_pct or not rule.price_window_minutes:
            return None
        
        if len(self._price_history) < 2:
            return None
        
        # Get price from N minutes ago
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=rule.price_window_minutes)
        old_price = None
        
        for point in reversed(self._price_history):
            if point.timestamp <= cutoff:
                old_price = point.price
                break
        
        if old_price is None:
            # Not enough history
            return None
        
        current_price = self._price_history[-1].price
        change_pct = ((current_price - old_price) / old_price) * 100
        
        if abs(change_pct) >= rule.price_change_pct:
            direction = "up" if change_pct > 0 else "down"
            return {
                "rule": rule.name,
                "type": RuleType.PRICE_MOVEMENT.value,
                "title": f"⚠️ Large Price Movement ({direction})",
                "message": f"Price moved {change_pct:+.2f}% in the last {rule.price_window_minutes} minutes\n"
                          f"From ${old_price:,.2f} to ${current_price:,.2f}",
                "level": "warning",
                "data": {
                    "change_pct": change_pct,
                    "old_price": old_price,
                    "current_price": current_price,
                },
            }
        
        return None
    
    def _eval_pnl_threshold(self, rule: AlertRule) -> Optional[dict]:
        """Evaluate PnL threshold rule."""
        # Check profit target
        if rule.profit_target and self._current_pnl >= rule.profit_target:
            return {
                "rule": rule.name,
                "type": RuleType.PNL_THRESHOLD.value,
                "title": "🎯 Profit Target Reached!",
                "message": f"Current PnL: ${self._current_pnl:+,.2f}\n"
                          f"Target: ${rule.profit_target:,.2f}",
                "level": "info",
                "data": {"pnl": self._current_pnl, "target": rule.profit_target},
            }
        
        # Check stop loss
        if rule.stop_loss and self._current_pnl <= rule.stop_loss:
            return {
                "rule": rule.name,
                "type": RuleType.PNL_THRESHOLD.value,
                "title": "🛑 Stop Loss Alert",
                "message": f"Current PnL: ${self._current_pnl:+,.2f}\n"
                          f"Stop Loss: ${rule.stop_loss:,.2f}",
                "level": "error",
                "data": {"pnl": self._current_pnl, "stop_loss": rule.stop_loss},
            }
        
        return None
    
    def _eval_consecutive_losses(self, rule: AlertRule) -> Optional[dict]:
        """Evaluate consecutive losses rule."""
        if not rule.max_consecutive_losses:
            return None
        
        if self._consecutive_losses >= rule.max_consecutive_losses:
            return {
                "rule": rule.name,
                "type": RuleType.CONSECUTIVE_LOSSES.value,
                "title": "📉 Consecutive Losses Alert",
                "message": f"Consecutive losing trades: {self._consecutive_losses}\n"
                          f"Threshold: {rule.max_consecutive_losses}",
                "level": "warning",
                "data": {"consecutive_losses": self._consecutive_losses},
            }
        
        return None
    
    def _eval_daily_loss_limit(self, rule: AlertRule) -> Optional[dict]:
        """Evaluate daily loss limit rule."""
        if not rule.daily_loss_limit_pct or self._daily_start_balance <= 0:
            return None
        
        daily_loss_pct = (self._daily_pnl / self._daily_start_balance) * 100
        
        if daily_loss_pct <= -rule.daily_loss_limit_pct:
            return {
                "rule": rule.name,
                "type": RuleType.DAILY_LOSS_LIMIT.value,
                "title": "🚨 Daily Loss Limit Reached",
                "message": f"Daily PnL: ${self._daily_pnl:+,.2f} ({daily_loss_pct:+.2f}%)\n"
                          f"Limit: -{rule.daily_loss_limit_pct}%",
                "level": "critical",
                "data": {"daily_pnl": self._daily_pnl, "daily_loss_pct": daily_loss_pct},
            }
        
        return None
    
    def _eval_connection_issue(self, rule: AlertRule) -> Optional[dict]:
        """Evaluate connection issue rule."""
        if not rule.connection_timeout_seconds:
            return None
        
        elapsed = (datetime.now(timezone.utc) - self._last_connection_time).total_seconds()
        
        if elapsed >= rule.connection_timeout_seconds:
            return {
                "rule": rule.name,
                "type": RuleType.CONNECTION_ISSUE.value,
                "title": "🔌 Connection Issue",
                "message": f"No successful connection in {elapsed:.0f} seconds\n"
                          f"Timeout threshold: {rule.connection_timeout_seconds}s",
                "level": "error",
                "data": {"elapsed_seconds": elapsed},
            }
        
        return None


# Global instance
_rules_engine: Optional[AlertRulesEngine] = None


def get_rules_engine() -> AlertRulesEngine:
    """Get or create rules engine instance."""
    global _rules_engine
    if _rules_engine is None:
        _rules_engine = AlertRulesEngine()
    return _rules_engine
