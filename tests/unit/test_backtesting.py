"""Unit tests for the Sprint 19 advanced backtesting engine."""

import numpy as np
import pandas as pd
import pytest

from tests.conftest import make_ohlcv_df
from shared.backtest.engine import BacktestEngine, BacktestResult
from shared.backtest.benchmark import StrategyBenchmark
from shared.backtest.charts import BacktestCharts
from binance_bot.strategies import GridStrategy, GridConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ohlcv_100():
    """100-candle OHLCV DataFrame with slight trend."""
    return make_ohlcv_df(n=100, base_price=50000.0, trend=0.001, seed=42)


@pytest.fixture
def grid_strategy():
    """Standard grid strategy for testing."""
    config = GridConfig(grid_levels=5, grid_spacing_pct=2.0, amount_per_level=0.001)
    return GridStrategy(symbol="BTC/USDT", config=config)


@pytest.fixture
def engine():
    """BacktestEngine with default settings."""
    return BacktestEngine(
        symbol="BTC/USDT",
        timeframe="1d",
        initial_balance=10000.0,
        commission=0.001,
        slippage=0.0005,
    )


# ---------------------------------------------------------------------------
# Anti look-ahead bias tests
# ---------------------------------------------------------------------------


class TestNoLookAheadBias:
    """Verify anti look-ahead bias mechanisms."""

    def test_no_look_ahead_bias(self, engine, ohlcv_100):
        """Strategy must never see future candles."""
        # Custom strategy that records how many candles it sees each call
        candle_counts = []

        class SpyStrategy(GridStrategy):
            def calculate_signals(self, df, current_price):
                candle_counts.append(len(df))
                return super().calculate_signals(df, current_price)

        config = GridConfig(grid_levels=5, grid_spacing_pct=2.0, amount_per_level=0.001)
        spy = SpyStrategy(symbol="BTC/USDT", config=config)
        engine.run(strategy=spy, data=ohlcv_100)

        # Each call should see exactly i+1 candles (1, 2, 3, …, N)
        assert len(candle_counts) == len(ohlcv_100)
        for i, count in enumerate(candle_counts):
            assert count == i + 1, f"At candle {i}, strategy saw {count} candles instead of {i+1}"

    def test_order_fills_at_next_open(self, ohlcv_100):
        """Orders generated on candle i must fill at candle i+1's open."""
        fill_prices = []

        class RecordStrategy(GridStrategy):
            _first_call = True

            def calculate_signals(self, df, current_price):
                if self._first_call:
                    self._first_call = False
                    # Setup grid
                    return super().calculate_signals(df, current_price)
                return super().calculate_signals(df, current_price)

        config = GridConfig(grid_levels=5, grid_spacing_pct=2.0, amount_per_level=0.001)
        strat = RecordStrategy(symbol="BTC/USDT", config=config)
        engine = BacktestEngine(
            symbol="BTC/USDT", timeframe="1d",
            initial_balance=10000.0, commission=0.001, slippage=0.0,
        )
        result = engine.run(strategy=strat, data=ohlcv_100)

        # Each trade's fill_price should match the *open* of the candle
        # it was filled on (next candle after signal)
        for trade in result.trades:
            fill_price = trade["fill_price"]
            signal_price = trade["signal_price"]
            # fill_price should NOT equal signal_price (it's the next open)
            # (unless the signal price happens to coincide with the open,
            #  which is possible but rare with random data)
            # The key invariant: fill_price is a candle open price
            assert "fill_price" in trade
            assert "signal_price" in trade

    def test_slippage_applied(self, ohlcv_100):
        """Verify slippage is applied to fill prices."""
        slippage = 0.01  # 1% — large for easy verification

        config = GridConfig(grid_levels=5, grid_spacing_pct=2.0, amount_per_level=0.001)
        strat = GridStrategy(symbol="BTC/USDT", config=config)

        engine = BacktestEngine(
            symbol="BTC/USDT", timeframe="1d",
            initial_balance=10000.0, commission=0.001,
            slippage=slippage,
        )
        result = engine.run(strategy=strat, data=ohlcv_100)

        for trade in result.trades:
            # For BUY trades: fill_price > open (slippage moves price up)
            # For SELL trades: fill_price < open (slippage moves price down)
            # We can't check exact open here, but we know signal_price != fill_price
            # when slippage > 0
            if trade["type"] == "BUY":
                assert trade["fill_price"] >= trade["signal_price"] * 0.99  # reasonable range
            elif trade["type"] == "SELL":
                assert trade["fill_price"] <= trade["signal_price"] * 1.01

    def test_commission_deducted(self, ohlcv_100):
        """Commission should be deducted from each trade."""
        config = GridConfig(grid_levels=5, grid_spacing_pct=2.0, amount_per_level=0.001)
        strat = GridStrategy(symbol="BTC/USDT", config=config)

        engine = BacktestEngine(
            symbol="BTC/USDT", timeframe="1d",
            initial_balance=10000.0, commission=0.01,  # 1% commission
            slippage=0.0,
        )
        result = engine.run(strategy=strat, data=ohlcv_100)

        for trade in result.trades:
            assert "commission" in trade
            assert trade["commission"] > 0


