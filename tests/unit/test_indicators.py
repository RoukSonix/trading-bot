"""Unit tests for technical indicators."""

import numpy as np
import pandas as pd
import pytest

from shared.core.indicators import Indicators
from tests.conftest import make_ohlcv_df


class TestSMA:
    """Tests for Simple Moving Average."""

    def test_sma_basic(self, ohlcv_df):
        result = Indicators.sma(ohlcv_df, period=20)
        assert isinstance(result, pd.Series)
        assert len(result) == len(ohlcv_df)
        # First 19 values should be NaN
        assert result.iloc[:19].isna().all()
        # 20th value onward should be valid
        assert not np.isnan(result.iloc[19])

    def test_sma_value(self):
        """SMA of constant series should equal that constant."""
        df = pd.DataFrame({"close": [100.0] * 30})
        result = Indicators.sma(df, period=10)
        assert result.iloc[-1] == pytest.approx(100.0)

    def test_sma_custom_period(self, ohlcv_df):
        sma_5 = Indicators.sma(ohlcv_df, period=5)
        sma_50 = Indicators.sma(ohlcv_df, period=50)
        # Shorter period should have fewer NaN values
        assert sma_5.notna().sum() > sma_50.notna().sum()


class TestEMA:
    """Tests for Exponential Moving Average."""

    def test_ema_basic(self, ohlcv_df):
        result = Indicators.ema(ohlcv_df, period=20)
        assert isinstance(result, pd.Series)
        assert len(result) == len(ohlcv_df)
        # EMA should have no NaN (ewm doesn't produce NaN by default)
        assert result.notna().all()

    def test_ema_value(self):
        """EMA of constant series should equal that constant."""
        df = pd.DataFrame({"close": [100.0] * 30})
        result = Indicators.ema(df, period=10)
        assert result.iloc[-1] == pytest.approx(100.0)

    def test_ema_responds_faster(self, ohlcv_df):
        """EMA should react faster to recent changes than SMA."""
        ema = Indicators.ema(ohlcv_df, period=20)
        sma = Indicators.sma(ohlcv_df, period=20)
        # EMA follows price more closely, so |close - EMA| < |close - SMA| on average
        close = ohlcv_df["close"]
        valid = sma.notna()
        ema_diff = (close[valid] - ema[valid]).abs().mean()
        sma_diff = (close[valid] - sma[valid]).abs().mean()
        assert ema_diff <= sma_diff


class TestRSI:
    """Tests for Relative Strength Index."""

    def test_rsi_range(self, ohlcv_df):
        result = Indicators.rsi(ohlcv_df, period=14)
        valid = result.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_rsi_uptrend(self, ohlcv_df_uptrend):
        result = Indicators.rsi(ohlcv_df_uptrend, period=14)
        # In an uptrend, RSI should tend to be above 50
        valid = result.dropna()
        assert valid.iloc[-1] > 50

    def test_rsi_downtrend(self, ohlcv_df_downtrend):
        result = Indicators.rsi(ohlcv_df_downtrend, period=14)
        # In a downtrend, RSI should tend to be below 50
        valid = result.dropna()
        assert valid.iloc[-1] < 50

    def test_rsi_constant_price(self):
        """RSI of constant price should be ~50 (undefined)."""
        df = pd.DataFrame({"close": [100.0] * 50})
        result = Indicators.rsi(df, period=14)
        # With zero change, RSI is undefined but should not crash
        assert len(result) == 50


