"""Optuna-based grid strategy hyperparameter optimizer."""

import json
from pathlib import Path
from typing import Optional

import optuna
import pandas as pd
from loguru import logger

from shared.backtest.engine import Backtester
from shared.optimization.metrics import PerformanceMetrics


class GridOptimizer:
    """Optuna-based grid strategy optimizer.

    Searches for optimal grid trading parameters by running backtests
    with different hyperparameter combinations and maximising Sharpe ratio.
    """

    def __init__(
        self,
        symbol: str = "BTC/USDT",
        initial_balance: float = 10000.0,
        commission: float = 0.001,
    ):
        """Initialize optimizer.

        Args:
            symbol: Trading pair symbol.
            initial_balance: Starting balance for backtests.
            commission: Commission rate per trade.
        """
        self.symbol = symbol
        self.initial_balance = initial_balance
        self.commission = commission
        self._data: Optional[pd.DataFrame] = None

    def set_data(self, data: pd.DataFrame):
        """Set historical data for backtesting.

        Args:
            data: OHLCV DataFrame with datetime index.
        """
        self._data = data

    def define_search_space(self, trial: optuna.Trial) -> dict:
        """Define hyperparameter search space.

        Args:
            trial: Optuna trial object.

        Returns:
            Dict of sampled hyperparameters.
        """
        return {
            "grid_levels": trial.suggest_int("grid_levels", 5, 30),
            "grid_spacing_pct": trial.suggest_float("grid_spacing_pct", 0.3, 5.0),
            "amount_per_level": trial.suggest_float("amount_per_level", 0.0001, 0.01, log=True),
            "upper_bound_pct": trial.suggest_float("upper_bound_pct", 3.0, 15.0),
            "lower_bound_pct": trial.suggest_float("lower_bound_pct", 3.0, 15.0),
        }

    def objective(self, trial: optuna.Trial) -> float:
        """Optuna objective function — maximize Sharpe ratio.

        Args:
            trial: Optuna trial.

        Returns:
            Sharpe ratio for the trial's parameters.
        """
        params = self.define_search_space(trial)
        result = self._run_backtest(params)
        sharpe = result["sharpe_ratio"]

        # Report intermediate metrics for pruning
        trial.set_user_attr("total_return", result["total_return"])
        trial.set_user_attr("max_drawdown", result["max_drawdown"])
        trial.set_user_attr("win_rate", result["win_rate"])
        trial.set_user_attr("profit_factor", result["profit_factor"])
        trial.set_user_attr("total_trades", result["total_trades"])

        return sharpe

    def optimize(
        self,
        data: Optional[pd.DataFrame] = None,
        n_trials: int = 100,
        timeout: Optional[int] = 3600,
        study_name: str = "grid_optimization",
    ) -> tuple[dict, float]:
        """Run optimization.

        Args:
            data: OHLCV DataFrame. Uses previously set data if None.
            n_trials: Maximum number of trials.
            timeout: Timeout in seconds (None = no timeout).
            study_name: Name for the Optuna study.

        Returns:
            Tuple of (best_params, best_sharpe_ratio).
        """
        if data is not None:
            self._data = data

        if self._data is None or self._data.empty:
            raise ValueError("No data provided. Call set_data() or pass data to optimize().")

        # Suppress Optuna internal logging — keep only warnings+
        optuna.logging.set_verbosity(optuna.logging.WARNING)

        study = optuna.create_study(
            direction="maximize",
            study_name=study_name,
            sampler=optuna.samplers.TPESampler(seed=42),
        )

        logger.info(f"Starting optimization: {n_trials} trials, timeout={timeout}s")
        study.optimize(self.objective, n_trials=n_trials, timeout=timeout)

        best = study.best_params
        best_value = study.best_value

        logger.info(f"Optimization complete. Best Sharpe: {best_value:.4f}")
        logger.info(f"Best params: {best}")

        self._study = study
        return best, best_value

    def _run_backtest(self, params: dict) -> dict:
        """Run a single backtest with the given parameters.

        Args:
            params: Dict of hyperparameters.

        Returns:
            Dict with performance metrics.
        """
        from binance_bot.strategies import GridStrategy, GridConfig

        config = GridConfig(
            grid_levels=params["grid_levels"],
            grid_spacing_pct=params["grid_spacing_pct"],
            amount_per_level=params["amount_per_level"],
        )

        strategy = GridStrategy(symbol=self.symbol, config=config)
        backtester = Backtester(
            initial_balance=self.initial_balance,
            commission=self.commission,
        )

        result = backtester.run(
            strategy=strategy,
            data=self._data,
            price_column="close",
            config_name="optuna_trial",
        )

        # Extract equity values for standalone metrics
        equity_values = [e["equity"] for e in result.equity_curve]

        return {
            "sharpe_ratio": result.sharpe_ratio,
            "sortino_ratio": result.sortino_ratio,
            "max_drawdown": result.max_drawdown,
            "total_return": result.total_return,
            "win_rate": result.win_rate,
            "profit_factor": result.profit_factor,
            "total_trades": result.total_trades,
            "equity_curve": equity_values,
        }

    def save_best_params(self, filepath: str):
        """Save best parameters to JSON file.

        Args:
            filepath: Path to save the JSON file.
        """
        if not hasattr(self, "_study"):
            raise RuntimeError("No optimization has been run yet.")

        best = self._study.best_params
        best["sharpe_ratio"] = self._study.best_value
        best["symbol"] = self.symbol

        # Include user attrs from best trial
        for key, val in self._study.best_trial.user_attrs.items():
            best[key] = val

        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(best, f, indent=2)

        logger.info(f"Best parameters saved to {filepath}")

    def get_optimization_history(self) -> list[dict]:
        """Get optimization history for visualization.

        Returns:
            List of dicts with trial number, value, and params.
        """
        if not hasattr(self, "_study"):
            return []

        history = []
        for trial in self._study.trials:
            if trial.state == optuna.trial.TrialState.COMPLETE:
                history.append({
                    "trial": trial.number,
                    "sharpe_ratio": trial.value,
                    "params": trial.params,
                    **trial.user_attrs,
                })
        return history