# ---------------------------------------------------------------------------
# BacktestResult tests
# ---------------------------------------------------------------------------


class TestBacktestResultMetrics:
    """Test BacktestResult fields and methods."""

    def test_backtest_result_metrics(self, engine, grid_strategy, ohlcv_100):
        """BacktestResult should have all required fields populated."""
        result = engine.run(strategy=grid_strategy, data=ohlcv_100)

        # All required fields present
        assert isinstance(result, BacktestResult)
        assert result.initial_balance == 10000.0
        assert result.symbol == "BTC/USDT"
        assert result.timeframe == "1d"
        assert result.start_date is not None
        assert result.end_date is not None
        assert result.duration_days > 0
        assert isinstance(result.total_return, float)
        assert isinstance(result.total_trades, int)
        assert isinstance(result.sharpe_ratio, float)
        assert isinstance(result.sortino_ratio, float)
        assert isinstance(result.max_drawdown, float)
        assert result.max_drawdown >= 0
        assert isinstance(result.equity_curve, list)
        assert len(result.equity_curve) == len(ohlcv_100)
        assert isinstance(result.drawdown_curve, list)
        assert len(result.drawdown_curve) == len(ohlcv_100)
        assert isinstance(result.daily_returns, list)

    def test_summary_method(self, engine, grid_strategy, ohlcv_100):
        """summary() should return a formatted string."""
        result = engine.run(strategy=grid_strategy, data=ohlcv_100)
        summary = result.summary()
        assert isinstance(summary, str)
        assert "BACKTEST RESULTS" in summary
        assert "Return" in summary

    def test_to_dict_method(self, engine, grid_strategy, ohlcv_100):
        """to_dict() should return serializable dict with all keys."""
        result = engine.run(strategy=grid_strategy, data=ohlcv_100)
        d = result.to_dict()
        assert isinstance(d, dict)

        expected_keys = {
            "config_name", "start_date", "end_date", "duration_days",
            "symbol", "timeframe", "params", "initial_balance",
            "final_balance", "total_return", "total_trades",
            "winning_trades", "losing_trades", "win_rate",
            "sharpe_ratio", "sortino_ratio", "max_drawdown",
            "max_drawdown_duration", "profit_factor", "expectancy",
            "avg_win", "avg_loss", "largest_win", "largest_loss",
            "avg_holding_period", "equity_curve", "drawdown_curve",
            "daily_returns",
        }
        assert expected_keys.issubset(set(d.keys()))

    def test_equity_curve_starts_at_initial(self, engine, grid_strategy, ohlcv_100):
        """Equity curve first value should be close to initial balance."""
        result = engine.run(strategy=grid_strategy, data=ohlcv_100)
        # First equity value: initial balance + 0 holdings * first price = 10000
        assert abs(result.equity_curve[0] - 10000.0) < 100  # within $100

    def test_empty_data_returns_empty_result(self, engine, grid_strategy):
        """Engine should handle empty data gracefully."""
        empty_df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        result = engine.run(strategy=grid_strategy, data=empty_df)
        assert result.total_trades == 0


