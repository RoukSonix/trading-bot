"""Integration tests for the optimization flow (Sprint 18)."""

import json
import tempfile
from pathlib import Path

import pytest

from tests.conftest import make_ohlcv_df
from shared.optimization.optimizer import GridOptimizer
from shared.optimization.walk_forward import WalkForwardOptimizer


@pytest.fixture
def ohlcv_data():
    """200-candle OHLCV DataFrame with slight trend for meaningful signals."""
    return make_ohlcv_df(n=200, base_price=50000.0, trend=0.001, seed=123)


class TestFullOptimizationRun:
    """Integration test for a full Optuna optimization run."""

    def test_full_optimization_run(self, ohlcv_data):
        """Run a small optimization (3 trials) and verify outputs."""
        optimizer = GridOptimizer(symbol="BTC/USDT")

        best_params, best_sharpe = optimizer.optimize(
            data=ohlcv_data,
            n_trials=3,
            timeout=120,
            study_name="test_integration",
        )

        # Verify we got valid params
        assert isinstance(best_params, dict)
        assert "grid_levels" in best_params
        assert "grid_spacing_pct" in best_params
        assert "amount_per_level" in best_params
        assert isinstance(best_sharpe, float)

        # Verify params are in valid range
        assert 5 <= best_params["grid_levels"] <= 30
        assert 0.3 <= best_params["grid_spacing_pct"] <= 5.0
        assert 0.0001 <= best_params["amount_per_level"] <= 0.01

        # Verify we can get history
        history = optimizer.get_optimization_history()
        assert len(history) == 3

    def test_save_and_load_best_params(self, ohlcv_data):
        """Verify saving and loading best params to JSON."""
        optimizer = GridOptimizer(symbol="BTC/USDT")
        optimizer.optimize(data=ohlcv_data, n_trials=3, timeout=60)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmpfile = f.name

        optimizer.save_best_params(tmpfile)

        # Verify file exists and is valid JSON
        path = Path(tmpfile)
        assert path.exists()

        with open(path) as f:
            saved = json.load(f)

        assert "grid_levels" in saved
        assert "symbol" in saved
        assert saved["symbol"] == "BTC/USDT"
        assert "sharpe_ratio" in saved

        # Cleanup
        path.unlink()


class TestWalkForward:
    """Integration test for walk-forward optimization."""

    def test_walk_forward(self, ohlcv_data):
        """Run walk-forward with 2 windows and 2 trials each."""
        optimizer = GridOptimizer(symbol="BTC/USDT")

        wf = WalkForwardOptimizer(optimizer)
        results = wf.run(
            data=ohlcv_data,
            train_pct=0.7,
            n_windows=2,
            n_trials=2,
            timeout=60,
        )

        assert len(results) >= 1

        for r in results:
            assert "window" in r
            assert "best_params" in r
            assert "in_sample_sharpe" in r
            assert "out_of_sample_sharpe" in r
            assert "out_of_sample_return" in r
            assert isinstance(r["in_sample_sharpe"], float)
            assert isinstance(r["out_of_sample_sharpe"], float)
