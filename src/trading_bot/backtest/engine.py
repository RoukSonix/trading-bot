"""Backtesting engine for trading strategies."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import pandas as pd
from loguru import logger

from trading_bot.strategies import GridStrategy, GridConfig
from trading_bot.strategies.base import SignalType


@dataclass
class BacktestResult:
    """Backtesting results."""
    
    # Time period
    start_date: datetime
    end_date: datetime
    duration_days: float
    
    # Performance
    initial_balance: float
    final_balance: float
    total_return: float  # percentage
    
    # Trades
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    
    # Risk metrics
    max_drawdown: float
    sharpe_ratio: Optional[float] = None
    
    # Details
    trades: list = field(default_factory=list)
    equity_curve: list = field(default_factory=list)


class Backtester:
    """Backtest trading strategies on historical data."""
    
    def __init__(
        self,
        initial_balance: float = 10000.0,
        commission: float = 0.001,  # 0.1% per trade
    ):
        """Initialize backtester.
        
        Args:
            initial_balance: Starting balance in USDT
            commission: Commission rate per trade
        """
        self.initial_balance = initial_balance
        self.commission = commission
    
    def run(
        self,
        strategy: GridStrategy,
        data: pd.DataFrame,
        price_column: str = "close",
    ) -> BacktestResult:
        """Run backtest on historical data.
        
        Args:
            strategy: Strategy to test
            data: OHLCV DataFrame with datetime index
            price_column: Column to use for price
            
        Returns:
            BacktestResult with performance metrics
        """
        logger.info(f"Running backtest on {len(data)} candles...")
        
        # Initialize
        balance = self.initial_balance
        holdings = 0.0
        trades = []
        equity_curve = []
        
        # Reset strategy
        strategy.levels = []
        strategy.center_price = None
        
        # Track metrics
        peak_equity = self.initial_balance
        max_drawdown = 0.0
        
        for i, (timestamp, row) in enumerate(data.iterrows()):
            price = row[price_column]
            
            # Calculate current equity
            equity = balance + (holdings * price)
            equity_curve.append({
                "timestamp": timestamp,
                "equity": equity,
                "price": price,
                "holdings": holdings,
                "balance": balance,
            })
            
            # Track drawdown
            if equity > peak_equity:
                peak_equity = equity
            drawdown = (peak_equity - equity) / peak_equity
            if drawdown > max_drawdown:
                max_drawdown = drawdown
            
            # Get signals
            signals = strategy.calculate_signals(data.iloc[:i+1], price)
            
            for signal in signals:
                cost = signal.price * signal.amount
                commission_cost = cost * self.commission
                
                if signal.type == SignalType.BUY:
                    total_cost = cost + commission_cost
                    if balance >= total_cost:
                        balance -= total_cost
                        holdings += signal.amount
                        trades.append({
                            "timestamp": timestamp,
                            "type": "BUY",
                            "price": signal.price,
                            "amount": signal.amount,
                            "cost": total_cost,
                            "balance": balance,
                            "holdings": holdings,
                        })
                else:  # SELL
                    if holdings >= signal.amount:
                        revenue = cost - commission_cost
                        balance += revenue
                        holdings -= signal.amount
                        trades.append({
                            "timestamp": timestamp,
                            "type": "SELL",
                            "price": signal.price,
                            "amount": signal.amount,
                            "revenue": revenue,
                            "balance": balance,
                            "holdings": holdings,
                        })
        
        # Final equity
        final_price = data[price_column].iloc[-1]
        final_balance = balance + (holdings * final_price)
        
        # Calculate metrics
        total_return = ((final_balance - self.initial_balance) / self.initial_balance) * 100
        
        # Win/loss analysis (simplified - based on round trips)
        winning = sum(1 for t in trades if t["type"] == "SELL" and t.get("revenue", 0) > t.get("cost", 0))
        losing = len([t for t in trades if t["type"] == "SELL"]) - winning
        total_sells = winning + losing
        win_rate = (winning / total_sells * 100) if total_sells > 0 else 0
        
        # Duration
        start_date = data.index[0]
        end_date = data.index[-1]
        duration = (end_date - start_date).total_seconds() / 86400  # days
        
        result = BacktestResult(
            start_date=start_date,
            end_date=end_date,
            duration_days=duration,
            initial_balance=self.initial_balance,
            final_balance=final_balance,
            total_return=total_return,
            total_trades=len(trades),
            winning_trades=winning,
            losing_trades=losing,
            win_rate=win_rate,
            max_drawdown=max_drawdown * 100,
            trades=trades,
            equity_curve=equity_curve,
        )
        
        self._print_result(result)
        
        return result
    
    def _print_result(self, result: BacktestResult):
        """Print backtest results."""
        logger.info("")
        logger.info("=" * 50)
        logger.info("📊 BACKTEST RESULTS")
        logger.info("=" * 50)
        logger.info(f"Period: {result.start_date} to {result.end_date}")
        logger.info(f"Duration: {result.duration_days:.1f} days")
        logger.info("")
        logger.info(f"Initial Balance: ${result.initial_balance:,.2f}")
        logger.info(f"Final Balance: ${result.final_balance:,.2f}")
        logger.info(f"Total Return: {result.total_return:+.2f}%")
        logger.info("")
        logger.info(f"Total Trades: {result.total_trades}")
        logger.info(f"Win Rate: {result.win_rate:.1f}%")
        logger.info(f"Max Drawdown: {result.max_drawdown:.2f}%")
        logger.info("=" * 50)
