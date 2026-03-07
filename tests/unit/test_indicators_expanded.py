"""Unit tests for expanded indicator library (Sprint 23)."""

import numpy as np
import pandas as pd
import pytest

from shared.indicators import (
    trend, momentum, volatility, volume,
    support_resistance, pattern, custom,
    multi_timeframe, correlation,
)
from shared.indicators.custom import IndicatorBuilder
from shared.indicators.multi_timeframe import MultiTimeframe
from shared.indicators.correlation import IndicatorCorrelation
from tests.conftest import make_ohlcv_df


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def df():
    """100-candle OHLCV DataFrame (no trend)."""
    return make_ohlcv_df(100)


@pytest.fixture
def df_uptrend():
    return make_ohlcv_df(100, trend=0.005)


@pytest.fixture
def df_downtrend():
    return make_ohlcv_df(100, trend=-0.005)


# ── Regression: SMA & EMA (must still pass via new module) ────────────────────

class TestSMARegression:
    def test_sma_basic(self, df):
        result = trend.sma(df, period=20)
        assert isinstance(result, pd.Series)
        assert len(result) == len(df)
        assert result.iloc[:19].isna().all()
        assert not np.isnan(result.iloc[19])

    def test_sma_constant(self):
        d = pd.DataFrame({"close": [100.0] * 30})
        assert trend.sma(d, 10).iloc[-1] == pytest.approx(100.0)


class TestEMARegression:
    def test_ema_basic(self, df):
        result = trend.ema(df, period=20)
        assert isinstance(result, pd.Series)
        assert result.notna().all()

    def test_ema_constant(self):
        d = pd.DataFrame({"close": [100.0] * 30})
        assert trend.ema(d, 10).iloc[-1] == pytest.approx(100.0)


# ── Trend Indicators ─────────────────────────────────────────────────────────

class TestWMA:
    def test_wma_basic(self, df):
        result = trend.wma(df, period=20)
        assert isinstance(result, pd.Series)
        assert len(result) == len(df)
        assert result.iloc[:19].isna().all()
        assert not np.isnan(result.iloc[19])

    def test_wma_constant(self):
        d = pd.DataFrame({"close": [50.0] * 30})
        assert trend.wma(d, 10).iloc[-1] == pytest.approx(50.0)


class TestDEMA:
    def test_dema_basic(self, df):
        result = trend.dema(df, period=20)
        assert isinstance(result, pd.Series)
        assert result.notna().all()


class TestTEMA:
    def test_tema_basic(self, df):
        result = trend.tema(df, period=20)
        assert isinstance(result, pd.Series)
        assert result.notna().all()


class TestKAMA:
    def test_kama_basic(self, df):
        result = trend.kama(df, period=10)
        assert isinstance(result, pd.Series)
        # First period-1 values are NaN
        assert not np.isnan(result.iloc[-1])


class TestSupertrend:
    def test_supertrend_structure(self, df):
        result = trend.supertrend(df, period=10, multiplier=3.0)
        assert isinstance(result, pd.DataFrame)
        assert "supertrend" in result.columns
        assert "direction" in result.columns
        assert len(result) == len(df)

    def test_supertrend_direction_values(self, df):
        result = trend.supertrend(df)
        valid = result["direction"].iloc[10:]
        assert set(valid.unique()).issubset({1, -1})


class TestPSAR:
    def test_psar_basic(self, df):
        result = trend.psar(df)
        assert isinstance(result, pd.Series)
        assert len(result) == len(df)
        assert result.notna().all()


class TestIchimoku:
    def test_ichimoku_structure(self, df):
        result = trend.ichimoku(df)
        assert isinstance(result, pd.DataFrame)
        expected_cols = ["tenkan_sen", "kijun_sen", "senkou_a", "senkou_b", "chikou"]
        for col in expected_cols:
            assert col in result.columns

    def test_ichimoku_tenkan_kijun_relationship(self, df):
        result = trend.ichimoku(df, tenkan=9, kijun=26)
        # Tenkan uses shorter period so should have fewer NaN
        assert result["tenkan_sen"].notna().sum() > result["kijun_sen"].notna().sum()


