"""Email alerts for trading bot using aiosmtplib."""

import os
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

import aiosmtplib
from loguru import logger


class EmailAlert:
    """Send alerts via email using SMTP."""
    
    def __init__(
        self,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_user: Optional[str] = None,
        smtp_pass: Optional[str] = None,
        alert_email: Optional[str] = None,
    ):
        """Initialize email alerter.
        
        Args:
            smtp_host: SMTP server host
            smtp_port: SMTP server port
            smtp_user: SMTP username
            smtp_pass: SMTP password
            alert_email: Recipient email address
        """
        self.smtp_host = smtp_host or os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = smtp_port or int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = smtp_user or os.getenv("SMTP_USER", "")
        self.smtp_pass = smtp_pass or os.getenv("SMTP_PASS", "")
        self.alert_email = alert_email or os.getenv("ALERT_EMAIL", "")
        
        self.enabled = all([self.smtp_user, self.smtp_pass, self.alert_email])
        
        if self.enabled:
            logger.info("Email alerts enabled")
        else:
            logger.debug("Email alerts disabled (missing SMTP config)")
    
    async def _send_email(
        self,
        subject: str,
        body: str,
        html: bool = False,
    ) -> bool:
        """Send email via SMTP.
        
        Args:
            subject: Email subject
            body: Email body
            html: If True, send as HTML
            
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            logger.debug(f"Email (disabled): {subject}")
            return False
        
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[Trading Bot] {subject}"
            msg["From"] = self.smtp_user
            msg["To"] = self.alert_email
            
            content_type = "html" if html else "plain"
            msg.attach(MIMEText(body, content_type))
            
            await aiosmtplib.send(
                msg,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_user,
                password=self.smtp_pass,
                start_tls=True,
                timeout=30,
            )
            
            logger.debug(f"Email sent: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Email error: {e}")
            return False
    
    async def send_alert(self, subject: str, body: str) -> bool:
        """Send generic alert email.
        
        Args:
            subject: Email subject
            body: Email body (plain text)
            
        Returns:
            True if sent successfully
        """
        return await self._send_email(subject, body, html=False)
    
    async def send_daily_report(
        self,
        symbol: str,
        start_balance: float,
        end_balance: float,
        total_trades: int,
        winning_trades: int,
        losing_trades: int,
        total_pnl: float,
        max_drawdown: float,
        trades_list: Optional[list] = None,
        current_balance: Optional[float] = None,
        today_pnl: Optional[float] = None,
    ) -> bool:
        """Send daily HTML report.
        
        Args:
            symbol: Trading pair
            start_balance: Balance at start
            end_balance: Balance at end
            total_trades: Number of trades
            winning_trades: Winning trades count
            losing_trades: Losing trades count
            total_pnl: Total PnL
            max_drawdown: Max drawdown %
            trades_list: Optional list of trade details
            
        Returns:
            True if sent successfully
        """
        pnl_pct = ((end_balance - start_balance) / start_balance) * 100 if start_balance > 0 else 0
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        pnl_color = "#00AA00" if total_pnl >= 0 else "#FF0000"
        
        # Build optional today PnL section for email
        today_pnl_html = ""
        if current_balance is not None or today_pnl is not None:
            today_pnl_html = ""
            if current_balance is not None:
                today_pnl_html += f"""
            <div class="stat-box">
                <div class="stat-label">Current Balance</div>
                <div class="stat-value">${current_balance:,.2f}</div>
            </div>"""
            if today_pnl is not None:
                today_pnl_color = "#00AA00" if today_pnl >= 0 else "#FF0000"
                today_pnl_pct_text = ""
                starting = (current_balance - today_pnl) if current_balance is not None else 0
                if starting > 0:
                    today_pnl_pct_text = f" ({today_pnl / starting * 100:+.2f}%)"
                today_pnl_html += f"""
            <div class="stat-box">
                <div class="stat-label">Today PnL</div>
                <div class="stat-value" style="color: {today_pnl_color}">${today_pnl:+,.2f}{today_pnl_pct_text}</div>
            </div>"""

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 600px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 2px solid #0066cc; padding-bottom: 10px; }}
        .stat-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin: 20px 0; }}
        .stat-box {{ background: #f8f9fa; padding: 15px; border-radius: 4px; text-align: center; }}
        .stat-label {{ color: #666; font-size: 12px; text-transform: uppercase; }}
        .stat-value {{ font-size: 24px; font-weight: bold; color: #333; }}
        .pnl {{ color: {pnl_color}; }}
        .footer {{ color: #999; font-size: 12px; margin-top: 20px; text-align: center; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #f8f9fa; }}
        .buy {{ color: #00AA00; }}
        .sell {{ color: #FF0000; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Daily Trading Report</h1>
        <p><strong>Date:</strong> {datetime.now(timezone.utc).strftime('%Y-%m-%d')}</p>
        <p><strong>Symbol:</strong> {symbol}</p>

        <div class="stat-grid">{today_pnl_html}
            <div class="stat-box">
                <div class="stat-label">Initial Balance</div>
                <div class="stat-value">${start_balance:,.2f}</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">End Balance</div>
                <div class="stat-value">${end_balance:,.2f}</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Lifetime PnL</div>
                <div class="stat-value pnl">${total_pnl:+,.2f} ({pnl_pct:+.2f}%)</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Max Drawdown</div>
                <div class="stat-value">{max_drawdown:.2f}%</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Total Trades</div>
                <div class="stat-value">{total_trades}</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Win Rate</div>
                <div class="stat-value">{win_rate:.1f}%</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Winning</div>
                <div class="stat-value buy">🟢 {winning_trades}</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Losing</div>
                <div class="stat-value sell">🔴 {losing_trades}</div>
            </div>
        </div>
"""
        
        if trades_list:
            html += """
        <h2>Recent Trades</h2>
        <table>
            <tr>
                <th>Time</th>
                <th>Side</th>
                <th>Price</th>
                <th>Amount</th>
                <th>PnL</th>
            </tr>
"""
            for trade in trades_list[-10:]:  # Last 10 trades
                side_class = "buy" if trade.get("side", "").upper() == "BUY" else "sell"
                pnl = trade.get("pnl", 0)
                pnl_display = f"${pnl:+.2f}" if pnl else "-"
                html += f"""
            <tr>
                <td>{trade.get('time', '-')}</td>
                <td class="{side_class}">{trade.get('side', '-').upper()}</td>
                <td>${trade.get('price', 0):,.2f}</td>
                <td>{trade.get('amount', 0):.6f}</td>
                <td class="{'buy' if pnl >= 0 else 'sell'}">{pnl_display}</td>
            </tr>
"""
            html += "</table>"
        
        html += """
        <div class="footer">
            <p>Trading Bot - Automated Report</p>
        </div>
    </div>
</body>
</html>
"""
        
        subject = f"Daily Report - {datetime.now(timezone.utc).strftime('%Y-%m-%d')} | PnL: ${total_pnl:+,.2f}"
        return await self._send_email(subject, html, html=True)
    
    async def send_emergency_alert(self, message: str, details: Optional[str] = None) -> bool:
        """Send high-priority emergency alert.
        
        Args:
            message: Emergency message
            details: Additional details
            
        Returns:
            True if sent successfully
        """
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #fff5f5; }}
        .container {{ max-width: 600px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; border: 3px solid #FF0000; }}
        h1 {{ color: #FF0000; }}
        .message {{ font-size: 18px; padding: 20px; background: #fff5f5; border-radius: 4px; }}
        .details {{ margin-top: 20px; padding: 15px; background: #f8f9fa; font-family: monospace; white-space: pre-wrap; }}
        .timestamp {{ color: #999; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🚨 EMERGENCY ALERT</h1>
        <div class="message">{message}</div>
        {"<div class='details'>" + details + "</div>" if details else ""}
        <p class="timestamp">Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
    </div>
</body>
</html>
"""
        
        return await self._send_email(f"🚨 EMERGENCY: {message}", html, html=True)


# Global instance (lazy initialized)
_email_alert: Optional[EmailAlert] = None


def get_email_alert() -> EmailAlert:
    """Get or create email alert instance."""
    global _email_alert
    if _email_alert is None:
        _email_alert = EmailAlert()
    return _email_alert
