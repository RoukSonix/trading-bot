"""Strategy benchmarking — compare multiple strategies side-by-side."""

import pandas as pd
from loguru import logger

from shared.backtest.engine import BacktestEngine, BacktestResult
from binance_bot.strategies import GridStrategy, GridConfig


class StrategyBenchmark:
    """Compare multiple strategies side-by-side."""

    def __init__(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "1h",
        initial_balance: float = 10000.0,
        commission: float = 0.001,
        slippage: float = 0.0005,
    ):
        self.symbol = symbol
        self.timeframe = timeframe
        self.initial_balance = initial_balance
        self.commission = commission
        self.slippage = slippage

    def compare(
        self,
        strategies: list[GridStrategy],
        data: pd.DataFrame,
        params_list: list[dict] | None = None,
    ) -> dict:
        """Run same data through multiple strategies.

        Args:
            strategies: List of strategy instances to compare.
            data: OHLCV DataFrame.
            params_list: Optional list of param dicts (one per strategy).

        Returns:
            Dict with 'results' list and 'comparison_table' string.
        """
        results: list[BacktestResult] = []
        params_list = params_list or [None] * len(strategies)

        for idx, (strategy, params) in enumerate(zip(strategies, params_list)):
            engine = BacktestEngine(
                symbol=self.symbol,
                timeframe=self.timeframe,
                initial_balance=self.initial_balance,
                commission=self.commission,
                slippage=self.slippage,
            )
            p = params or {"name": strategy.name if hasattr(strategy, "name") else f"strategy_{idx}"}
            result = engine.run(strategy=strategy, data=data, params=p)
            results.append(result)

        # Sort by total return
        results.sort(key=lambda r: r.total_return, reverse=True)
        table = self._build_table(results)
        logger.info(table)

        return {"results": results, "comparison_table": table}

    def vs_buy_and_hold(
        self,
        strategy_result: BacktestResult,
        data: pd.DataFrame,
    ) -> dict:
        """Compare strategy vs simple buy-and-hold.

        Args:
            strategy_result: Existing backtest result for the strategy.
            data: OHLCV DataFrame used for the backtest.

        Returns:
            Dict with buy-and-hold metrics and comparison.
        """
        if data.empty:
            return {"error": "No data provided"}

        first_close = data["close"].iloc[0]
        last_close = data["close"].iloc[-1]
        bnh_return = ((last_close - first_close) / first_close) * 100

        # Buy-and-hold equity curve: buy at first close, hold
        amount = self.initial_balance / first_close
        bnh_equity = [self.initial_balance]
        for price in data["close"].iloc[1:]:
            bnh_equity.append(amount * price)

        # Max drawdown for buy-and-hold
        peak = bnh_equity[0]
        max_dd = 0.0
        for val in bnh_equity:
            if val > peak:
                peak = val
            dd = (peak - val) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)

        bnh_final = bnh_equity[-1]

        comparison = {
            "strategy": {
                "name": strategy_result.config_name,
                "total_return": strategy_result.total_return,
                "max_drawdown": strategy_result.max_drawdown,
                "sharpe_ratio": strategy_result.sharpe_ratio,
                "total_trades": strategy_result.total_trades,
                "final_balance": strategy_result.final_balance,
            },
            "buy_and_hold": {
                "name": "Buy & Hold",
                "total_return": bnh_return,
                "max_drawdown": max_dd * 100,
                "final_balance": bnh_final,
            },
            "outperformance": strategy_result.total_return - bnh_return,
            "bnh_equity_curve": bnh_equity,
        }

        logger.info(f"Strategy return: {strategy_result.total_return:+.2f}%")
        logger.info(f"Buy & Hold return: {bnh_return:+.2f}%")
        logger.info(f"Outperformance: {comparison['outperformance']:+.2f}%")

        return comparison

    @staticmethod
    def _build_table(results: list[BacktestResult]) -> str:
        """Build a comparison table string."""
        header = (
            f"{'Strategy':<20} {'Return':>10} {'Win Rate':>10} "
            f"{'Max DD':>10} {'Sharpe':>10} {'Sortino':>10} "
            f"{'PF':>8} {'Trades':>8}"
        )
        sep = "=" * len(header)
        lines = [sep, "  STRATEGY COMPARISON (sorted by return)", sep, header, "-" * len(header)]

        for r in results:
            lines.append(
                f"{r.config_name:<20} "
                f"{r.total_return:>+9.2f}% "
                f"{r.win_rate:>9.1f}% "
                f"{r.max_drawdown:>9.2f}% "
                f"{r.sharpe_ratio:>10.2f} "
                f"{r.sortino_ratio:>10.2f} "
                f"{r.profit_factor:>8.2f} "
                f"{r.total_trades:>8}"
            )

        lines.append(sep)
        return "\n".join(lines)
