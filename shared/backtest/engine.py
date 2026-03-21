"""Backtesting engine for trading strategies.

Provides both the legacy Backtester (Sprint 17) and the professional-grade
BacktestEngine (Sprint 19) with anti look-ahead bias, slippage, and
comprehensive metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, TYPE_CHECKING
import json
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger

from shared.risk import RiskMetrics

if TYPE_CHECKING:
    from binance_bot.strategies import GridStrategy, GridConfig
    from binance_bot.strategies.base import SignalType


@dataclass
class BacktestResult:
    """Complete backtest results with professional-grade metrics."""

    # Config / metadata
    config_name: str = "default"
    start_date: datetime = None
    end_date: datetime = None
    duration_days: float = 0.0
    symbol: str = ""
    timeframe: str = ""
    params: dict = field(default_factory=dict)

    # Performance
    initial_balance: float = 10000.0
    final_balance: float = 10000.0
    total_return: float = 0.0  # percentage

    # Trade counts
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0

    # Risk metrics
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_duration: int = 0  # in candles

    # Trade metrics
    win_rate: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    avg_holding_period: float = 0.0  # in hours

    # Curves
    equity_curve: list = field(default_factory=list)
    drawdown_curve: list = field(default_factory=list)
    daily_returns: list = field(default_factory=list)

    # Details
    trades: list = field(default_factory=list)

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            "=" * 60,
            f"  BACKTEST RESULTS: {self.config_name}",
            "=" * 60,
            f"  Period     : {self.start_date} -> {self.end_date}",
            f"  Duration   : {self.duration_days:.1f} days",
            f"  Symbol     : {self.symbol}  Timeframe: {self.timeframe}",
            "",
            f"  Initial    : ${self.initial_balance:,.2f}",
            f"  Final      : ${self.final_balance:,.2f}",
            f"  Return     : {self.total_return:+.2f}%",
            "",
            f"  Trades     : {self.total_trades}  (W:{self.winning_trades} / L:{self.losing_trades})",
            f"  Win Rate   : {self.win_rate:.1f}%",
            f"  Profit Fct : {self.profit_factor:.2f}",
            "",
            f"  Sharpe     : {self.sharpe_ratio:.2f}",
            f"  Sortino    : {self.sortino_ratio:.2f}",
            f"  Max DD     : {self.max_drawdown:.2f}%",
            f"  Max DD Dur : {self.max_drawdown_duration} candles",
            "",
            f"  Avg Win    : ${self.avg_win:,.2f}",
            f"  Avg Loss   : ${self.avg_loss:,.2f}",
            f"  Largest Win: ${self.largest_win:,.2f}",
            f"  Largest Los: ${self.largest_loss:,.2f}",
            f"  Avg Hold   : {self.avg_holding_period:.1f} hours",
            "=" * 60,
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize to dict for JSON storage."""
        return {
            "config_name": self.config_name,
            "start_date": str(self.start_date),
            "end_date": str(self.end_date),
            "duration_days": self.duration_days,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "params": self.params,
            "initial_balance": self.initial_balance,
            "final_balance": self.final_balance,
            "total_return": self.total_return,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_duration": self.max_drawdown_duration,
            "profit_factor": self.profit_factor,
            "expectancy": self.expectancy,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "largest_win": self.largest_win,
            "largest_loss": self.largest_loss,
            "avg_holding_period": self.avg_holding_period,
            "equity_curve": self.equity_curve,
            "drawdown_curve": self.drawdown_curve,
            "daily_returns": self.daily_returns,
        }


# ---------------------------------------------------------------------------
# Sprint-19 professional backtesting engine
# ---------------------------------------------------------------------------


