"""Integration tests for the Sprint 19 backtest flow."""

import json
import tempfile
from pathlib import Path

import pytest

from tests.conftest import make_ohlcv_df
from shared.backtest.engine import BacktestEngine, BacktestResult
from shared.backtest.benchmark import StrategyBenchmark
from binance_bot.strategies import GridStrategy, GridConfig


@pytest.fixture
def ohlcv_data():
    """200-candle OHLCV DataFrame with slight trend."""
    return make_ohlcv_df(n=200, base_price=50000.0, trend=0.001, seed=123)


class TestFullBacktestRun:
    """Integration test for a full backtest run."""

    def test_full_backtest_run(self, ohlcv_data):
        """Run a complete backtest and verify all outputs are valid."""
        config = GridConfig(grid_levels=5, grid_spacing_pct=2.0, amount_per_level=0.001)
        strategy = GridStrategy(symbol="BTC/USDT", config=config)

        engine = BacktestEngine(
            symbol="BTC/USDT",
            timeframe="1d",
            initial_balance=10000.0,
            commission=0.001,
            slippage=0.0005,
        )

        result = engine.run(strategy=strategy, data=ohlcv_data)

        # Verify result is complete
        assert isinstance(result, BacktestResult)
        assert result.symbol == "BTC/USDT"
        assert result.timeframe == "1d"
        assert result.initial_balance == 10000.0
        assert result.duration_days > 0
        assert result.start_date is not None
        assert result.end_date is not None

        # Equity curve must have one value per candle
        assert len(result.equity_curve) == len(ohlcv_data)
        assert len(result.drawdown_curve) == len(ohlcv_data)

        # Daily returns derived from equity curve
        assert len(result.daily_returns) == len(ohlcv_data) - 1

        # Metrics are finite (not NaN)
        assert result.sharpe_ratio == result.sharpe_ratio  # not NaN
        assert result.sortino_ratio == result.sortino_ratio
        assert result.max_drawdown >= 0

        # to_dict / JSON serialization round-trip
        d = result.to_dict()
        json_str = json.dumps(d, default=str)
        loaded = json.loads(json_str)
        assert loaded["symbol"] == "BTC/USDT"
        assert loaded["initial_balance"] == 10000.0

    def test_backtest_result_save_load(self, ohlcv_data):
        """Save backtest result to JSON and reload it."""
        config = GridConfig(grid_levels=5, grid_spacing_pct=1.5, amount_per_level=0.001)
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        engine = BacktestEngine(symbol="BTC/USDT", timeframe="1d")

        result = engine.run(strategy=strategy, data=ohlcv_data)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmpfile = f.name

        path = Path(tmpfile)
        with open(path, "w") as f:
            json.dump(result.to_dict(), f, indent=2, default=str)

        assert path.exists()
        with open(path) as f:
            saved = json.load(f)

        assert saved["symbol"] == "BTC/USDT"
        assert saved["initial_balance"] == 10000.0
        assert "equity_curve" in saved
        assert "drawdown_curve" in saved
        assert "daily_returns" in saved
        assert "max_drawdown_duration" in saved

        path.unlink()


class TestBenchmarkComparison:
    """Integration test for strategy benchmarking."""

    def test_benchmark_comparison(self, ohlcv_data):
        """Compare multiple strategies and verify outputs."""
        strategies = []
        for levels in [5, 10, 15]:
            config = GridConfig(grid_levels=levels, grid_spacing_pct=1.5, amount_per_level=0.001)
            strategies.append(GridStrategy(symbol="BTC/USDT", config=config))

        bench = StrategyBenchmark(
            symbol="BTC/USDT",
            timeframe="1d",
            initial_balance=10000.0,
        )

        params_list = [
            {"name": "5-level"},
            {"name": "10-level"},
            {"name": "15-level"},
        ]

        comp = bench.compare(strategies, ohlcv_data, params_list)

        assert "results" in comp
        assert "comparison_table" in comp
        assert len(comp["results"]) == 3
        assert isinstance(comp["comparison_table"], str)

        # Results are sorted by return (descending)
        returns = [r.total_return for r in comp["results"]]
        assert returns == sorted(returns, reverse=True)


class TestBacktestWithOptimizationParams:
    """Test backtest integration with optimization parameters."""

    def test_backtest_with_optimization_params(self, ohlcv_data):
        """Run backtest with params dict (like optimizer would provide)."""
        params = {
            "name": "optimized",
            "grid_levels": 8,
            "grid_spacing_pct": 1.2,
            "amount_per_level": 0.002,
        }

        config = GridConfig(
            grid_levels=params["grid_levels"],
            grid_spacing_pct=params["grid_spacing_pct"],
            amount_per_level=params["amount_per_level"],
        )
        strategy = GridStrategy(symbol="BTC/USDT", config=config)

        engine = BacktestEngine(
            symbol="BTC/USDT",
            timeframe="1d",
            initial_balance=10000.0,
        )

        result = engine.run(strategy=strategy, data=ohlcv_data, params=params)

        assert result.config_name == "optimized"
        assert result.params == params
        assert result.total_trades >= 0
        assert isinstance(result.total_return, float)

    def test_legacy_backtester_still_works(self, ohlcv_data):
        """Ensure the legacy Backtester class still functions correctly."""
        from shared.backtest.engine import Backtester

        config = GridConfig(grid_levels=5, grid_spacing_pct=2.0, amount_per_level=0.001)
        strategy = GridStrategy(symbol="BTC/USDT", config=config)
        backtester = Backtester(initial_balance=10000.0, commission=0.001)

        result = backtester.run(strategy=strategy, data=ohlcv_data)

        assert isinstance(result, BacktestResult)
        assert result.initial_balance == 10000.0
        assert result.total_trades >= 0
        assert isinstance(result.equity_curve, list)
        # Legacy equity_curve entries are dicts
        if result.equity_curve:
            assert isinstance(result.equity_curve[0], dict)
            assert "equity" in result.equity_curve[0]
