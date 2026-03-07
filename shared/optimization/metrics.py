"""Performance metrics for hyperparameter optimization."""

from typing import List

import numpy as np


class PerformanceMetrics:
    """Calculate trading performance metrics from backtest results."""

    @staticmethod
    def sharpe_ratio(returns: List[float], risk_free_rate: float = 0.0) -> float:
        """Annualized Sharpe Ratio.

        Args:
            returns: List of periodic returns (e.g. per-trade or daily).
            risk_free_rate: Annual risk-free rate (default 0).

        Returns:
            Annualized Sharpe ratio. 0.0 if insufficient data.
        """
        if len(returns) < 2:
            return 0.0
        arr = np.array(returns, dtype=np.float64)
        std = arr.std(ddof=1)
        if std == 0:
            return 0.0
        mean = arr.mean()
        # Annualise assuming 252 trading days
        annualized_return = mean * 252
        annualized_std = std * np.sqrt(252)
        return float((annualized_return - risk_free_rate) / annualized_std)

    @staticmethod
    def sortino_ratio(returns: List[float], risk_free_rate: float = 0.0) -> float:
        """Sortino Ratio — uses downside deviation only.

        Args:
            returns: List of periodic returns.
            risk_free_rate: Annual risk-free rate (default 0).

        Returns:
            Annualized Sortino ratio. 0.0 if insufficient data.
        """
        if len(returns) < 2:
            return 0.0
        arr = np.array(returns, dtype=np.float64)
        downside = arr[arr < 0]
        if len(downside) < 1:
            return 0.0
        downside_std = downside.std(ddof=1) if len(downside) > 1 else abs(downside[0])
        if downside_std == 0:
            return 0.0
        mean = arr.mean()
        annualized_return = mean * 252
        annualized_downside = downside_std * np.sqrt(252)
        return float((annualized_return - risk_free_rate) / annualized_downside)

    @staticmethod
    def max_drawdown(equity_curve: List[float]) -> float:
        """Maximum drawdown percentage.

        Args:
            equity_curve: List of equity values over time.

        Returns:
            Max drawdown as a fraction (e.g. 0.15 = 15%).
        """
        if len(equity_curve) < 2:
            return 0.0
        arr = np.array(equity_curve, dtype=np.float64)
        peak = np.maximum.accumulate(arr)
        drawdowns = (peak - arr) / np.where(peak > 0, peak, 1.0)
        return float(drawdowns.max())

    @staticmethod
    def win_rate(trades: List[dict]) -> float:
        """Percentage of winning trades.

        Args:
            trades: List of trade dicts. A trade is a winner if it has
                    key 'pnl' > 0 OR if it's a SELL with 'revenue' > 'cost'.

        Returns:
            Win rate as fraction (0-1).
        """
        if not trades:
            return 0.0
        wins = 0
        counted = 0
        for t in trades:
            if "pnl" in t:
                counted += 1
                if t["pnl"] > 0:
                    wins += 1
            elif t.get("type") == "SELL" and "revenue" in t:
                counted += 1
                cost = t.get("cost", 0)
                if t["revenue"] > cost:
                    wins += 1
        return wins / counted if counted > 0 else 0.0

    @staticmethod
    def profit_factor(trades: List[dict]) -> float:
        """Gross profit / Gross loss.

        Args:
            trades: List of trade dicts with 'pnl' key.

        Returns:
            Profit factor. inf if no losses, 0.0 if no wins.
        """
        gross_profit = 0.0
        gross_loss = 0.0
        for t in trades:
            pnl = t.get("pnl", 0.0)
            if pnl > 0:
                gross_profit += pnl
            elif pnl < 0:
                gross_loss += abs(pnl)
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0
        return gross_profit / gross_loss

    @staticmethod
    def calmar_ratio(returns: List[float], max_dd: float) -> float:
        """Calmar Ratio = Annualized return / Max drawdown.

        Args:
            returns: List of periodic returns.
            max_dd: Maximum drawdown as fraction.

        Returns:
            Calmar ratio. 0.0 if max_dd is 0.
        """
        if max_dd == 0 or not returns:
            return 0.0
        arr = np.array(returns, dtype=np.float64)
        annualized_return = arr.mean() * 252
        return float(annualized_return / max_dd)

    @staticmethod
    def calculate_all(trades: List[dict], equity_curve: List[float]) -> dict:
        """Calculate all metrics at once.

        Args:
            trades: List of trade dicts with 'pnl' key for profit trades.
            equity_curve: List of equity values over time.

        Returns:
            Dict with all computed metrics.
        """
        # Derive returns from equity curve
        returns = []
        for i in range(1, len(equity_curve)):
            prev = equity_curve[i - 1]
            if prev != 0:
                returns.append((equity_curve[i] - prev) / prev)

        max_dd = PerformanceMetrics.max_drawdown(equity_curve)

        return {
            "sharpe_ratio": PerformanceMetrics.sharpe_ratio(returns),
            "sortino_ratio": PerformanceMetrics.sortino_ratio(returns),
            "max_drawdown": max_dd,
            "win_rate": PerformanceMetrics.win_rate(trades),
            "profit_factor": PerformanceMetrics.profit_factor(trades),
            "calmar_ratio": PerformanceMetrics.calmar_ratio(returns, max_dd),
        }