class BacktestEngine:
    """Professional backtesting engine with anti look-ahead bias."""

    def __init__(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "1h",
        initial_balance: float = 10000.0,
        commission: float = 0.001,    # 0.1 %
        slippage: float = 0.0005,     # 0.05 %
    ):
        self.symbol = symbol
        self.timeframe = timeframe
        self.initial_balance = initial_balance
        self.commission = commission
        self.slippage = slippage

    # ----- public API -------------------------------------------------------

    def run(
        self,
        strategy: GridStrategy,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        data: Optional[pd.DataFrame] = None,
        params: Optional[dict] = None,
    ) -> BacktestResult:
        """Run backtest with strict chronological data access.

        Anti look-ahead bias: strategy only sees data UP TO current candle,
        fills at next candle open (not current close).
        """
        from binance_bot.strategies.base import SignalType

        df = self._prepare_data(data, start_date, end_date)
        if df is None:
            return BacktestResult(config_name="empty")

        # State
        balance = self.initial_balance
        holdings = 0.0
        trades: list[dict] = []
        equity_values: list[float] = []
        drawdown_values: list[float] = []
        pending_orders: list[dict] = []
        peak_equity = self.initial_balance
        max_dd_duration = 0
        current_dd_duration = 0

        strategy.levels = []
        strategy.center_price = None

        for i in range(len(df)):
            row = df.iloc[i]
            timestamp = df.index[i]
            current_price = row["close"]

            # Fill pending orders at candle open
            balance, holdings = self._fill_pending_orders(
                pending_orders, row["open"], timestamp, balance, holdings, trades,
            )
            pending_orders.clear()

            # Equity tracking
            equity = balance + holdings * current_price
            equity_values.append(equity)

            if equity > peak_equity:
                peak_equity = equity
                current_dd_duration = 0
            else:
                current_dd_duration += 1
                max_dd_duration = max(max_dd_duration, current_dd_duration)

            dd_pct = ((peak_equity - equity) / peak_equity * 100) if peak_equity > 0 else 0.0
            drawdown_values.append(dd_pct)

            # Strategy sees data UP TO current candle only
            visible_data = df.iloc[: i + 1]
            signals = strategy.calculate_signals(visible_data, current_price)

            last_buy_price = 0.0
            buy_trades = [t for t in trades if t["type"] == "BUY"]
            if buy_trades:
                last_buy_price = buy_trades[-1]["fill_price"]

            for signal in signals:
                if signal.type == SignalType.HOLD:
                    continue
                pending_orders.append({
                    "side": "BUY" if signal.type == SignalType.BUY else "SELL",
                    "signal_price": signal.price,
                    "amount": signal.amount,
                    "entry_price": last_buy_price,
                })

        final_balance = balance + holdings * df["close"].iloc[-1]
        result = self._compute_result(
            trades=trades, equity_values=equity_values,
            drawdown_values=drawdown_values, max_dd_duration=max_dd_duration,
            final_balance=final_balance, df=df, params=params,
        )
        logger.info(result.summary())
        return result

    def _prepare_data(
        self, data: Optional[pd.DataFrame], start_date: Optional[str], end_date: Optional[str],
    ) -> Optional[pd.DataFrame]:
        """Validate and filter data. Returns None if no data."""
        if data is None or data.empty:
            logger.warning("No data provided.")
            return None
        df = data.copy()
        if start_date is not None:
            df = df[df.index >= pd.Timestamp(start_date)]
        if end_date is not None:
            df = df[df.index <= pd.Timestamp(end_date)]
        if df.empty:
            logger.warning("No data after date filtering.")
            return None
        return df

    def _fill_pending_orders(
        self, orders: list[dict], candle_open: float, timestamp,
        balance: float, holdings: float, trades: list[dict],
    ) -> tuple[float, float]:
        """Fill pending orders at candle open price with slippage."""
        for order in orders:
            fill_price = self._apply_slippage(candle_open, order["side"])
            cost = fill_price * order["amount"]
            commission_cost = cost * self.commission

            if order["side"] == "BUY":
                total_cost = cost + commission_cost
                if balance >= total_cost:
                    balance -= total_cost
                    holdings += order["amount"]
                    trades.append({
                        "timestamp": str(timestamp), "type": "BUY",
                        "signal_price": order["signal_price"], "fill_price": fill_price,
                        "amount": order["amount"], "cost": total_cost,
                        "commission": commission_cost, "balance": balance,
                        "holdings": holdings,
                    })
            else:  # SELL
                if holdings >= order["amount"]:
                    revenue = cost - commission_cost
                    balance += revenue
                    holdings -= order["amount"]
                    entry_price = order.get("entry_price", fill_price)
                    pnl = (fill_price - entry_price) * order["amount"] - commission_cost
                    trades.append({
                        "timestamp": str(timestamp), "type": "SELL",
                        "signal_price": order["signal_price"], "fill_price": fill_price,
                        "amount": order["amount"], "revenue": revenue,
                        "pnl": pnl, "commission": commission_cost,
                        "balance": balance, "holdings": holdings,
                    })
        return balance, holdings

    # ----- helpers ----------------------------------------------------------

    def _apply_slippage(self, price: float, side: str) -> float:
        """Apply slippage to fill price."""
        if side == "BUY":
            return price * (1 + self.slippage)
        return price * (1 - self.slippage)

    def _compute_result(
        self,
        trades: list[dict],
        equity_values: list[float],
        drawdown_values: list[float],
        max_dd_duration: int,
        final_balance: float,
        df: pd.DataFrame,
        params: Optional[dict],
    ) -> BacktestResult:
        """Compute comprehensive BacktestResult from raw data."""
        total_return = ((final_balance - self.initial_balance) / self.initial_balance) * 100

        # Pair buy/sell trades for PnL analysis
        sell_trades = [t for t in trades if t["type"] == "SELL"]
        pnls = [t.get("pnl", 0.0) for t in sell_trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        winning_count = len(wins)
        losing_count = len(losses)
        total_completed = winning_count + losing_count
        win_rate = (winning_count / total_completed * 100) if total_completed > 0 else 0.0

        avg_win = float(np.mean(wins)) if wins else 0.0
        avg_loss = float(np.mean(losses)) if losses else 0.0
        largest_win = float(max(wins)) if wins else 0.0
        largest_loss = float(min(losses)) if losses else 0.0

        gross_profit = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (9999.99 if gross_profit > 0 else 0.0)

        expectancy = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss) if total_completed > 0 else 0.0

        # Holding periods (rough: time between consecutive buy→sell)
        holding_hours = self._estimate_holding_periods(trades)
        avg_holding = float(np.mean(holding_hours)) if holding_hours else 0.0

        # Daily returns from equity curve
        daily_returns = []
        for idx in range(1, len(equity_values)):
            prev = equity_values[idx - 1]
            if prev != 0:
                daily_returns.append((equity_values[idx] - prev) / prev)

        # Risk metrics via PerformanceMetrics (lazy import to avoid circular dep)
        from shared.optimization.metrics import PerformanceMetrics

        sharpe = PerformanceMetrics.sharpe_ratio(daily_returns)
        sortino = PerformanceMetrics.sortino_ratio(daily_returns)
        max_dd = PerformanceMetrics.max_drawdown(equity_values) * 100  # as %

        # Dates
        start_dt = df.index[0]
        end_dt = df.index[-1]
        duration = (end_dt - start_dt).total_seconds() / 86400

        return BacktestResult(
            config_name=params.get("name", "backtest") if params else "backtest",
            start_date=start_dt,
            end_date=end_dt,
            duration_days=duration,
            symbol=self.symbol,
            timeframe=self.timeframe,
            params=params or {},
            initial_balance=self.initial_balance,
            final_balance=final_balance,
            total_return=total_return,
            total_trades=len(trades),
            winning_trades=winning_count,
            losing_trades=losing_count,
            win_rate=win_rate,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown=max_dd,
            max_drawdown_duration=max_dd_duration,
            profit_factor=profit_factor,
            expectancy=expectancy,
            avg_win=avg_win,
            avg_loss=avg_loss,
            largest_win=largest_win,
            largest_loss=largest_loss,
            avg_holding_period=avg_holding,
            equity_curve=equity_values,
            drawdown_curve=drawdown_values,
            daily_returns=daily_returns,
            trades=trades,
        )

    @staticmethod
    def _estimate_holding_periods(trades: list[dict]) -> list[float]:
        """Estimate holding period in hours for each buy→sell pair."""
        hours = []
        last_buy_ts = None
        for t in trades:
            if t["type"] == "BUY":
                last_buy_ts = t["timestamp"]
            elif t["type"] == "SELL" and last_buy_ts is not None:
                try:
                    buy_dt = pd.Timestamp(last_buy_ts)
                    sell_dt = pd.Timestamp(t["timestamp"])
                    diff = (sell_dt - buy_dt).total_seconds() / 3600
                    hours.append(diff)
                except Exception:
                    pass
                last_buy_ts = None
        return hours


