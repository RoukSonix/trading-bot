"""Backtesting engine for trading strategies."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict
import json
from pathlib import Path

import pandas as pd
from loguru import logger

from binance_bot.strategies import GridStrategy, GridConfig
from binance_bot.strategies.base import SignalType
from shared.risk import RiskMetrics


@dataclass
class BacktestResult:
    """Backtesting results."""
    
    # Config
    config_name: str = "default"
    
    # Time period
    start_date: datetime = None
    end_date: datetime = None
    duration_days: float = 0.0
    
    # Performance
    initial_balance: float = 10000.0
    final_balance: float = 10000.0
    total_return: float = 0.0  # percentage
    
    # Trades
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    
    # Risk metrics
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    
    # Details
    trades: list = field(default_factory=list)
    equity_curve: list = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "config_name": self.config_name,
            "start_date": str(self.start_date),
            "end_date": str(self.end_date),
            "duration_days": self.duration_days,
            "initial_balance": self.initial_balance,
            "final_balance": self.final_balance,
            "total_return": self.total_return,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "max_drawdown": self.max_drawdown,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "profit_factor": self.profit_factor,
            "expectancy": self.expectancy,
        }


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
        self.risk_metrics = RiskMetrics(initial_balance=initial_balance)
    
    def run(
        self,
        strategy: GridStrategy,
        data: pd.DataFrame,
        price_column: str = "close",
        config_name: str = "default",
    ) -> BacktestResult:
        """Run backtest on historical data.
        
        Args:
            strategy: Strategy to test
            data: OHLCV DataFrame with datetime index
            price_column: Column to use for price
            config_name: Name for this config (for comparison)
            
        Returns:
            BacktestResult with performance metrics
        """
        logger.info(f"Running backtest '{config_name}' on {len(data)} candles...")
        
        # Initialize
        balance = self.initial_balance
        holdings = 0.0
        trades = []
        equity_curve = []
        
        # Reset strategy and metrics
        strategy.levels = []
        strategy.center_price = None
        self.risk_metrics = RiskMetrics(initial_balance=self.initial_balance)
        
        # Track metrics
        peak_equity = self.initial_balance
        max_drawdown = 0.0
        last_buy_price = 0.0
        
        for i, (timestamp, row) in enumerate(data.iterrows()):
            price = row[price_column]
            
            # Calculate current equity
            equity = balance + (holdings * price)
            equity_curve.append({
                "timestamp": str(timestamp),
                "equity": equity,
                "price": price,
                "holdings": holdings,
                "balance": balance,
            })
            self.risk_metrics.update_equity(equity)
            
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
                        last_buy_price = signal.price
                        trades.append({
                            "timestamp": str(timestamp),
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
                        
                        # Record trade in risk metrics
                        if last_buy_price > 0:
                            self.risk_metrics.record_trade(
                                symbol=strategy.symbol,
                                side="buy",
                                entry_price=last_buy_price,
                                exit_price=signal.price,
                                amount=signal.amount,
                            )
                        
                        trades.append({
                            "timestamp": str(timestamp),
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
        
        # Win/loss analysis
        winning = len(self.risk_metrics.winning_trades)
        losing = len(self.risk_metrics.losing_trades)
        total_completed = winning + losing
        win_rate = (winning / total_completed * 100) if total_completed > 0 else 0
        
        # Duration
        start_date = data.index[0]
        end_date = data.index[-1]
        duration = (end_date - start_date).total_seconds() / 86400  # days
        
        result = BacktestResult(
            config_name=config_name,
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
            sharpe_ratio=self.risk_metrics.sharpe_ratio(int(duration)),
            sortino_ratio=self.risk_metrics.sortino_ratio(int(duration)),
            profit_factor=self.risk_metrics.profit_factor,
            expectancy=self.risk_metrics.expectancy,
            trades=trades,
            equity_curve=equity_curve,
        )
        
        self._print_result(result)
        
        return result
    
    def run_comparison(
        self,
        configs: List[Dict],
        data: pd.DataFrame,
        price_column: str = "close",
    ) -> List[BacktestResult]:
        """Run multiple backtests with different configs for comparison.
        
        Args:
            configs: List of dicts with 'name' and GridConfig params
            data: OHLCV DataFrame
            price_column: Column for price
            
        Returns:
            List of BacktestResult sorted by total_return
        """
        results = []
        
        for config in configs:
            name = config.get("name", f"config_{len(results)}")
            grid_config = GridConfig(
                grid_levels=config.get("levels", 10),
                grid_spacing_pct=config.get("spacing", 1.0),
                amount_per_level=config.get("amount", 0.001),
            )
            strategy = GridStrategy(symbol="BTC/USDT", config=grid_config)
            
            result = self.run(
                strategy=strategy,
                data=data,
                price_column=price_column,
                config_name=name,
            )
            results.append(result)
        
        # Sort by return
        results.sort(key=lambda r: r.total_return, reverse=True)
        
        # Print comparison
        self._print_comparison(results)
        
        return results
    
    def _print_result(self, result: BacktestResult):
        """Print backtest results."""
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"📊 BACKTEST RESULTS: {result.config_name}")
        logger.info("=" * 60)
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
        logger.info("")
        logger.info(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
        logger.info(f"Sortino Ratio: {result.sortino_ratio:.2f}")
        logger.info(f"Profit Factor: {result.profit_factor:.2f}")
        logger.info(f"Expectancy: ${result.expectancy:.2f}")
        logger.info("=" * 60)
    
    def _print_comparison(self, results: List[BacktestResult]):
        """Print comparison table."""
        logger.info("")
        logger.info("=" * 80)
        logger.info("📈 STRATEGY COMPARISON (sorted by return)")
        logger.info("=" * 80)
        logger.info(f"{'Config':<20} {'Return':>10} {'Win Rate':>10} {'Max DD':>10} {'Sharpe':>10} {'Trades':>8}")
        logger.info("-" * 80)
        
        for r in results:
            logger.info(
                f"{r.config_name:<20} "
                f"{r.total_return:>+9.2f}% "
                f"{r.win_rate:>9.1f}% "
                f"{r.max_drawdown:>9.2f}% "
                f"{r.sharpe_ratio:>10.2f} "
                f"{r.total_trades:>8}"
            )
        
        logger.info("=" * 80)
    
    def save_results(self, results: List[BacktestResult], filepath: str):
        """Save results to JSON file."""
        data = [r.to_dict() for r in results]
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Results saved to {filepath}")
