"""Telegram alerts for trading bot."""

import asyncio
from typing import Optional

from loguru import logger
from telegram import Bot
from telegram.error import TelegramError

from trading_bot.config import settings


class TelegramAlerter:
    """Send alerts via Telegram."""
    
    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None):
        """Initialize Telegram alerter.
        
        Args:
            token: Telegram bot token
            chat_id: Chat ID to send messages to
        """
        self.token = token or getattr(settings, 'telegram_bot_token', None)
        self.chat_id = chat_id or getattr(settings, 'telegram_chat_id', None)
        self.bot: Optional[Bot] = None
        self.enabled = False
        
        if self.token and self.chat_id:
            self.bot = Bot(token=self.token)
            self.enabled = True
            logger.info("Telegram alerts enabled")
        else:
            logger.warning("Telegram alerts disabled (no token/chat_id)")
    
    async def send(self, message: str, parse_mode: str = "HTML") -> bool:
        """Send a message.
        
        Args:
            message: Message text
            parse_mode: HTML or Markdown
            
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            logger.debug(f"Telegram (disabled): {message}")
            return False
        
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=parse_mode,
            )
            return True
        except TelegramError as e:
            logger.error(f"Telegram error: {e}")
            return False
    
    async def send_trade(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        pnl: Optional[float] = None,
    ):
        """Send trade notification.
        
        Args:
            symbol: Trading pair
            side: BUY or SELL
            amount: Trade amount
            price: Trade price
            pnl: Profit/loss if closing position
        """
        emoji = "🟢" if side.upper() == "BUY" else "🔴"
        
        msg = f"{emoji} <b>{side.upper()}</b> {symbol}\n"
        msg += f"Amount: {amount:.6f}\n"
        msg += f"Price: ${price:,.2f}"
        
        if pnl is not None:
            pnl_emoji = "📈" if pnl >= 0 else "📉"
            msg += f"\n{pnl_emoji} PnL: ${pnl:+,.2f}"
        
        await self.send(msg)
    
    async def send_status(
        self,
        symbol: str,
        price: float,
        holdings: float,
        balance: float,
        total_value: float,
        trades_count: int,
    ):
        """Send status update.
        
        Args:
            symbol: Trading pair
            price: Current price
            holdings: Crypto holdings
            balance: USDT balance
            total_value: Total portfolio value
            trades_count: Number of trades
        """
        profit = total_value - 10000  # Assuming 10k start
        profit_pct = (profit / 10000) * 100
        
        msg = f"📊 <b>Status Update</b>\n\n"
        msg += f"Symbol: {symbol}\n"
        msg += f"Price: ${price:,.2f}\n"
        msg += f"Holdings: {holdings:.6f}\n"
        msg += f"Balance: ${balance:,.2f}\n"
        msg += f"Total: ${total_value:,.2f}\n"
        msg += f"Trades: {trades_count}\n"
        msg += f"P&L: ${profit:+,.2f} ({profit_pct:+.2f}%)"
        
        await self.send(msg)
    
    async def send_alert(self, title: str, message: str, level: str = "info"):
        """Send general alert.
        
        Args:
            title: Alert title
            message: Alert message
            level: info/warning/error
        """
        emoji = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "🚨",
        }.get(level, "📢")
        
        msg = f"{emoji} <b>{title}</b>\n\n{message}"
        await self.send(msg)
    
    async def send_ai_decision(self, action: str, reason: str, confidence: int):
        """Send AI decision notification.
        
        Args:
            action: AI action (CONTINUE/ADJUST/STOP)
            reason: AI reasoning
            confidence: Confidence percentage
        """
        emoji = {
            "CONTINUE": "✅",
            "ADJUST": "🔧",
            "PAUSE": "⏸️",
            "STOP": "🛑",
        }.get(action, "🤖")
        
        msg = f"{emoji} <b>AI Decision: {action}</b>\n\n"
        msg += f"Confidence: {confidence}%\n"
        msg += f"Reason: {reason}"
        
        await self.send(msg)


# Global instance
telegram = TelegramAlerter()