class TestBollingerBands:
    """Tests for Bollinger Bands."""

    def test_bollinger_bands_structure(self, ohlcv_df):
        upper, middle, lower = Indicators.bollinger_bands(ohlcv_df)
        assert isinstance(upper, pd.Series)
        assert isinstance(middle, pd.Series)
        assert isinstance(lower, pd.Series)
        assert len(upper) == len(ohlcv_df)

    def test_bollinger_bands_ordering(self, ohlcv_df):
        upper, middle, lower = Indicators.bollinger_bands(ohlcv_df)
        valid = upper.notna() & middle.notna() & lower.notna()
        assert (upper[valid] >= middle[valid]).all()
        assert (middle[valid] >= lower[valid]).all()

    def test_bollinger_middle_is_sma(self, ohlcv_df):
        _, middle, _ = Indicators.bollinger_bands(ohlcv_df, period=20)
        sma = Indicators.sma(ohlcv_df, period=20)
        valid = middle.notna() & sma.notna()
        pd.testing.assert_series_equal(middle[valid], sma[valid])

    def test_bollinger_custom_std_dev(self, ohlcv_df):
        upper_2, _, lower_2 = Indicators.bollinger_bands(ohlcv_df, std_dev=2.0)
        upper_3, _, lower_3 = Indicators.bollinger_bands(ohlcv_df, std_dev=3.0)
        valid = upper_2.notna() & upper_3.notna()
        # Wider std_dev = wider bands
        assert (upper_3[valid] >= upper_2[valid]).all()
        assert (lower_3[valid] <= lower_2[valid]).all()


class TestMACD:
    """Tests for MACD indicator."""

    def test_macd_structure(self, ohlcv_df):
        macd_line, signal_line, histogram = Indicators.macd(ohlcv_df)
        assert isinstance(macd_line, pd.Series)
        assert isinstance(signal_line, pd.Series)
        assert isinstance(histogram, pd.Series)
        assert len(macd_line) == len(ohlcv_df)

    def test_macd_histogram_is_difference(self, ohlcv_df):
        macd_line, signal_line, histogram = Indicators.macd(ohlcv_df)
        expected = macd_line - signal_line
        pd.testing.assert_series_equal(histogram, expected)

    def test_macd_uptrend(self, ohlcv_df_uptrend):
        macd_line, _, _ = Indicators.macd(ohlcv_df_uptrend)
        # In uptrend, MACD should be positive (fast EMA > slow EMA)
        assert macd_line.iloc[-1] > 0


class TestATR:
    """Tests for Average True Range."""

    def test_atr_positive(self, ohlcv_df):
        result = Indicators.atr(ohlcv_df, period=14)
        valid = result.dropna()
        assert (valid > 0).all()

    def test_atr_length(self, ohlcv_df):
        result = Indicators.atr(ohlcv_df, period=14)
        assert len(result) == len(ohlcv_df)


class TestAddAllIndicators:
    """Tests for add_all_indicators convenience method."""

    def test_adds_all_columns(self, ohlcv_df):
        result = Indicators.add_all_indicators(ohlcv_df)
        expected_cols = [
            "sma_20", "sma_50", "ema_12", "ema_26",
            "rsi", "bb_upper", "bb_middle", "bb_lower",
            "macd", "macd_signal", "macd_hist", "atr",
        ]
        for col in expected_cols:
            assert col in result.columns, f"Missing column: {col}"

    def test_does_not_modify_original(self, ohlcv_df):
        original_cols = set(ohlcv_df.columns)
        Indicators.add_all_indicators(ohlcv_df)
        assert set(ohlcv_df.columns) == original_cols


class TestToDataframe:
    """Tests for candle list to DataFrame conversion."""

    def test_to_dataframe_with_ms_timestamp(self):
        candles = [
            {"timestamp": 1700000000000, "open": 100, "high": 105, "low": 95, "close": 102, "volume": 50},
            {"timestamp": 1700003600000, "open": 102, "high": 108, "low": 100, "close": 106, "volume": 60},
        ]
        df = Indicators.to_dataframe(candles)
        assert isinstance(df.index, pd.DatetimeIndex)
        assert len(df) == 2
        assert "close" in df.columns

    def test_to_dataframe_with_s_timestamp(self):
        candles = [
            {"timestamp": 1700000000, "open": 100, "high": 105, "low": 95, "close": 102, "volume": 50},
        ]
        df = Indicators.to_dataframe(candles)
        assert isinstance(df.index, pd.DatetimeIndex)
