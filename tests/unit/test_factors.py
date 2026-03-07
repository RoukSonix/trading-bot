"""Unit tests for factor analysis (momentum, volatility, composite score)."""

import numpy as np
import pandas as pd
import pytest

from shared.factors.factor_calculator import FactorCalculator, FactorResult
from shared.factors.factor_strategy import (
    FactorScore,
    FactorStrategy,
    GridAction,
    MarketRegime,
)
from tests.conftest import make_ohlcv_df


class TestMomentumCalculation:
    """Tests for momentum factor calculation."""

    def test_positive_momentum_uptrend(self):
        df = make_ohlcv_df(100, trend=0.005)
        calc = FactorCalculator()
        result = calc.calculate(df, "BTC/USDT")

        assert result.momentum_60d > 0
        assert result.momentum_20d > 0
        assert result.momentum_5d > 0
        assert result.momentum_score > 0

    def test_negative_momentum_downtrend(self):
        df = make_ohlcv_df(100, trend=-0.005)
        calc = FactorCalculator()
        result = calc.calculate(df, "BTC/USDT")

        assert result.momentum_60d < 0
        assert result.momentum_20d < 0
        assert result.momentum_score < 0

    def test_momentum_score_bounded(self):
        df = make_ohlcv_df(100, trend=0.01)
        calc = FactorCalculator()
        result = calc.calculate(df, "BTC/USDT")

        assert -1.0 <= result.momentum_score <= 1.0

    def test_momentum_custom_weights(self):
        df = make_ohlcv_df(100, trend=0.003)
        calc_60 = FactorCalculator(momentum_weights=(1.0, 0.0, 0.0))
        calc_5 = FactorCalculator(momentum_weights=(0.0, 0.0, 1.0))

        r60 = calc_60.calculate(df, "BTC/USDT")
        r5 = calc_5.calculate(df, "BTC/USDT")

        assert r60.momentum_score != r5.momentum_score

    def test_insufficient_data_returns_defaults(self):
        df = make_ohlcv_df(10)
        calc = FactorCalculator()
        result = calc.calculate(df, "BTC/USDT")

        assert result.momentum_60d == 0.0
        assert result.momentum_20d == 0.0
        assert result.composite_score == 0.0


class TestVolatilityCalculation:
    """Tests for volatility factor calculation."""

    def test_volatility_positive(self):
        df = make_ohlcv_df(100)
        calc = FactorCalculator()
        result = calc.calculate(df, "BTC/USDT")

        assert result.atr_14 > 0
        assert result.atr_pct > 0
        assert result.std_dev_20 > 0

    def test_volatility_score_bounded(self):
        df = make_ohlcv_df(100)
        calc = FactorCalculator()
        result = calc.calculate(df, "BTC/USDT")

        assert 0.0 <= result.volatility_score <= 1.0

    def test_rsi_bounded(self):
        df = make_ohlcv_df(100)
        calc = FactorCalculator()
        result = calc.calculate(df, "BTC/USDT")

        assert 0 <= result.rsi_14 <= 100

    def test_rsi_signal_bounded(self):
        df = make_ohlcv_df(100)
        calc = FactorCalculator()
        result = calc.calculate(df, "BTC/USDT")

        assert -1.0 <= result.rsi_signal <= 1.0