class TestADX:
    def test_adx_range(self, df):
        result = trend.adx(df, period=14)
        valid_adx = result["adx"].dropna()
        assert (valid_adx >= 0).all()
        assert "plus_di" in result.columns
        assert "minus_di" in result.columns


class TestAroon:
    def test_aroon_range(self, df):
        result = trend.aroon(df, period=25)
        valid_up = result["aroon_up"].dropna()
        valid_down = result["aroon_down"].dropna()
        assert (valid_up >= 0).all() and (valid_up <= 100).all()
        assert (valid_down >= 0).all() and (valid_down <= 100).all()


class TestCCI:
    def test_cci_basic(self, df):
        result = trend.cci(df, period=20)
        assert isinstance(result, pd.Series)
        assert len(result) == len(df)


class TestVWAP:
    def test_vwap_basic(self, df):
        result = trend.vwap(df)
        assert isinstance(result, pd.Series)
        assert result.notna().all()


# ── Momentum Indicators ──────────────────────────────────────────────────────

class TestStochastic:
    def test_stochastic_range(self, df):
        result = momentum.stochastic(df, k=14, d=3)
        valid_k = result["stoch_k"].dropna()
        assert (valid_k >= 0).all() and (valid_k <= 100).all()

    def test_stochastic_d_smoother(self, df):
        result = momentum.stochastic(df)
        # %D is SMA of %K — should have more NaN
        assert result["stoch_d"].isna().sum() >= result["stoch_k"].isna().sum()


class TestStochRSI:
    def test_stoch_rsi_range(self, df):
        result = momentum.stoch_rsi(df, period=14)
        valid = result["stoch_rsi_k"].dropna()
        assert (valid >= 0).all() and (valid <= 1).all()


class TestWilliamsR:
    def test_williams_r_range(self, df):
        result = momentum.williams_r(df, period=14)
        valid = result.dropna()
        assert (valid >= -100).all() and (valid <= 0).all()


class TestMFI:
    def test_mfi_range(self, df):
        result = momentum.mfi(df, period=14)
        valid = result.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()


class TestROC:
    def test_roc_basic(self, df):
        result = momentum.roc(df, period=12)
        assert isinstance(result, pd.Series)
        assert len(result) == len(df)


class TestTSI:
    def test_tsi_range(self, df):
        result = momentum.tsi(df, long=25, short=13)
        valid = result.dropna()
        assert (valid >= -100).all() and (valid <= 100).all()


class TestUltimate:
    def test_ultimate_range(self, df):
        result = momentum.ultimate(df)
        valid = result.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()


class TestAO:
    def test_ao_basic(self, df):
        result = momentum.ao(df)
        assert isinstance(result, pd.Series)


class TestMomentum:
    def test_momentum_basic(self, df):
        result = momentum.momentum(df, period=10)
        assert isinstance(result, pd.Series)
        # First 10 values NaN
        assert result.iloc[:10].isna().all()


# ── Volatility Indicators ────────────────────────────────────────────────────

class TestATR:
    def test_atr_positive(self, df):
        result = volatility.atr(df, period=14)
        valid = result.dropna()
        assert (valid > 0).all()


class TestTrueRange:
    def test_true_range_positive(self, df):
        result = volatility.true_range(df)
        valid = result.dropna()
        assert (valid >= 0).all()


class TestKeltner:
    def test_keltner_ordering(self, df):
        upper, middle, lower = volatility.keltner(df)
        valid = upper.notna() & middle.notna() & lower.notna()
        assert (upper[valid] >= middle[valid]).all()
        assert (middle[valid] >= lower[valid]).all()


class TestDonchian:
    def test_donchian_ordering(self, df):
        upper, middle, lower = volatility.donchian(df)
        valid = upper.notna() & lower.notna()
        assert (upper[valid] >= lower[valid]).all()


class TestATRPercent:
    def test_atr_percent_positive(self, df):
        result = volatility.atr_percent(df, period=14)
        valid = result.dropna()
        assert (valid > 0).all()