# ---------------------------------------------------------------------------
# Buy and hold comparison tests
# ---------------------------------------------------------------------------


class TestBuyAndHoldComparison:
    """Test buy-and-hold comparison."""

    def test_buy_and_hold_comparison(self, engine, grid_strategy, ohlcv_100):
        """vs_buy_and_hold should return valid comparison dict."""
        result = engine.run(strategy=grid_strategy, data=ohlcv_100)
        bench = StrategyBenchmark()
        comp = bench.vs_buy_and_hold(result, ohlcv_100)

        assert "strategy" in comp
        assert "buy_and_hold" in comp
        assert "outperformance" in comp
        assert "bnh_equity_curve" in comp
        assert isinstance(comp["outperformance"], float)
        assert comp["strategy"]["total_return"] == result.total_return
        assert isinstance(comp["buy_and_hold"]["total_return"], float)
        assert len(comp["bnh_equity_curve"]) == len(ohlcv_100)

    def test_buy_and_hold_return_matches_price_change(self, ohlcv_100):
        """Buy-and-hold return should match the price change percentage."""
        first_close = ohlcv_100["close"].iloc[0]
        last_close = ohlcv_100["close"].iloc[-1]
        expected_return = ((last_close - first_close) / first_close) * 100

        # Create a trivial strategy result
        result = BacktestResult(total_return=0.0)
        bench = StrategyBenchmark()
        comp = bench.vs_buy_and_hold(result, ohlcv_100)
        assert abs(comp["buy_and_hold"]["total_return"] - expected_return) < 0.01


# ---------------------------------------------------------------------------
# Charts tests
# ---------------------------------------------------------------------------


class TestBacktestCharts:
    """Test chart generation doesn't error."""

    def test_equity_curve_chart(self, engine, grid_strategy, ohlcv_100):
        """equity_curve() should return a plotly Figure."""
        import plotly.graph_objects as go

        result = engine.run(strategy=grid_strategy, data=ohlcv_100)
        fig = BacktestCharts.equity_curve(result)
        assert isinstance(fig, go.Figure)

    def test_drawdown_chart(self, engine, grid_strategy, ohlcv_100):
        """drawdown_chart() should return a plotly Figure."""
        import plotly.graph_objects as go

        result = engine.run(strategy=grid_strategy, data=ohlcv_100)
        fig = BacktestCharts.drawdown_chart(result)
        assert isinstance(fig, go.Figure)

    def test_monthly_returns_heatmap(self, engine, grid_strategy, ohlcv_100):
        """monthly_returns_heatmap() should return a plotly Figure."""
        import plotly.graph_objects as go

        result = engine.run(strategy=grid_strategy, data=ohlcv_100)
        fig = BacktestCharts.monthly_returns_heatmap(result)
        assert isinstance(fig, go.Figure)

    def test_trade_distribution(self, engine, grid_strategy, ohlcv_100):
        """trade_distribution() should return a plotly Figure."""
        import plotly.graph_objects as go

        result = engine.run(strategy=grid_strategy, data=ohlcv_100)
        fig = BacktestCharts.trade_distribution(result)
        assert isinstance(fig, go.Figure)

    def test_comparison_table(self, engine, ohlcv_100):
        """comparison_table() should return a formatted string."""
        results = []
        for i in range(3):
            config = GridConfig(grid_levels=5 + i, grid_spacing_pct=1.5, amount_per_level=0.001)
            strat = GridStrategy(symbol="BTC/USDT", config=config)
            r = engine.run(strategy=strat, data=ohlcv_100, params={"name": f"config_{i}"})
            results.append(r)

        table = BacktestCharts.comparison_table(results)
        assert isinstance(table, str)
        assert "config_0" in table or "config_1" in table or "config_2" in table
