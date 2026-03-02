"""PnL Reporting System.

Generates daily and weekly PnL reports in JSON format with metrics:
- Total PnL
- Win rate
- Average trade
- Volume statistics
- Risk metrics
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from loguru import logger

from trading_bot.core.database import get_trades, get_trades_summary, TradeLog


class PnLReporter:
    """PnL report generator.
    
    Generates comprehensive trading reports with:
    - Daily/weekly performance summaries
    - Win rate and risk metrics
    - Trade statistics
    - JSON export for analysis
    """
    
    REPORTS_DIR = Path("data/reports")
    
    def __init__(self, reports_dir: Optional[Path] = None):
        """Initialize reporter.
        
        Args:
            reports_dir: Directory for report output (default: data/reports)
        """
        self.reports_dir = reports_dir or self.REPORTS_DIR
        self.reports_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_daily_report(
        self,
        date: Optional[datetime] = None,
        symbol: str = None,
        strategy: str = None,
        save: bool = True,
    ) -> dict:
        """Generate daily PnL report.
        
        Args:
            date: Date for report (default: today)
            symbol: Filter by trading pair
            strategy: Filter by strategy
            save: Save report to file
            
        Returns:
            Dict with daily report data
        """
        if date is None:
            date = datetime.utcnow()
        
        # Calculate day boundaries (UTC)
        day_start = datetime(date.year, date.month, date.day, 0, 0, 0)
        day_end = day_start + timedelta(days=1)
        
        start_ts = int(day_start.timestamp() * 1000)
        end_ts = int(day_end.timestamp() * 1000)
        
        # Get trades for the day
        trades = get_trades(
            symbol=symbol,
            start_timestamp=start_ts,
            end_timestamp=end_ts,
            strategy=strategy,
        )
        
        # Get summary statistics
        summary = get_trades_summary(
            symbol=symbol,
            start_timestamp=start_ts,
            end_timestamp=end_ts,
            strategy=strategy,
        )
        
        # Calculate additional metrics
        report = {
            "report_type": "daily",
            "date": date.strftime("%Y-%m-%d"),
            "generated_at": datetime.utcnow().isoformat(),
            "filters": {
                "symbol": symbol,
                "strategy": strategy,
            },
            "summary": summary,
            "metrics": self._calculate_metrics(trades),
            "hourly_breakdown": self._hourly_breakdown(trades),
            "trades": [t.to_dict() for t in trades] if len(trades) <= 100 else None,
            "trade_count_note": f"{len(trades)} trades (first 100 shown)" if len(trades) > 100 else None,
        }
        
        if save:
            filename = f"daily_{date.strftime('%Y-%m-%d')}"
            if symbol:
                filename += f"_{symbol.replace('/', '_')}"
            filename += ".json"
            self._save_report(report, filename)
        
        return report
    
    def generate_weekly_report(
        self,
        week_start: Optional[datetime] = None,
        symbol: str = None,
        strategy: str = None,
        save: bool = True,
    ) -> dict:
        """Generate weekly PnL report.
        
        Args:
            week_start: Start date of week (default: current week Monday)
            symbol: Filter by trading pair
            strategy: Filter by strategy
            save: Save report to file
            
        Returns:
            Dict with weekly report data
        """
        if week_start is None:
            today = datetime.utcnow()
            # Get Monday of current week
            week_start = today - timedelta(days=today.weekday())
        
        week_start = datetime(week_start.year, week_start.month, week_start.day, 0, 0, 0)
        week_end = week_start + timedelta(days=7)
        
        start_ts = int(week_start.timestamp() * 1000)
        end_ts = int(week_end.timestamp() * 1000)
        
        # Get trades for the week
        trades = get_trades(
            symbol=symbol,
            start_timestamp=start_ts,
            end_timestamp=end_ts,
            strategy=strategy,
        )
        
        # Get summary statistics
        summary = get_trades_summary(
            symbol=symbol,
            start_timestamp=start_ts,
            end_timestamp=end_ts,
            strategy=strategy,
        )
        
        # Generate daily breakdown
        daily_data = []
        for i in range(7):
            day = week_start + timedelta(days=i)
            day_end = day + timedelta(days=1)
            day_start_ts = int(day.timestamp() * 1000)
            day_end_ts = int(day_end.timestamp() * 1000)
            
            day_summary = get_trades_summary(
                symbol=symbol,
                start_timestamp=day_start_ts,
                end_timestamp=day_end_ts,
                strategy=strategy,
            )
            
            daily_data.append({
                "date": day.strftime("%Y-%m-%d"),
                "day_of_week": day.strftime("%A"),
                "trades": day_summary["total_trades"],
                "pnl": day_summary["total_pnl"],
                "net_pnl": day_summary["net_pnl"],
                "win_rate": day_summary["win_rate"],
                "volume": day_summary["total_volume"],
            })
        
        report = {
            "report_type": "weekly",
            "week_start": week_start.strftime("%Y-%m-%d"),
            "week_end": (week_end - timedelta(days=1)).strftime("%Y-%m-%d"),
            "generated_at": datetime.utcnow().isoformat(),
            "filters": {
                "symbol": symbol,
                "strategy": strategy,
            },
            "summary": summary,
            "metrics": self._calculate_metrics(trades),
            "daily_breakdown": daily_data,
            "best_day": max(daily_data, key=lambda x: x["pnl"]) if daily_data else None,
            "worst_day": min(daily_data, key=lambda x: x["pnl"]) if daily_data else None,
        }
        
        if save:
            filename = f"weekly_{week_start.strftime('%Y-%m-%d')}"
            if symbol:
                filename += f"_{symbol.replace('/', '_')}"
            filename += ".json"
            self._save_report(report, filename)
        
        return report
    
    def _calculate_metrics(self, trades: list[TradeLog]) -> dict:
        """Calculate advanced trading metrics.
        
        Args:
            trades: List of trades
            
        Returns:
            Dict with calculated metrics
        """
        if not trades:
            return {
                "profit_factor": 0,
                "sharpe_estimate": 0,
                "max_consecutive_wins": 0,
                "max_consecutive_losses": 0,
                "avg_holding_time": None,
                "risk_reward_ratio": 0,
            }
        
        pnls = [t.pnl for t in trades]
        winning_pnls = [p for p in pnls if p > 0]
        losing_pnls = [p for p in pnls if p < 0]
        
        # Profit factor
        gross_profit = sum(winning_pnls) if winning_pnls else 0
        gross_loss = abs(sum(losing_pnls)) if losing_pnls else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0
        
        # Risk/Reward ratio
        avg_win = sum(winning_pnls) / len(winning_pnls) if winning_pnls else 0
        avg_loss = abs(sum(losing_pnls) / len(losing_pnls)) if losing_pnls else 0
        risk_reward = avg_win / avg_loss if avg_loss > 0 else float('inf') if avg_win > 0 else 0
        
        # Consecutive wins/losses
        max_wins, max_losses = 0, 0
        current_wins, current_losses = 0, 0
        
        for pnl in pnls:
            if pnl > 0:
                current_wins += 1
                current_losses = 0
                max_wins = max(max_wins, current_wins)
            elif pnl < 0:
                current_losses += 1
                current_wins = 0
                max_losses = max(max_losses, current_losses)
            else:
                current_wins = 0
                current_losses = 0
        
        # Sharpe-like estimate (simplified)
        if len(pnls) > 1:
            import statistics
            mean_return = statistics.mean(pnls)
            std_return = statistics.stdev(pnls)
            sharpe_estimate = mean_return / std_return if std_return > 0 else 0
        else:
            sharpe_estimate = 0
        
        return {
            "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else "∞",
            "sharpe_estimate": round(sharpe_estimate, 3),
            "max_consecutive_wins": max_wins,
            "max_consecutive_losses": max_losses,
            "risk_reward_ratio": round(risk_reward, 2) if risk_reward != float('inf') else "∞",
            "gross_profit": round(gross_profit, 4),
            "gross_loss": round(gross_loss, 4),
        }
    
    def _hourly_breakdown(self, trades: list[TradeLog]) -> list[dict]:
        """Break down trades by hour.
        
        Args:
            trades: List of trades
            
        Returns:
            List of hourly data
        """
        hourly = {}
        for t in trades:
            hour = t.datetime_utc.hour
            if hour not in hourly:
                hourly[hour] = {"trades": 0, "pnl": 0, "volume": 0}
            hourly[hour]["trades"] += 1
            hourly[hour]["pnl"] += t.pnl
            hourly[hour]["volume"] += t.price * t.amount
        
        return [
            {
                "hour": h,
                "hour_label": f"{h:02d}:00",
                "trades": data["trades"],
                "pnl": round(data["pnl"], 4),
                "volume": round(data["volume"], 4),
            }
            for h, data in sorted(hourly.items())
        ]
    
    def _save_report(self, report: dict, filename: str) -> Path:
        """Save report to JSON file.
        
        Args:
            report: Report data
            filename: Output filename
            
        Returns:
            Path to saved file
        """
        filepath = self.reports_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info(f"📊 Report saved: {filepath}")
        return filepath
    
    def list_reports(self, report_type: str = None) -> list[Path]:
        """List available reports.
        
        Args:
            report_type: Filter by type (daily/weekly)
            
        Returns:
            List of report file paths
        """
        pattern = "*.json"
        if report_type:
            pattern = f"{report_type}_*.json"
        
        return sorted(self.reports_dir.glob(pattern), reverse=True)


# Convenience functions
def generate_daily_report(
    date: datetime = None,
    symbol: str = None,
    strategy: str = None,
    save: bool = True,
) -> dict:
    """Generate daily PnL report (convenience function).
    
    Args:
        date: Date for report (default: today)
        symbol: Filter by trading pair
        strategy: Filter by strategy
        save: Save report to file
        
    Returns:
        Dict with daily report data
    """
    reporter = PnLReporter()
    return reporter.generate_daily_report(date, symbol, strategy, save)


def generate_weekly_report(
    week_start: datetime = None,
    symbol: str = None,
    strategy: str = None,
    save: bool = True,
) -> dict:
    """Generate weekly PnL report (convenience function).
    
    Args:
        week_start: Start date of week (default: current week Monday)
        symbol: Filter by trading pair
        strategy: Filter by strategy
        save: Save report to file
        
    Returns:
        Dict with weekly report data
    """
    reporter = PnLReporter()
    return reporter.generate_weekly_report(week_start, symbol, strategy, save)