class TestCompositeScore:
    """Tests for composite factor score."""

    def test_composite_score_bounded(self):
        df = make_ohlcv_df(100)
        calc = FactorCalculator()
        result = calc.calculate(df, "BTC/USDT")

        assert -1.0 <= result.composite_score <= 1.0

    def test_composite_uses_all_factors(self):
        df = make_ohlcv_df(100)
        calc = FactorCalculator()
        result = calc.calculate(df, "BTC/USDT")

        # All sub-scores should be populated
        assert result.momentum_score != 0.0 or result.volatility_score != 0.0
        assert result.rsi_14 != 50.0 or result.volume_score != 0.0

    def test_custom_composite_weights(self):
        df = make_ohlcv_df(100)
        calc1 = FactorCalculator(composite_weights={
            "momentum": 1.0, "volatility": 0.0, "rsi": 0.0, "volume": 0.0,
        })
        calc2 = FactorCalculator(composite_weights={
            "momentum": 0.0, "volatility": 0.0, "rsi": 1.0, "volume": 0.0,
        })

        r1 = calc1.calculate(df, "BTC/USDT")
        r2 = calc2.calculate(df, "BTC/USDT")

        assert r1.composite_score != r2.composite_score

    def test_no_volume_column(self):
        df = make_ohlcv_df(100)
        df = df.drop(columns=["volume"])
        calc = FactorCalculator()
        result = calc.calculate(df, "BTC/USDT")

        assert result.volume_sma_ratio == 1.0
        assert result.volume_score == 0.0

    def test_to_dict_fields(self):
        df = make_ohlcv_df(100)
        calc = FactorCalculator()
        result = calc.calculate(df, "BTC/USDT")
        d = calc.to_dict(result)

        assert "Momentum (60d)" in d
        assert "ATR (14)" in d
        assert "RSI (14)" in d
        assert "Volume Ratio" in d
        assert "Composite Score" in d


class TestFactorStrategy:
    """Tests for factor strategy scoring."""

    def _get_factors(self, trend: float = 0.0) -> FactorResult:
        df = make_ohlcv_df(100, trend=trend)
        calc = FactorCalculator()
        return calc.calculate(df, "BTC/USDT")

    def test_score_returns_factor_score(self):
        factors = self._get_factors()
        strategy = FactorStrategy()
        score = strategy.score(factors)

        assert isinstance(score, FactorScore)
        assert isinstance(score.regime, MarketRegime)
        assert isinstance(score.action, GridAction)

    def test_trade_score_bounded(self):
        factors = self._get_factors()
        strategy = FactorStrategy()
        score = strategy.score(factors)

        assert -1.0 <= score.trade_score <= 1.0

    def test_grid_suitability_bounded(self):
        factors = self._get_factors()
        strategy = FactorStrategy()
        score = strategy.score(factors)

        assert 0.0 <= score.grid_suitability <= 1.0

    def test_risk_score_bounded(self):
        factors = self._get_factors()
        strategy = FactorStrategy()
        score = strategy.score(factors)

        assert 0.0 <= score.risk_score <= 1.0

    def test_reasoning_not_empty(self):
        factors = self._get_factors()
        strategy = FactorStrategy()
        score = strategy.score(factors)

        assert len(score.reasoning) > 0
        assert "Market regime" in score.reasoning

    def test_uptrend_regime(self):
        factors = self._get_factors(trend=0.008)
        strategy = FactorStrategy()
        score = strategy.score(factors)

        assert score.regime in (MarketRegime.TRENDING_UP, MarketRegime.HIGH_VOLATILITY)

    def test_low_suitability_pauses(self):
        # Use a threshold impossibly high so suitability always falls below it
        strategy = FactorStrategy(grid_suitability_threshold=2.0)
        factors = self._get_factors()
        score = strategy.score(factors)

        # With impossibly high threshold, should recommend pause
        assert score.action == GridAction.PAUSE

    def test_to_ai_context(self):
        factors = self._get_factors()
        strategy = FactorStrategy()
        score = strategy.score(factors)
        context = strategy.to_ai_context(factors, score)

        assert "Factor Analysis" in context
        assert "Market Regime" in context
        assert "Momentum" in context
        assert "Volatility" in context
        assert "Grid Recommendation" in context

    def test_analyze_and_score(self):
        df = make_ohlcv_df(100)
        strategy = FactorStrategy()
        factors, score = strategy.analyze_and_score(df, "BTC/USDT")

        assert isinstance(factors, FactorResult)
        assert isinstance(score, FactorScore)