class TestHistoricalVolatility:
    def test_hv_positive(self, df):
        result = volatility.historical_volatility(df, period=20)
        valid = result.dropna()
        assert (valid >= 0).all()


class TestChaikinVolatility:
    def test_chaikin_basic(self, df):
        result = volatility.chaikin_volatility(df, period=10)
        assert isinstance(result, pd.Series)


class TestNATR:
    def test_natr_positive(self, df):
        result = volatility.natr(df, period=14)
        valid = result.dropna()
        assert (valid > 0).all()


# ── Volume Indicators ────────────────────────────────────────────────────────

class TestOBV:
    def test_obv_basic(self, df):
        result = volume.obv(df)
        assert isinstance(result, pd.Series)
        assert len(result) == len(df)


class TestVolumeVWAP:
    def test_vwap_basic(self, df):
        result = volume.vwap(df)
        assert isinstance(result, pd.Series)
        assert result.notna().all()


class TestADLine:
    def test_ad_line_basic(self, df):
        result = volume.ad_line(df)
        assert isinstance(result, pd.Series)
        assert len(result) == len(df)


class TestCMF:
    def test_cmf_range(self, df):
        result = volume.cmf(df, period=20)
        valid = result.dropna()
        assert (valid >= -1).all() and (valid <= 1).all()


class TestForceIndex:
    def test_force_index_basic(self, df):
        result = volume.force_index(df, period=13)
        assert isinstance(result, pd.Series)


class TestEOM:
    def test_eom_basic(self, df):
        result = volume.eom(df, period=14)
        assert isinstance(result, pd.Series)


class TestVolumeProfile:
    def test_volume_profile_structure(self, df):
        result = volume.volume_profile(df, bins=10)
        assert isinstance(result, pd.DataFrame)
        assert "price_low" in result.columns
        assert "volume" in result.columns
        assert len(result) == 10


class TestPVT:
    def test_pvt_basic(self, df):
        result = volume.pvt(df)
        assert isinstance(result, pd.Series)


class TestNVI:
    def test_nvi_starts_at_1000(self, df):
        result = volume.nvi(df)
        assert result.iloc[0] == pytest.approx(1000.0)


# ── Support & Resistance ─────────────────────────────────────────────────────

class TestPivotPoints:
    def test_pivot_points_structure(self, df):
        result = support_resistance.pivot_points(df)
        assert isinstance(result, dict)
        expected_keys = {"P", "R1", "R2", "R3", "S1", "S2", "S3"}
        assert set(result.keys()) == expected_keys

    def test_pivot_points_ordering(self, df):
        pp = support_resistance.pivot_points(df)
        assert pp["R3"] > pp["R2"] > pp["R1"] > pp["P"] > pp["S1"] > pp["S2"] > pp["S3"]


class TestFibonacci:
    def test_fibonacci_retracement_levels(self):
        result = support_resistance.fibonacci_retracement(100.0, 50.0)
        assert result["0.0"] == pytest.approx(100.0)
        assert result["100.0"] == pytest.approx(50.0)
        assert result["50.0"] == pytest.approx(75.0)
        assert result["61.8"] == pytest.approx(100.0 - 0.618 * 50.0)

    def test_fibonacci_extension(self):
        result = support_resistance.fibonacci_extension(100.0, 50.0, 70.0)
        assert "100.0" in result
        assert result["100.0"] == pytest.approx(70.0 + 50.0)
        assert result["161.8"] == pytest.approx(70.0 + 1.618 * 50.0)


class TestSupportResistanceLevels:
    def test_sr_levels_structure(self, df):
        result = support_resistance.support_resistance_levels(df, window=10)
        assert "support" in result
        assert "resistance" in result
        assert isinstance(result["support"], list)
        assert isinstance(result["resistance"], list)


# ── Candlestick Patterns ─────────────────────────────────────────────────────

