"""Discord webhook alerts for trading bot."""

import asyncio
from datetime import datetime, timezone
from typing import Optional
import os

import aiohttp
from loguru import logger


class DiscordAlert:
    """Send alerts via Discord webhooks with rich embeds."""
    
    # Embed colors
    COLOR_SUCCESS = 0x00FF00  # Green
    COLOR_ERROR = 0xFF0000    # Red
    COLOR_WARNING = 0xFFAA00  # Orange
    COLOR_INFO = 0x0099FF     # Blue
    COLOR_PROFIT = 0x00FF00   # Green
    COLOR_LOSS = 0xFF0000     # Red
    
    def __init__(self, webhook_url: Optional[str] = None):
        """Initialize Discord alerter.
        
        Args:
            webhook_url: Discord webhook URL (or from env)
        """
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "")
        self.enabled = bool(self.webhook_url)
        self._session: Optional[aiohttp.ClientSession] = None
        
        if self.enabled:
            logger.info("Discord alerts enabled")
        else:
            logger.debug("Discord alerts disabled (no webhook URL)")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def _send_webhook(self, payload: dict, silent: bool = True) -> bool:
        """Send payload to Discord webhook.
        
        Args:
            payload: Discord webhook payload
            silent: If True, suppress notifications (default: True)
            
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            logger.debug(f"Discord (disabled): {payload.get('content', 'embed')}")
            return False
        
        # Ensure content exists for embed visibility
        if "embeds" in payload and payload["embeds"] and "content" not in payload:
            embed = payload["embeds"][0]
            title = embed.get("title", "Alert")
            payload["content"] = f"**{title}**"
        
        # Suppress notifications by default (silent mode)
        if silent:
            payload["flags"] = 4096  # SUPPRESS_NOTIFICATIONS
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                session = await self._get_session()
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 204:
                        return True
                    elif response.status == 429:
                        retry_after = (await response.json()).get("retry_after", 1)
                        logger.warning(f"Discord rate limited, retry after {retry_after}s (attempt {attempt + 1}/{max_retries})")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_after)
                            continue
                        return False
                    else:
                        text = await response.text()
                        logger.error(f"Discord error {response.status}: {text}")
                        return False
            except asyncio.TimeoutError:
                logger.error("Discord webhook timeout")
                return False
            except Exception as e:
                logger.error(f"Discord error: {e}")
                return False
        return False
    
    async def send_trade_alert(
        self,
        symbol: str,
        side: str,
        price: float,
        amount: float,
        pnl: Optional[float] = None,
        pnl_pct: Optional[float] = None,
        order_id: Optional[str] = None,
        direction: Optional[str] = None,
        net_exposure: Optional[float] = None,
        strategy_name: Optional[str] = None,
        regime: Optional[str] = None,
    ) -> bool:
        """Send trade notification with rich embed.

        Args:
            symbol: Trading pair (e.g., BTC/USDT)
            side: BUY or SELL
            price: Trade price
            amount: Trade amount
            pnl: Realized PnL (if closing)
            pnl_pct: PnL percentage
            order_id: Order ID
            direction: Trade direction - "long" or "short" (Sprint 20)
            net_exposure: Net exposure after trade (Sprint 20)
            strategy_name: Active strategy name
            regime: Current market regime

        Returns:
            True if sent successfully
        """
        is_buy = side.upper() == "BUY"
        is_short = direction == "short"

        # Determine color based on PnL or side
        if pnl is not None:
            color = self.COLOR_PROFIT if pnl >= 0 else self.COLOR_LOSS
        else:
            color = self.COLOR_INFO

        # Build directional title
        if is_short:
            if is_buy:
                title = "🔵 SHORT BUY (Cover) Executed"
            else:
                title = "🔴 SHORT SELL (Open) Executed"
        else:
            title = f"{'🟢 LONG BUY' if is_buy else '🔴 SELL'} Trade Executed"

        # Build side label
        side_label = side.upper()
        if is_short:
            side_label = f"SHORT {side_label}"
        elif direction == "long":
            side_label = f"LONG {side_label}"

        fields = [
            {"name": "Symbol", "value": symbol, "inline": True},
            {"name": "Side", "value": f"{'🟢' if is_buy else '🔴'} {side_label}", "inline": True},
            {"name": "Price", "value": f"${price:,.2f}", "inline": True},
            {"name": "Amount", "value": f"{amount:.6f}", "inline": True},
            {"name": "Value", "value": f"💰 ${price * amount:,.2f}", "inline": True},
        ]

        if direction:
            dir_emoji = "📈" if direction == "long" else "📉"
            fields.append({"name": "Direction", "value": f"{dir_emoji} {direction.upper()}", "inline": True})

        if pnl is not None:
            pnl_emoji = "📈" if pnl >= 0 else "📉"
            pnl_text = f"{pnl_emoji} ${pnl:+,.2f}"
            if pnl_pct is not None:
                pnl_text += f" ({pnl_pct:+.2f}%)"
            fields.append({"name": "PnL", "value": pnl_text, "inline": True})

        if net_exposure is not None:
            fields.append({"name": "Net Exposure", "value": f"📊 {net_exposure:.6f}", "inline": True})

        if strategy_name:
            fields.append({"name": "Strategy", "value": f"🎯 {strategy_name}", "inline": True})

        if regime:
            fields.append({"name": "Regime", "value": f"📊 {regime}", "inline": True})

        if order_id:
            fields.append({"name": "Order ID", "value": f"`{order_id}`", "inline": True})

        embed = {
            "title": title,
            "color": color,
            "fields": fields,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": "Trading Bot"},
        }

        return await self._send_webhook({"embeds": [embed]})
    
    async def send_status_alert(
        self,
        status: str,
        symbol: str,
        current_price: Optional[float] = None,
        total_value: Optional[float] = None,
        trades_count: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> bool:
        """Send bot status change notification.
        
        Args:
            status: New status (started, stopped, paused, resumed, etc.)
            symbol: Trading pair
            current_price: Current market price
            total_value: Portfolio total value
            trades_count: Number of trades
            reason: Reason for status change
            
        Returns:
            True if sent successfully
        """
        status_config = {
            "started": ("🚀 Bot Started", self.COLOR_SUCCESS),
            "stopped": ("🛑 Bot Stopped", self.COLOR_ERROR),
            "paused": ("⏸️ Bot Paused", self.COLOR_WARNING),
            "resumed": ("▶️ Bot Resumed", self.COLOR_SUCCESS),
            "waiting": ("⏳ Waiting for Entry", self.COLOR_INFO),
            "trading": ("📈 Trading Active", self.COLOR_SUCCESS),
            "emergency": ("🚨 Emergency Stop", self.COLOR_ERROR),
        }
        
        title, color = status_config.get(status.lower(), (f"📊 Status: {status}", self.COLOR_INFO))
        
        fields = [{"name": "Symbol", "value": symbol, "inline": True}]
        
        if current_price is not None:
            fields.append({"name": "Price", "value": f"${current_price:,.2f}", "inline": True})

        if total_value is not None:
            fields.append({"name": "Portfolio", "value": f"${total_value:,.2f}", "inline": True})
        
        if trades_count is not None:
            fields.append({"name": "Trades", "value": str(trades_count), "inline": True})
        
        if reason:
            fields.append({"name": "Reason", "value": reason, "inline": False})
        
        embed = {
            "title": title,
            "color": color,
            "fields": fields,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": "Trading Bot"},
        }
        
        return await self._send_webhook({"embeds": [embed]})
    
    async def send_error_alert(
        self,
        error: str,
        context: Optional[str] = None,
        traceback: Optional[str] = None,
    ) -> bool:
        """Send error notification.
        
        Args:
            error: Error message
            context: Where the error occurred
            traceback: Stack trace (truncated)
            
        Returns:
            True if sent successfully
        """
        fields = [{"name": "Error", "value": f"```{error[:1000]}```", "inline": False}]
        
        if context:
            fields.insert(0, {"name": "Context", "value": context, "inline": False})
        
        if traceback:
            # Truncate traceback to fit Discord limit
            tb = traceback[:1000] + "..." if len(traceback) > 1000 else traceback
            fields.append({"name": "Traceback", "value": f"```python\n{tb}```", "inline": False})
        
        embed = {
            "title": "🚨 Error Alert",
            "color": self.COLOR_ERROR,
            "fields": fields,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": "Trading Bot"},
        }
        
        return await self._send_webhook({"embeds": [embed]})
    
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
        """Send daily trading summary.

        Args:
            symbol: Trading pair
            start_balance: Initial balance (lifetime reference)
            end_balance: Balance at end of day
            total_trades: Number of trades
            winning_trades: Number of winning trades
            losing_trades: Number of losing trades
            total_pnl: Lifetime PnL
            max_drawdown: Maximum drawdown percentage
            best_trade: Best trade PnL
            worst_trade: Worst trade PnL
            trades_list: List of trades
            current_balance: Current portfolio value
            today_pnl: Today-only profit/loss

        Returns:
            True if sent successfully
        """
        pnl_pct = ((end_balance - start_balance) / start_balance) * 100 if start_balance > 0 else 0
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

        color = self.COLOR_PROFIT if total_pnl >= 0 else self.COLOR_LOSS

        fields = [
            {"name": "Symbol", "value": symbol, "inline": True},
            {"name": "Total Trades", "value": str(total_trades), "inline": True},
            {"name": "Win Rate", "value": f"{win_rate:.1f}%", "inline": True},
        ]

        if current_balance is not None:
            fields.append({"name": "💰 Current Balance", "value": f"${current_balance:,.2f}", "inline": True})

        if today_pnl is not None:
            today_emoji = "📈" if today_pnl >= 0 else "📉"
            today_pnl_text = f"{today_emoji} ${today_pnl:+,.2f}"
            starting = current_balance - today_pnl if current_balance is not None else 0
            if starting > 0:
                today_pct = (today_pnl / starting) * 100
                today_pnl_text += f" ({today_pct:+.2f}%)"
            fields.append({"name": "Today PnL", "value": today_pnl_text, "inline": True})

        fields.extend([
            {"name": "Initial Balance", "value": f"${start_balance:,.2f}", "inline": True},
            {"name": "End Balance", "value": f"${end_balance:,.2f}", "inline": True},
            {"name": "Lifetime PnL", "value": f"${total_pnl:+,.2f} ({pnl_pct:+.2f}%)", "inline": True},
            {"name": "Winning", "value": f"🟢 {winning_trades}", "inline": True},
            {"name": "Losing", "value": f"🔴 {losing_trades}", "inline": True},
            {"name": "Max Drawdown", "value": f"{max_drawdown:.2f}%", "inline": True},
        ])

        if best_trade is not None:
            fields.append({"name": "Best Trade", "value": f"${best_trade:+,.2f}", "inline": True})

        if worst_trade is not None:
            fields.append({"name": "Worst Trade", "value": f"${worst_trade:+,.2f}", "inline": True})

        if trades_list:
            fields.append({"name": "Trades Count", "value": str(len(trades_list)), "inline": True})

        embed = {
            "title": f"📊 Daily Summary - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
            "color": color,
            "fields": fields,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": "Trading Bot | Daily Report"},
        }
        
        return await self._send_webhook({"embeds": [embed]})
    
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
        """Send TP/SL event alert.

        Args:
            event_type: "take_profit", "stop_loss", "trailing_stop", or "break_even".
            symbol: Trading pair.
            level_price: Original grid level fill price.
            exit_price: Price at which TP/SL triggered.
            pnl: Realized PnL for this level.
            direction: "long" or "short".
            break_even_price: New SL price if break-even event.

        Returns:
            True if sent successfully.
        """
        config = {
            "take_profit": ("TP Hit!", self.COLOR_PROFIT),
            "stop_loss": ("SL Hit!", self.COLOR_LOSS),
            "trailing_stop": ("Trailing Stop Triggered!", self.COLOR_WARNING),
            "break_even": ("Break-Even Stop Moved!", self.COLOR_INFO),
        }

        title_text, color = config.get(event_type, (event_type, self.COLOR_INFO))
        pnl_emoji = "+" if pnl >= 0 else ""

        fields = [
            {"name": "Symbol", "value": symbol, "inline": True},
            {"name": "Direction", "value": direction.upper(), "inline": True},
            {"name": "Fill Price", "value": f"${level_price:,.2f}", "inline": True},
        ]

        if event_type == "break_even" and break_even_price is not None:
            fields.append({"name": "New SL", "value": f"${break_even_price:,.2f}", "inline": True})
        else:
            fields.append({"name": "Exit Price", "value": f"${exit_price:,.2f}", "inline": True})
            fields.append({"name": "PnL", "value": f"${pnl_emoji}{pnl:,.2f}", "inline": True})

        embed = {
            "title": f"{'🎯' if event_type == 'take_profit' else '🛑' if 'stop' in event_type else '🔒'} {title_text}",
            "description": f"Level ${level_price:,.2f} closed at ${exit_price:,.2f} ({pnl_emoji}${pnl:,.2f})",
            "color": color,
            "fields": fields,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": "Trading Bot | TP/SL"},
        }

        return await self._send_webhook({"embeds": [embed]})

    async def send_custom(
        self,
        title: str,
        description: str,
        color: Optional[int] = None,
        fields: Optional[list] = None,
    ) -> bool:
        """Send custom embed message.
        
        Args:
            title: Embed title
            description: Embed description
            color: Embed color (hex)
            fields: List of field dicts
            
        Returns:
            True if sent successfully
        """
        embed = {
            "title": title,
            "description": description,
            "color": color or self.COLOR_INFO,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": "Trading Bot"},
        }
        
        if fields:
            embed["fields"] = fields
        
        return await self._send_webhook({"embeds": [embed]})


# Global instance (lazy initialized)
_discord_alert: Optional[DiscordAlert] = None


def get_discord_alert() -> DiscordAlert:
    """Get or create Discord alert instance."""
    global _discord_alert
    if _discord_alert is None:
        _discord_alert = DiscordAlert()
    return _discord_alert
