"""Alert Manager - centralized alert management with rate limiting."""

import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional
import traceback

from loguru import logger

from shared.alerts.discord import DiscordAlert, get_discord_alert
from shared.alerts.email import EmailAlert, get_email_alert


class AlertLevel(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"



class AlertConfig:
    """Alert configuration."""
    
    def __init__(
        self,
        alerts_enabled: bool = True,
        discord_enabled: bool = True,
        email_enabled: bool = False,
        alert_on_trade: bool = True,
        alert_on_error: bool = True,
        daily_summary_enabled: bool = True,
        daily_summary_time: str = "20:00",  # UTC
        rate_limit_per_minute: int = 10,
        min_alert_interval_seconds: int = 5,
    ):
        self.alerts_enabled = alerts_enabled
        self.discord_enabled = discord_enabled
        self.email_enabled = email_enabled
        self.alert_on_trade = alert_on_trade
        self.alert_on_error = alert_on_error
        self.daily_summary_enabled = daily_summary_enabled
        self.daily_summary_time = daily_summary_time
        self.rate_limit_per_minute = rate_limit_per_minute
        self.min_alert_interval_seconds = min_alert_interval_seconds

        # Validate daily_summary_time format
        try:
            parts = self.daily_summary_time.split(":")
            if len(parts) != 2:
                raise ValueError
            h, m = int(parts[0]), int(parts[1])
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError
        except (ValueError, AttributeError):
            self.daily_summary_time = "20:00"
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "alerts_enabled": self.alerts_enabled,
            "discord_enabled": self.discord_enabled,
            "email_enabled": self.email_enabled,
            "alert_on_trade": self.alert_on_trade,
            "alert_on_error": self.alert_on_error,
            "daily_summary_enabled": self.daily_summary_enabled,
            "daily_summary_time": self.daily_summary_time,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "min_alert_interval_seconds": self.min_alert_interval_seconds,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "AlertConfig":
        """Create from dictionary."""
        import inspect
        valid_params = set(inspect.signature(cls.__init__).parameters.keys()) - {"self"}
        return cls(**{k: v for k, v in data.items() if k in valid_params})


class AlertManager:
    """Centralized alert management with rate limiting and routing."""
    
    def __init__(self, config: Optional[AlertConfig] = None):
        """Initialize alert manager.
        
        Args:
            config: Alert configuration
        """
        self.config = config or AlertConfig()
        
        # Alert channels
        self._discord: Optional[DiscordAlert] = None
        self._email: Optional[EmailAlert] = None
        
        # Rate limiting
        self._alert_timestamps: deque = deque(maxlen=100)
        self._last_alert_time: dict[str, datetime] = {}
        
        # Stats
        self.alerts_sent = 0
        self.alerts_blocked = 0
        
        # Daily summary scheduler
        self._daily_summary_task: Optional[asyncio.Task] = None
        self._daily_summary_callback = None
    
    @property
    def discord(self) -> DiscordAlert:
        """Get Discord alert instance."""
        if self._discord is None:
            self._discord = get_discord_alert()
        return self._discord
    
    @property
    def email(self) -> EmailAlert:
        """Get email alert instance."""
        if self._email is None:
            self._email = get_email_alert()
        return self._email
    
    def _check_rate_limit(self, alert_type: str) -> bool:
        """Check if alert should be rate limited.
        
        Args:
            alert_type: Type of alert for deduplication
            
        Returns:
            True if alert should be sent, False if rate limited
        """
        now = datetime.now(timezone.utc)

        # Check per-minute global rate limit
        cutoff = now - timedelta(minutes=1)
        while self._alert_timestamps and self._alert_timestamps[0] < cutoff:
            self._alert_timestamps.popleft()
        
        if len(self._alert_timestamps) >= self.config.rate_limit_per_minute:
            self.alerts_blocked += 1
            logger.warning(f"Alert rate limited (global): {alert_type}")
            return False
        
        # Check minimum interval for same type
        if alert_type in self._last_alert_time:
            elapsed = (now - self._last_alert_time[alert_type]).total_seconds()
            if elapsed < self.config.min_alert_interval_seconds:
                self.alerts_blocked += 1
                logger.debug(f"Alert rate limited (interval): {alert_type}")
                return False
        
        return True
    
    def _record_alert(self, alert_type: str):
        """Record alert for rate limiting."""
        now = datetime.now(timezone.utc)
        self._alert_timestamps.append(now)
        self._last_alert_time[alert_type] = now
        self.alerts_sent += 1
    
    async def send_trade_alert(
        self,
        symbol: str,
        side: str,
        price: float,
        amount: float,
        pnl: Optional[float] = None,
        pnl_pct: Optional[float] = None,
        order_id: Optional[str] = None,
    ) -> bool:
        """Send trade alert to configured channels.
        
        Returns:
            True if sent to at least one channel
        """
        if not self.config.alerts_enabled or not self.config.alert_on_trade:
            return False
        
        alert_key = f"trade_{symbol}_{side}"
        if not self._check_rate_limit(alert_key):
            return False
        
        success = False
        
        if self.config.discord_enabled:
            result = await self.discord.send_trade_alert(
                symbol=symbol,
                side=side,
                price=price,
                amount=amount,
                pnl=pnl,
                pnl_pct=pnl_pct,
                order_id=order_id,
            )
            success = success or result
        
        if self.config.email_enabled and pnl is not None:
            # Only email for trades with PnL (position closes)
            body = f"""
Trade Executed: {side.upper()} {symbol}
Price: ${price:,.2f}
Amount: {amount:.6f}
PnL: ${pnl:+,.2f}
Order ID: {order_id or 'N/A'}
Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
            result = await self.email.send_alert(f"Trade: {side.upper()} {symbol}", body)
            success = success or result
        
        if success:
            self._record_alert(alert_key)
        
        return success
    
    async def send_status_alert(
        self,
        status: str,
        symbol: str,
        current_price: Optional[float] = None,
        total_value: Optional[float] = None,
        trades_count: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> bool:
        """Send status change alert."""
        if not self.config.alerts_enabled:
            return False
        
        alert_key = f"status_{status}"
        if not self._check_rate_limit(alert_key):
            return False
        
        success = False
        
        if self.config.discord_enabled:
            result = await self.discord.send_status_alert(
                status=status,
                symbol=symbol,
                current_price=current_price,
                total_value=total_value,
                trades_count=trades_count,
                reason=reason,
            )
            success = success or result
        
        if self.config.email_enabled and status in ("emergency", "stopped"):
            body = f"""
Bot Status Change: {status.upper()}
Symbol: {symbol}
Price: {f'${current_price:,.2f}' if current_price is not None else 'N/A'}
Portfolio: {f'${total_value:,.2f}' if total_value is not None else 'N/A'}
Reason: {reason or 'N/A'}
Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
            result = await self.email.send_alert(f"Bot {status.upper()}", body)
            success = success or result
        
        if success:
            self._record_alert(alert_key)
        
        return success
    
    async def send_error_alert(
        self,
        error: str,
        context: Optional[str] = None,
        exc: Optional[Exception] = None,
        level: AlertLevel = AlertLevel.ERROR,
    ) -> bool:
        """Send error alert."""
        if not self.config.alerts_enabled or not self.config.alert_on_error:
            return False
        
        alert_key = f"error_{context or 'general'}"
        if not self._check_rate_limit(alert_key):
            return False
        
        tb = None
        if exc:
            tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        
        success = False
        
        if self.config.discord_enabled:
            result = await self.discord.send_error_alert(
                error=error,
                context=context,
                traceback=tb,
            )
            success = success or result
        
        if self.config.email_enabled and level in (AlertLevel.ERROR, AlertLevel.CRITICAL):
            body = f"""
Error: {error}
Context: {context or 'N/A'}
Level: {level.value}
Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}

{('Traceback:\n' + tb) if tb else ''}
"""
            result = await self.email.send_alert(f"Error: {error[:50]}", body)
            success = success or result
        
        if success:
            self._record_alert(alert_key)
        
        return success
    
    async def send_daily_summary(
        self,
        symbol: str,
        start_balance: float,
        end_balance: float,
        total_trades: int,
        winning_trades: int,
        losing_trades: int,
        total_pnl: float,
        max_drawdown: float,
        best_trade: Optional[float] = None,
        worst_trade: Optional[float] = None,
        trades_list: Optional[list] = None,
        current_balance: Optional[float] = None,
        today_pnl: Optional[float] = None,
    ) -> bool:
        """Send daily summary to all channels."""
        if not self.config.alerts_enabled or not self.config.daily_summary_enabled:
            return False

        success = False

        if self.config.discord_enabled:
            result = await self.discord.send_daily_summary(
                symbol=symbol,
                start_balance=start_balance,
                end_balance=end_balance,
                total_trades=total_trades,
                winning_trades=winning_trades,
                losing_trades=losing_trades,
                total_pnl=total_pnl,
                max_drawdown=max_drawdown,
                best_trade=best_trade,
                worst_trade=worst_trade,
                trades_list=trades_list,
                current_balance=current_balance,
                today_pnl=today_pnl,
            )
            success = success or result

        if self.config.email_enabled:
            result = await self.email.send_daily_report(
                symbol=symbol,
                start_balance=start_balance,
                end_balance=end_balance,
                total_trades=total_trades,
                winning_trades=winning_trades,
                losing_trades=losing_trades,
                total_pnl=total_pnl,
                max_drawdown=max_drawdown,
                trades_list=trades_list,
                current_balance=current_balance,
                today_pnl=today_pnl,
            )
            success = success or result

        if success:
            self._record_alert("daily_summary")

        return success
    
    async def send_custom_alert(
        self,
        title: str,
        message: str,
        level: AlertLevel = AlertLevel.INFO,
        fields: Optional[list] = None,
    ) -> bool:
        """Send custom alert."""
        if not self.config.alerts_enabled:
            return False
        
        alert_key = f"custom_{title[:20]}"
        if not self._check_rate_limit(alert_key):
            return False
        
        color_map = {
            AlertLevel.INFO: 0x0099FF,
            AlertLevel.WARNING: 0xFFAA00,
            AlertLevel.ERROR: 0xFF0000,
            AlertLevel.CRITICAL: 0xFF0000,
        }
        
        success = False
        
        if self.config.discord_enabled:
            result = await self.discord.send_custom(
                title=title,
                description=message,
                color=color_map.get(level, 0x0099FF),
                fields=fields,
            )
            success = success or result
        
        if self.config.email_enabled and level in (AlertLevel.WARNING, AlertLevel.ERROR, AlertLevel.CRITICAL):
            result = await self.email.send_alert(title, message)
            success = success or result
        
        if success:
            self._record_alert(alert_key)
        
        return success

    async def send_tp_sl_alert(
        self,
        event_type: str,
        symbol: str,
        level_price: float,
        exit_price: float,
        pnl: float,
        direction: str = "long",
        break_even_price: Optional[float] = None,
    ) -> bool:
        """Send TP/SL event alert through all configured channels."""
        if not self.config.alerts_enabled:
            return False

        if not self._check_rate_limit("tp_sl"):
            return False

        sent = False
        if self.config.discord_enabled:
            sent = await self.discord.send_tp_sl_alert(
                event_type=event_type,
                symbol=symbol,
                level_price=level_price,
                exit_price=exit_price,
                pnl=pnl,
                direction=direction,
                break_even_price=break_even_price,
            )
        self._record_alert("tp_sl")
        return sent

    def start_daily_summary_scheduler(self, callback):
        """Start the daily summary scheduler.
        
        Args:
            callback: Async function that returns summary data dict
        """
        self._daily_summary_callback = callback
        self._daily_summary_task = asyncio.create_task(self._daily_summary_loop())
        logger.info(f"Daily summary scheduler started (UTC {self.config.daily_summary_time})")
    
    def stop_daily_summary_scheduler(self):
        """Stop the daily summary scheduler."""
        if self._daily_summary_task:
            self._daily_summary_task.cancel()
            self._daily_summary_task = None
            logger.info("Daily summary scheduler stopped")
    
    async def _daily_summary_loop(self):
        """Background loop for daily summary."""
        while True:
            try:
                # Parse target time
                try:
                    parts = self.config.daily_summary_time.split(":")
                    target_hour, target_minute = int(parts[0]), int(parts[1])
                except (ValueError, IndexError):
                    target_hour, target_minute = 20, 0
                
                now = datetime.now(timezone.utc)
                target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
                
                # If target time has passed today, schedule for tomorrow
                if target <= now:
                    target += timedelta(days=1)
                
                # Wait until target time
                wait_seconds = (target - now).total_seconds()
                logger.debug(f"Daily summary scheduled in {wait_seconds:.0f} seconds")
                await asyncio.sleep(wait_seconds)
                
                # Call callback and send summary
                if self._daily_summary_callback:
                    try:
                        data = await self._daily_summary_callback()
                        if data:
                            await self.send_daily_summary(**data)
                    except Exception as e:
                        logger.error(f"Daily summary callback error: {e}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Daily summary loop error: {e}")
                await asyncio.sleep(60)  # Wait a minute before retrying
    
    async def close(self):
        """Clean up resources."""
        self.stop_daily_summary_scheduler()
        if self._discord:
            await self._discord.close()
    
    def get_stats(self) -> dict:
        """Get alert statistics."""
        return {
            "alerts_sent": self.alerts_sent,
            "alerts_blocked": self.alerts_blocked,
            "config": self.config.to_dict(),
        }


# Global instance
_alert_manager: Optional[AlertManager] = None


def get_alert_manager(config: Optional[AlertConfig] = None) -> AlertManager:
    """Get or create alert manager instance."""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager(config)
    return _alert_manager