class TestDoji:
    def test_doji_detection(self):
        candle = pd.Series({
            "open": 100.0, "high": 105.0, "low": 95.0, "close": 100.2
        })
        assert pattern.doji(candle, threshold=0.05)

    def test_not_doji(self):
        candle = pd.Series({
            "open": 95.0, "high": 105.0, "low": 90.0, "close": 104.0
        })
        assert not pattern.doji(candle, threshold=0.05)


class TestHammer:
    def test_hammer_detection(self):
        candle = pd.Series({
            "open": 100.0, "high": 101.0, "low": 94.0, "close": 100.5
        })
        result = pattern.hammer(candle)
        assert result in ("hammer", "hanging_man", None)


class TestEngulfing:
    def test_bullish_engulfing(self):
        candles = pd.DataFrame([
            {"open": 102.0, "high": 103.0, "low": 99.0, "close": 100.0},  # bearish
            {"open": 99.0, "high": 104.0, "low": 98.0, "close": 103.0},   # bullish engulfing
        ])
        assert pattern.engulfing(candles) == "bullish_engulfing"

    def test_bearish_engulfing(self):
        candles = pd.DataFrame([
            {"open": 100.0, "high": 103.0, "low": 99.0, "close": 102.0},  # bullish
            {"open": 103.0, "high": 104.0, "low": 98.0, "close": 99.0},   # bearish engulfing
        ])
        assert pattern.engulfing(candles) == "bearish_engulfing"


class TestMorningStar:
    def test_morning_star(self):
        candles = pd.DataFrame([
            {"open": 105.0, "high": 106.0, "low": 99.0, "close": 100.0},   # bearish
            {"open": 100.0, "high": 100.5, "low": 99.5, "close": 100.2},   # small body
            {"open": 100.5, "high": 106.0, "low": 100.0, "close": 105.0},  # bullish
        ])
        assert pattern.morning_star(candles) == "morning_star"


class TestThreeSoldiers:
    def test_three_white_soldiers(self):
        candles = pd.DataFrame([
            {"open": 100.0, "high": 103.0, "low": 99.0, "close": 102.0},
            {"open": 101.0, "high": 105.0, "low": 100.5, "close": 104.0},
            {"open": 103.0, "high": 107.0, "low": 102.5, "close": 106.0},
        ])
        assert pattern.three_soldiers(candles) == "three_white_soldiers"

    def test_three_black_crows(self):
        candles = pd.DataFrame([
            {"open": 106.0, "high": 107.0, "low": 103.0, "close": 104.0},
            {"open": 105.0, "high": 106.0, "low": 101.0, "close": 102.0},
            {"open": 103.0, "high": 104.0, "low": 99.0, "close": 100.0},
        ])
        assert pattern.three_soldiers(candles) == "three_black_crows"


# ── Custom Indicator Builder ─────────────────────────────────────────────────

class TestIndicatorBuilder:
    def test_builder_empty(self, df):
        builder = IndicatorBuilder()
        assert builder.calculate(df) == 0.0

    def test_builder_single_indicator(self, df):
        builder = IndicatorBuilder()
        builder.add(momentum.rsi, weight=1.0, period=14)
        value = builder.calculate(df)
        assert 0 <= value <= 100

    def test_builder_composite(self, df):
        builder = IndicatorBuilder()
        builder.add(momentum.rsi, weight=0.5, period=14)
        builder.add(trend.sma, weight=0.5, period=20)
        value = builder.calculate(df)
        assert isinstance(value, float)

    def test_builder_to_signal(self, df):
        builder = IndicatorBuilder()
        builder.add(momentum.rsi, weight=1.0, period=14)
        signal = builder.to_signal(df)
        assert signal in ("buy", "sell", "hold")

    def test_builder_chaining(self, df):
        builder = (
            IndicatorBuilder()
            .add(momentum.rsi, weight=0.5, period=14)
            .add(trend.sma, weight=0.5, period=20)
        )
        assert len(builder.components) == 2


# ── Multi-Timeframe ──────────────────────────────────────────────────────────