# ---------------------------------------------------------------------------
# Legacy Backtester (Sprint 17) — kept for backward compatibility
# ---------------------------------------------------------------------------


class Backtester:
    """Backtest trading strategies on historical data (legacy API)."""

    def __init__(
        self,
        initial_balance: float = 10000.0,
        commission: float = 0.001,
    ):
        self.initial_balance = initial_balance
        self.commission = commission
        self.risk_metrics = RiskMetrics(initial_balance=initial_balance)

    def run(
        self,
        strategy: GridStrategy,
        data: pd.DataFrame,
        price_column: str = "close",
        config_name: str = "default",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> BacktestResult:
        """Run backtest on historical data."""
        from binance_bot.strategies.base import SignalType

        if start_date is not None:
            data = data[data.index >= pd.Timestamp(start_date)]
        if end_date is not None:
            data = data[data.index <= pd.Timestamp(end_date)]
        if data.empty:
            logger.warning("No data after date filtering.")
            return BacktestResult(config_name=config_name)

        logger.info(f"Running backtest '{config_name}' on {len(data)} candles...")

        balance = self.initial_balance
        holdings = 0.0
        trades = []
        equity_curve = []

        strategy.levels = []
        strategy.center_price = None
        self.risk_metrics = RiskMetrics(initial_balance=self.initial_balance)

        peak_equity = self.initial_balance
        max_drawdown = 0.0
        last_buy_price = 0.0

        for i, (timestamp, row) in enumerate(data.iterrows()):
            price = row[price_column]
            equity = balance + (holdings * price)
            equity_curve.append({
                "timestamp": str(timestamp),
                "equity": equity,
                "price": price,
                "holdings": holdings,
                "balance": balance,
            })
            self.risk_metrics.update_equity(equity)

            if equity > peak_equity:
                peak_equity = equity
            drawdown = (peak_equity - equity) / peak_equity
            if drawdown > max_drawdown:
                max_drawdown = drawdown

            signals = strategy.calculate_signals(data.iloc[: i + 1], price)

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

        final_price = data[price_column].iloc[-1]
        final_balance = balance + (holdings * final_price)
        total_return = ((final_balance - self.initial_balance) / self.initial_balance) * 100

        winning = len(self.risk_metrics.winning_trades)
        losing = len(self.risk_metrics.losing_trades)
        total_completed = winning + losing
        win_rate = (winning / total_completed * 100) if total_completed > 0 else 0

        start_d = data.index[0]
        end_d = data.index[-1]
        duration = (end_d - start_d).total_seconds() / 86400

        result = BacktestResult(
            config_name=config_name,
            start_date=start_d,
            end_date=end_d,
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

    def run_with_params(
        self,
        params: dict,
        data: pd.DataFrame,
        symbol: str = "BTC/USDT",
        price_column: str = "close",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> BacktestResult:
        """Run backtest with a flat parameter dict (for optimizers)."""
        from binance_bot.strategies import GridStrategy, GridConfig

        config = GridConfig(
            grid_levels=params.get("grid_levels", 10),
            grid_spacing_pct=params.get("grid_spacing_pct", 1.0),
            amount_per_level=params.get("amount_per_level", 0.001),
        )
        strategy = GridStrategy(symbol=symbol, config=config)
        return self.run(
            strategy=strategy,
            data=data,
            price_column=price_column,
            config_name="params_run",
            start_date=start_date,
            end_date=end_date,
        )

    def run_comparison(
        self,
        configs: List[Dict],
        data: pd.DataFrame,
        price_column: str = "close",
    ) -> List[BacktestResult]:
        """Run multiple backtests with different configs for comparison."""
        from binance_bot.strategies import GridStrategy, GridConfig

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
        results.sort(key=lambda r: r.total_return, reverse=True)
        self._print_comparison(results)
        return results

    def _print_result(self, result: BacktestResult):
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"BACKTEST RESULTS: {result.config_name}")
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
        logger.info("")
        logger.info("=" * 80)
        logger.info("STRATEGY COMPARISON (sorted by return)")
        logger.info("=" * 80)
        logger.info(
            f"{'Config':<20} {'Return':>10} {'Win Rate':>10} {'Max DD':>10} {'Sharpe':>10} {'Trades':>8}"
        )
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
