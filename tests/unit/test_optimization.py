"""Unit tests for the optimization module (Sprint 18)."""

import numpy as np
import pytest

from shared.optimization.metrics import PerformanceMetrics


class TestSearchSpaceValidRanges:
    """Test that the optimizer search space produces valid ranges."""

    def test_search_space_valid_ranges(self):
        """Verify GridOptimizer search space constraints are reasonable."""
        # Import here to avoid optuna import at module level for fast tests
        import optuna

        from shared.optimization.optimizer import GridOptimizer

        optimizer = GridOptimizer(symbol="BTC/USDT")
        study = optuna.create_study()
        trial = study.ask()
        params = optimizer.define_search_space(trial)

        assert 5 <= params["grid_levels"] <= 30
        assert 0.3 <= params["grid_spacing_pct"] <= 5.0
        assert 0.0001 <= params["amount_per_level"] <= 0.01
        assert 3.0 <= params["upper_bound_pct"] <= 15.0
        assert 3.0 <= params["lower_bound_pct"] <= 15.0


class TestPerformanceMetrics:
    """Test PerformanceMetrics static calculations."""

    def test_sharpe_ratio_positive(self):
        """Sharpe ratio is positive for consistently positive returns."""
        returns = [0.01, 0.02, 0.015, 0.01, 0.02, 0.005, 0.01, 0.015, 0.02, 0.01]
        sharpe = PerformanceMetrics.sharpe_ratio(returns)
        assert sharpe > 0

    def test_sharpe_ratio_negative(self):
        """Sharpe ratio is negative for consistently negative returns."""
        returns = [-0.01, -0.02, -0.015, -0.01, -0.02, -0.005, -0.01, -0.015, -0.02, -0.01]
        sharpe = PerformanceMetrics.sharpe_ratio(returns)
        assert sharpe < 0

    def test_sharpe_ratio_insufficient_data(self):
        """Sharpe ratio returns 0 when < 2 data points."""
        assert PerformanceMetrics.sharpe_ratio([]) == 0.0
        assert PerformanceMetrics.sharpe_ratio([0.01]) == 0.0

    def test_sharpe_ratio_zero_std(self):
        """Sharpe ratio returns 0 for zero-variance returns."""
        returns = [0.01, 0.01, 0.01, 0.01]
        assert PerformanceMetrics.sharpe_ratio(returns) == 0.0

    def test_sortino_ratio_positive(self):
        """Sortino is positive for mostly positive returns."""
        returns = [0.02, 0.01, -0.005, 0.03, 0.015, -0.002, 0.02, 0.01, 0.025, 0.01]
        sortino = PerformanceMetrics.sortino_ratio(returns)
        assert sortino > 0

    def test_sortino_ratio_no_downside(self):
        """Sortino is 0.0 (finite) if no negative returns (BUG-007 fix)."""
        returns = [0.01, 0.02, 0.015, 0.01]
        sortino = PerformanceMetrics.sortino_ratio(returns)
        assert sortino == 0.0

    def test_sortino_ratio_insufficient_data(self):
        """Sortino returns 0 when < 2 data points."""
        assert PerformanceMetrics.sortino_ratio([]) == 0.0
        assert PerformanceMetrics.sortino_ratio([0.01]) == 0.0

    def test_max_drawdown_simple(self):
        """Max drawdown is computed correctly."""
        equity = [100, 110, 105, 95, 100, 90, 110]
        dd = PerformanceMetrics.max_drawdown(equity)
        # Peak is 110, trough is 90 -> 20/110 ≈ 0.1818
        assert abs(dd - 20 / 110) < 1e-6

    def test_max_drawdown_no_drawdown(self):
        """Max drawdown is 0 for monotonically increasing equity."""
        equity = [100, 101, 102, 103, 104]
        assert PerformanceMetrics.max_drawdown(equity) == 0.0

    def test_max_drawdown_insufficient_data(self):
        """Max drawdown is 0 for < 2 points."""
        assert PerformanceMetrics.max_drawdown([]) == 0.0
        assert PerformanceMetrics.max_drawdown([100]) == 0.0

    def test_win_rate_all_winners(self):
        """Win rate is 1.0 if all trades are winners."""
        trades = [{"pnl": 10}, {"pnl": 5}, {"pnl": 20}]
        assert PerformanceMetrics.win_rate(trades) == 1.0

    def test_win_rate_all_losers(self):
        """Win rate is 0.0 if all trades are losers."""
        trades = [{"pnl": -10}, {"pnl": -5}]
        assert PerformanceMetrics.win_rate(trades) == 0.0

    def test_win_rate_mixed(self):
        """Win rate for mixed outcomes."""
        trades = [{"pnl": 10}, {"pnl": -5}, {"pnl": 20}, {"pnl": -3}]
        assert PerformanceMetrics.win_rate(trades) == 0.5

    def test_win_rate_empty(self):
        """Win rate is 0 for empty list."""
        assert PerformanceMetrics.win_rate([]) == 0.0

    def test_profit_factor_basic(self):
        """Profit factor = gross profit / gross loss."""
        trades = [{"pnl": 100}, {"pnl": -50}, {"pnl": 80}]
        pf = PerformanceMetrics.profit_factor(trades)
        assert abs(pf - 180 / 50) < 1e-6

    def test_profit_factor_no_losses(self):
        """Profit factor is inf with no losses."""
        trades = [{"pnl": 10}, {"pnl": 20}]
        assert PerformanceMetrics.profit_factor(trades) == float("inf")

    def test_profit_factor_no_wins(self):
        """Profit factor is 0 with no wins."""
        trades = [{"pnl": -10}, {"pnl": -20}]
        assert PerformanceMetrics.profit_factor(trades) == 0.0

    def test_calmar_ratio(self):
        """Calmar ratio = annualized return / max drawdown."""
        returns = [0.01] * 10  # constant positive returns
        max_dd = 0.05
        calmar = PerformanceMetrics.calmar_ratio(returns, max_dd)
        expected = (np.mean(returns) * 252) / max_dd
        assert abs(calmar - expected) < 1e-6

    def test_calmar_ratio_zero_drawdown(self):
        """Calmar is 0 when max drawdown is 0."""
        assert PerformanceMetrics.calmar_ratio([0.01, 0.02], 0.0) == 0.0

    def test_calculate_all(self):
        """calculate_all returns all expected keys."""
        equity = [10000, 10100, 10050, 10200, 10150, 10300]
        trades = [{"pnl": 100}, {"pnl": -50}, {"pnl": 150}, {"pnl": -50}, {"pnl": 150}]
        result = PerformanceMetrics.calculate_all(trades, equity)

        expected_keys = {
            "sharpe_ratio",
            "sortino_ratio",
            "max_drawdown",
            "win_rate",
            "profit_factor",
            "calmar_ratio",
        }
        assert set(result.keys()) == expected_keys
        assert result["win_rate"] == 0.6
        assert result["max_drawdown"] >= 0