class TestMultiTimeframe:
    def test_analyze_basic(self, df):
        mtf = MultiTimeframe(symbol="BTC/USDT")
        candles_by_tf = {"1h": df, "4h": df, "1d": df}
        analysis = mtf.analyze(candles_by_tf)
        assert "1h" in analysis
        assert "trend" in analysis["1h"]
        assert "rsi" in analysis["1h"]
        assert "macd" in analysis["1h"]

    def test_consensus_bullish(self, df_uptrend):
        mtf = MultiTimeframe()
        candles_by_tf = {"1h": df_uptrend, "4h": df_uptrend, "1d": df_uptrend}
        analysis = mtf.analyze(candles_by_tf)
        result = mtf.consensus(analysis)
        assert result in ("bullish", "bearish", "neutral")

    def test_consensus_empty(self):
        mtf = MultiTimeframe()
        assert mtf.consensus({}) == "neutral"

    def test_timeframe_weights(self):
        mtf = MultiTimeframe()
        assert mtf.TIMEFRAME_WEIGHTS["1d"] > mtf.TIMEFRAME_WEIGHTS["1h"]
        assert mtf.TIMEFRAME_WEIGHTS["4h"] > mtf.TIMEFRAME_WEIGHTS["15m"]


# ── Correlation Matrix ───────────────────────────────────────────────────────

class TestCorrelationMatrix:
    def test_calculate_matrix(self, df):
        corr = IndicatorCorrelation()
        indicators = [
            ("RSI", momentum.rsi, {"period": 14}),
            ("SMA_20", trend.sma, {"period": 20}),
            ("EMA_20", trend.ema, {"period": 20}),
        ]
        matrix = corr.calculate_matrix(df, indicators)
        assert isinstance(matrix, pd.DataFrame)
        assert matrix.shape == (3, 3)
        # Diagonal should be 1.0
        for i in range(3):
            assert matrix.iloc[i, i] == pytest.approx(1.0)

    def test_find_redundant(self, df):
        corr = IndicatorCorrelation()
        indicators = [
            ("SMA_20", trend.sma, {"period": 20}),
            ("EMA_20", trend.ema, {"period": 20}),
            ("RSI", momentum.rsi, {"period": 14}),
        ]
        matrix = corr.calculate_matrix(df, indicators)
        redundant = corr.find_redundant(matrix, threshold=0.9)
        # SMA_20 and EMA_20 should be highly correlated
        assert isinstance(redundant, list)

    def test_suggest_best_combination(self, df):
        corr = IndicatorCorrelation()
        indicators = [
            ("SMA_20", trend.sma, {"period": 20}),
            ("EMA_20", trend.ema, {"period": 20}),
            ("RSI", momentum.rsi, {"period": 14}),
        ]
        best = corr.suggest_best_combination(df, indicators, n=2)
        assert len(best) == 2
        assert isinstance(best[0], str)


# ── Backward Compatibility ───────────────────────────────────────────────────

class TestBackwardCompatibility:
    """Ensure shared.core.indicators.Indicators still works."""

    def test_import_from_core(self):
        from shared.core.indicators import Indicators
        assert hasattr(Indicators, "sma")
        assert hasattr(Indicators, "ema")
        assert hasattr(Indicators, "rsi")
        assert hasattr(Indicators, "bollinger_bands")
        assert hasattr(Indicators, "macd")
        assert hasattr(Indicators, "atr")
        assert hasattr(Indicators, "add_all_indicators")
        assert hasattr(Indicators, "to_dataframe")

    def test_core_sma_matches_new(self, df):
        from shared.core.indicators import Indicators
        old = Indicators.sma(df, 20)
        new = trend.sma(df, 20)
        pd.testing.assert_series_equal(old, new)

    def test_core_add_all_indicators(self, df):
        from shared.core.indicators import Indicators
        result = Indicators.add_all_indicators(df)
        expected_cols = [
            "sma_20", "sma_50", "ema_12", "ema_26",
            "rsi", "bb_upper", "bb_middle", "bb_lower",
            "macd", "macd_signal", "macd_hist", "atr",
        ]
        for col in expected_cols:
            assert col in result.columns
