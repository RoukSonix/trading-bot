"""Risk metrics and dashboard."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional
import statistics
from loguru import logger


@dataclass
class TradeRecord:
    """Single trade record for metrics calculation."""
    timestamp: datetime
    symbol: str
    side: str  # buy/sell
    entry_price: float
    exit_price: float
    amount: float
    pnl: float
    pnl_pct: float
    duration: timedelta = timedelta(0)


@dataclass
class RiskMetrics:
    """
    Risk metrics calculator and dashboard.
    
    Calculates:
    - Sharpe Ratio
    - Sortino Ratio
    - Max Drawdown
    - Win Rate
    - Profit Factor
    - Average Win/Loss
    - Risk-adjusted returns
    """
    
    trades: List[TradeRecord] = field(default_factory=list)
    equity_curve: List[tuple] = field(default_factory=list)  # (timestamp, balance)
    initial_balance: float = 10000.0
    risk_free_rate: float = 0.04  # 4% annual risk-free rate
    
    def record_trade(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        exit_price: float,
        amount: float,
        entry_time: Optional[datetime] = None,
        exit_time: Optional[datetime] = None,
    ):
        """Record a completed trade."""
        pnl = (exit_price - entry_price) * amount if side == "buy" else (entry_price - exit_price) * amount
        pnl_pct = (exit_price - entry_price) / entry_price if side == "buy" else (entry_price - exit_price) / entry_price
        
        duration = (exit_time - entry_time) if entry_time and exit_time else timedelta(0)
        
        trade = TradeRecord(
            timestamp=exit_time or datetime.now(),
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            exit_price=exit_price,
            amount=amount,
            pnl=pnl,
            pnl_pct=pnl_pct,
            duration=duration,
        )
        self.trades.append(trade)
    
    def update_equity(self, balance: float):
        """Update equity curve."""
        self.equity_curve.append((datetime.now(), balance))
    
    @property
    def total_trades(self) -> int:
        """Total number of trades."""
        return len(self.trades)
    
    @property
    def winning_trades(self) -> List[TradeRecord]:
        """Get all winning trades."""
        return [t for t in self.trades if t.pnl > 0]
    
    @property
    def losing_trades(self) -> List[TradeRecord]:
        """Get all losing trades."""
        return [t for t in self.trades if t.pnl < 0]
    
    @property
    def win_rate(self) -> float:
        """Calculate win rate."""
        if not self.trades:
            return 0.0
        return len(self.winning_trades) / len(self.trades)
    
    @property
    def total_pnl(self) -> float:
        """Total PnL."""
        return sum(t.pnl for t in self.trades)
    
    @property
    def average_win(self) -> float:
        """Average winning trade."""
        wins = self.winning_trades
        if not wins:
            return 0.0
        return statistics.mean(t.pnl for t in wins)
    
    @property
    def average_loss(self) -> float:
        """Average losing trade."""
        losses = self.losing_trades
        if not losses:
            return 0.0
        return statistics.mean(t.pnl for t in losses)
    
    @property
    def profit_factor(self) -> float:
        """
        Profit Factor = Gross Profit / Gross Loss
        > 1.5 is good, > 2.0 is excellent
        """
        gross_profit = sum(t.pnl for t in self.winning_trades)
        gross_loss = abs(sum(t.pnl for t in self.losing_trades))
        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0.0
        return gross_profit / gross_loss
    
    @property
    def max_drawdown(self) -> float:
        """
        Maximum drawdown from equity curve.
        """
        if len(self.equity_curve) < 2:
            return 0.0
        
        balances = [b for _, b in self.equity_curve]
        peak = balances[0]
        max_dd = 0.0
        
        for balance in balances:
            if balance > peak:
                peak = balance
            dd = (peak - balance) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
        
        return max_dd
    
    @property
    def max_drawdown_amount(self) -> float:
        """Maximum drawdown in currency."""
        if len(self.equity_curve) < 2:
            return 0.0
        
        balances = [b for _, b in self.equity_curve]
        peak = balances[0]
        max_dd = 0.0
        
        for balance in balances:
            if balance > peak:
                peak = balance
            dd = peak - balance
            max_dd = max(max_dd, dd)
        
        return max_dd
    
    def sharpe_ratio(self, period_days: int = 365) -> float:
        """
        Calculate Sharpe Ratio.
        
        Sharpe = (Return - Risk-Free Rate) / Std Dev of Returns
        > 1.0 is acceptable, > 2.0 is good, > 3.0 is excellent
        """
        if len(self.trades) < 2:
            return 0.0
        
        returns = [t.pnl_pct for t in self.trades]
        
        avg_return = statistics.mean(returns)
        std_return = statistics.stdev(returns)
        
        if std_return == 0:
            return 0.0
        
        # Annualize (assuming 252 trading days)
        trades_per_year = len(self.trades) * (365 / period_days) if period_days > 0 else len(self.trades)
        annualized_return = avg_return * trades_per_year
        annualized_std = std_return * (trades_per_year ** 0.5)
        
        sharpe = (annualized_return - self.risk_free_rate) / annualized_std
        return sharpe
    
    def sortino_ratio(self, period_days: int = 365) -> float:
        """
        Calculate Sortino Ratio.
        
        Like Sharpe but only considers downside volatility.
        Better for strategies with asymmetric returns.
        """
        if len(self.trades) < 2:
            return 0.0
        
        returns = [t.pnl_pct for t in self.trades]
        negative_returns = [r for r in returns if r < 0]
        
        if not negative_returns:
            return float('inf')
        
        avg_return = statistics.mean(returns)
        downside_std = statistics.stdev(negative_returns) if len(negative_returns) > 1 else 0
        
        if downside_std == 0:
            return float('inf') if avg_return > 0 else 0.0
        
        # Annualize
        trades_per_year = len(self.trades) * (365 / period_days) if period_days > 0 else len(self.trades)
        annualized_return = avg_return * trades_per_year
        annualized_downside = downside_std * (trades_per_year ** 0.5)
        
        sortino = (annualized_return - self.risk_free_rate) / annualized_downside
        return sortino
    
    def calmar_ratio(self) -> float:
        """
        Calmar Ratio = Annual Return / Max Drawdown
        Measures risk-adjusted performance considering worst drawdown.
        """
        max_dd = self.max_drawdown
        if max_dd == 0:
            return 0.0
        
        if not self.equity_curve:
            return 0.0
        
        initial = self.equity_curve[0][1]
        final = self.equity_curve[-1][1]
        
        # Simple return
        total_return = (final - initial) / initial if initial > 0 else 0
        
        return total_return / max_dd if max_dd > 0 else 0
    
    @property
    def expectancy(self) -> float:
        """
        Trade expectancy (expected value per trade).
        
        Expectancy = (Win Rate × Avg Win) - (Loss Rate × Avg Loss)
        """
        if not self.trades:
            return 0.0
        
        win_rate = self.win_rate
        loss_rate = 1 - win_rate
        
        avg_win = self.average_win
        avg_loss = abs(self.average_loss)
        
        return (win_rate * avg_win) - (loss_rate * avg_loss)
    
    @property
    def risk_reward_ratio(self) -> float:
        """Average risk/reward ratio."""
        avg_loss = abs(self.average_loss)
        if avg_loss == 0:
            return 0.0
        return self.average_win / avg_loss
    
    def get_summary(self) -> dict:
        """Get comprehensive metrics summary."""
        return {
            # Basic stats
            "total_trades": self.total_trades,
            "winning_trades": len(self.winning_trades),
            "losing_trades": len(self.losing_trades),
            "win_rate": f"{self.win_rate*100:.1f}%",
            
            # PnL
            "total_pnl": f"${self.total_pnl:,.2f}",
            "average_win": f"${self.average_win:,.2f}",
            "average_loss": f"${self.average_loss:,.2f}",
            
            # Risk metrics
            "profit_factor": f"{self.profit_factor:.2f}",
            "max_drawdown": f"{self.max_drawdown*100:.2f}%",
            "max_drawdown_amount": f"${self.max_drawdown_amount:,.2f}",
            
            # Risk-adjusted returns
            "sharpe_ratio": f"{self.sharpe_ratio():.2f}",
            "sortino_ratio": f"{self.sortino_ratio():.2f}",
            "calmar_ratio": f"{self.calmar_ratio():.2f}",
            
            # Trade quality
            "expectancy": f"${self.expectancy:,.2f}",
            "risk_reward": f"{self.risk_reward_ratio:.2f}",
        }
    
    def print_dashboard(self):
        """Print risk metrics dashboard to console."""
        summary = self.get_summary()
        
        logger.info("=" * 60)
        logger.info("📊 RISK METRICS DASHBOARD")
        logger.info("=" * 60)
        
        logger.info("\n📈 TRADING STATISTICS")
        logger.info(f"  Total Trades:     {summary['total_trades']}")
        logger.info(f"  Win Rate:         {summary['win_rate']}")
        logger.info(f"  Winning Trades:   {summary['winning_trades']}")
        logger.info(f"  Losing Trades:    {summary['losing_trades']}")
        
        logger.info("\n💰 PROFIT & LOSS")
        logger.info(f"  Total PnL:        {summary['total_pnl']}")
        logger.info(f"  Average Win:      {summary['average_win']}")
        logger.info(f"  Average Loss:     {summary['average_loss']}")
        logger.info(f"  Profit Factor:    {summary['profit_factor']}")
        
        logger.info("\n⚠️ RISK METRICS")
        logger.info(f"  Max Drawdown:     {summary['max_drawdown']}")
        logger.info(f"  Max DD Amount:    {summary['max_drawdown_amount']}")
        
        logger.info("\n📉 RISK-ADJUSTED RETURNS")
        logger.info(f"  Sharpe Ratio:     {summary['sharpe_ratio']}")
        logger.info(f"  Sortino Ratio:    {summary['sortino_ratio']}")
        logger.info(f"  Calmar Ratio:     {summary['calmar_ratio']}")
        
        logger.info("\n🎯 TRADE QUALITY")
        logger.info(f"  Expectancy:       {summary['expectancy']}")
        logger.info(f"  Risk/Reward:      {summary['risk_reward']}")
        
        logger.info("=" * 60)
