"""Tests for factor_calculator module."""

import numpy as np
import pandas as pd
import pytest

from shared.factors.factor_calculator import FactorCalculator, FactorResult


def _make_ohlcv_df(n: int = 100, base_price: float = 50000.0, trend: float = 0.0) -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing.

    Args:
        n: Number of candles.
        base_price: Starting price.
        trend: Daily drift (e.g., 0.001 = +0.1% per day).
    """
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=n, freq="1D")
    returns = np.random.normal(trend, 0.02, n)
    prices = base_price * np.cumprod(1 + returns)

    df = pd.DataFrame({
        "open": prices * (1 + np.random.uniform(-0.005, 0.005, n)),
        "high": prices * (1 + np.abs(np.random.normal(0, 0.01, n))),
        "low": prices * (1 - np.abs(np.random.normal(0, 0.01, n))),
        "close": prices,
        "volume": np.random.uniform(100, 1000, n),
    }, index=dates)

    return df


class TestFactorCalculator:
    """Tests for FactorCalculator."""

    def test_basic_calculation(self):
        df = _make_ohlcv_df(100)
        calc = FactorCalculator()
        result = calc.calculate(df, "BTC/USDT")

        assert isinstance(result, FactorResult)
        assert result.symbol == "BTC/USDT"
        assert result.timestamp is not None

    def test_momentum_factors(self):
        # Uptrend: positive momentum
        df_up = _make_ohlcv_df(100, trend=0.005)
        calc = FactorCalculator()
        result = calc.calculate(df_up, "BTC/USDT")

        assert result.momentum_60d > 0
        assert result.momentum_20d > 0
        assert result.momentum_score > 0

    def test_momentum_downtrend(self):
        df_down = _make_ohlcv_df(100, trend=-0.005)
        calc = FactorCalculator()
        result = calc.calculate(df_down, "BTC/USDT")

        assert result.momentum_60d < 0
        assert result.momentum_score < 0

    def test_volatility_factors(self):
        df = _make_ohlcv_df(100)
        calc = FactorCalculator()
        result = calc.calculate(df, "BTC/USDT")

        assert result.atr_14 > 0
        assert result.atr_pct > 0
        assert result.std_dev_20 > 0
        assert 0.0 <= result.volatility_score <= 1.0

    def test_rsi_factors(self):
        df = _make_ohlcv_df(100)
        calc = FactorCalculator()
        result = calc.calculate(df, "BTC/USDT")

        assert 0 <= result.rsi_14 <= 100
        assert -1.0 <= result.rsi_signal <= 1.0

    def test_volume_factors(self):
        df = _make_ohlcv_df(100)
        calc = FactorCalculator()
        result = calc.calculate(df, "BTC/USDT")

        assert result.volume_sma_ratio > 0
        assert -1.0 <= result.obv_trend <= 1.0
        assert -1.0 <= result.volume_score <= 1.0

    def test_composite_score_bounded(self):
        df = _make_ohlcv_df(100)
        calc = FactorCalculator()
        result = calc.calculate(df, "BTC/USDT")

        assert -1.0 <= result.composite_score <= 1.0

    def test_insufficient_data(self):
        df = _make_ohlcv_df(10)  # Less than 20 rows
        calc = FactorCalculator()
        result = calc.calculate(df, "BTC/USDT")

        # Should return default values
        assert result.momentum_60d == 0.0
        assert result.composite_score == 0.0

    def test_minimal_data_20_rows(self):
        df = _make_ohlcv_df(20)
        calc = FactorCalculator()
        result = calc.calculate(df, "BTC/USDT")

        # Should work with exactly 20 rows
        assert result.momentum_20d != 0.0

    def test_custom_weights(self):
        df = _make_ohlcv_df(100, trend=0.003)
        calc1 = FactorCalculator(momentum_weights=(1.0, 0.0, 0.0))  # Only 60d
        calc2 = FactorCalculator(momentum_weights=(0.0, 0.0, 1.0))  # Only 5d

        r1 = calc1.calculate(df, "BTC/USDT")
        r2 = calc2.calculate(df, "BTC/USDT")

        # Different weights should yield different momentum scores
        assert r1.momentum_score != r2.momentum_score

    def test_to_dict(self):
        df = _make_ohlcv_df(100)
        calc = FactorCalculator()
        result = calc.calculate(df, "BTC/USDT")
        d = calc.to_dict(result)

        assert "Momentum (60d)" in d
        assert "ATR (14)" in d
        assert "RSI (14)" in d
        assert "Volume Ratio" in d
        assert "Composite Score" in d

    def test_no_volume_column(self):
        df = _make_ohlcv_df(100)
        df = df.drop(columns=["volume"])
        calc = FactorCalculator()
        result = calc.calculate(df, "BTC/USDT")

        # Volume factors should be defaults
        assert result.volume_sma_ratio == 1.0
        assert result.volume_score == 0.0
