"""Walk-forward optimization to avoid overfitting."""

from typing import Optional

import pandas as pd
from loguru import logger

from shared.optimization.optimizer import GridOptimizer


class WalkForwardOptimizer:
    """Walk-forward optimization splits data into train/test windows.

    Optimizes on each training window, then validates on the subsequent
    test window.  This guards against overfitting to a single data period.
    """

    def __init__(self, optimizer: GridOptimizer):
        """Initialize with a configured GridOptimizer.

        Args:
            optimizer: GridOptimizer instance (symbol, balance, commission preset).
        """
        self.optimizer = optimizer
        self.results: list[dict] = []

    def run(
        self,
        data: pd.DataFrame,
        train_pct: float = 0.7,
        n_windows: int = 5,
        n_trials: int = 50,
        timeout: Optional[int] = 600,
    ) -> list[dict]:
        """Run walk-forward optimization.

        Splits data into *n_windows* overlapping train/test windows.
        For each window the optimizer searches for the best params on the
        training portion, then validates those params on the test portion.

        Args:
            data: Full OHLCV DataFrame with datetime index.
            train_pct: Fraction of each window used for training (0-1).
            n_windows: Number of walk-forward windows.
            n_trials: Optuna trials per window.
            timeout: Timeout per window (seconds).

        Returns:
            List of per-window result dicts containing best params and
            in-sample / out-of-sample metrics.
        """
        total_rows = len(data)
        if total_rows < 20:
            raise ValueError("Not enough data for walk-forward optimization.")

        # Calculate window size with overlap
        step = int((total_rows * (1 - train_pct)) / n_windows)
        window_size = int(total_rows * train_pct / (1 - (1 - train_pct) / n_windows * (n_windows - 1)))
        window_size = min(window_size, total_rows)

        self.results = []

        for i in range(n_windows):
            start_idx = i * step
            end_idx = start_idx + window_size
            if end_idx > total_rows:
                end_idx = total_rows
                start_idx = max(0, end_idx - window_size)

            window_data = data.iloc[start_idx:end_idx]
            split_point = int(len(window_data) * train_pct)

            train_data = window_data.iloc[:split_point]
            test_data = window_data.iloc[split_point:]

            if len(train_data) < 10 or len(test_data) < 5:
                logger.warning(f"Window {i+1}: insufficient data, skipping")
                continue

            logger.info(
                f"Window {i+1}/{n_windows}: "
                f"train={len(train_data)} rows, test={len(test_data)} rows"
            )

            # Optimize on training data
            best_params, in_sample_sharpe = self.optimizer.optimize(
                data=train_data,
                n_trials=n_trials,
                timeout=timeout,
                study_name=f"wf_window_{i+1}",
            )

            # Validate on test data
            self.optimizer.set_data(test_data)
            oos_result = self.optimizer._run_backtest(best_params)

            window_result = {
                "window": i + 1,
                "train_start": str(train_data.index[0]),
                "train_end": str(train_data.index[-1]),
                "test_start": str(test_data.index[0]),
                "test_end": str(test_data.index[-1]),
                "best_params": best_params,
                "in_sample_sharpe": in_sample_sharpe,
                "out_of_sample_sharpe": oos_result["sharpe_ratio"],
                "out_of_sample_return": oos_result["total_return"],
                "out_of_sample_max_dd": oos_result["max_drawdown"],
            }
            self.results.append(window_result)

            logger.info(
                f"  IS Sharpe: {in_sample_sharpe:.4f} | "
                f"OOS Sharpe: {oos_result['sharpe_ratio']:.4f} | "
                f"OOS Return: {oos_result['total_return']:+.2f}%"
            )

        self._print_summary()
        return self.results

    def _print_summary(self):
        """Print walk-forward summary."""
        if not self.results:
            logger.warning("No walk-forward results to summarize.")
            return

        logger.info("")
        logger.info("=" * 70)
        logger.info("WALK-FORWARD OPTIMIZATION SUMMARY")
        logger.info("=" * 70)
        logger.info(
            f"{'Window':<8} {'IS Sharpe':>12} {'OOS Sharpe':>12} "
            f"{'OOS Return':>12} {'OOS MaxDD':>12}"
        )
        logger.info("-" * 70)

        for r in self.results:
            logger.info(
                f"{r['window']:<8} "
                f"{r['in_sample_sharpe']:>12.4f} "
                f"{r['out_of_sample_sharpe']:>12.4f} "
                f"{r['out_of_sample_return']:>+11.2f}% "
                f"{r['out_of_sample_max_dd']:>11.2f}%"
            )

        # Averages
        avg_is = sum(r["in_sample_sharpe"] for r in self.results) / len(self.results)
        avg_oos = sum(r["out_of_sample_sharpe"] for r in self.results) / len(self.results)
        avg_ret = sum(r["out_of_sample_return"] for r in self.results) / len(self.results)

        logger.info("-" * 70)
        logger.info(
            f"{'AVG':<8} {avg_is:>12.4f} {avg_oos:>12.4f} {avg_ret:>+11.2f}%"
        )
        logger.info("=" * 70)
