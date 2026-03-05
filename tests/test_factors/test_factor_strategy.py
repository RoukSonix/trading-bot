"""Tests for factor_strategy module."""

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


def _make_ohlcv_df(n: int = 100, base_price: float = 50000.0, trend: float = 0.0) -> pd.DataFrame:
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=n, freq="1D")
    returns = np.random.normal(trend, 0.02, n)
    prices = base_price * np.cumprod(1 + returns)
    return pd.DataFrame({
        "open": prices * (1 + np.random.uniform(-0.005, 0.005, n)),
        "high": prices * (1 + np.abs(np.random.normal(0, 0.01, n))),
        "low": prices * (1 - np.abs(np.random.normal(0, 0.01, n))),
        "close": prices,
        "volume": np.random.uniform(100, 1000, n),
    }, index=dates)


class TestFactorStrategy:
    """Tests for FactorStrategy."""

    def test_score_basic(self):
        strategy = FactorStrategy()
        df = _make_ohlcv_df(100)
        factors, score = strategy.analyze_and_score(df, "BTC/USDT")

        assert isinstance(score, FactorScore)
        assert -1.0 <= score.trade_score <= 1.0
        assert 0.0 <= score.grid_suitability <= 1.0
        assert 0.0 <= score.risk_score <= 1.0
        assert isinstance(score.regime, MarketRegime)
        assert isinstance(score.action, GridAction)

    def test_regime_detection_uptrend(self):
        strategy = FactorStrategy()
        df = _make_ohlcv_df(100, trend=0.01)  # Strong uptrend
        factors, score = strategy.analyze_and_score(df, "BTC/USDT")

        # Strong uptrend should be detected
        assert score.regime in (MarketRegime.TRENDING_UP, MarketRegime.HIGH_VOLATILITY)

    def test_regime_detection_ranging(self):
        strategy = FactorStrategy()
        # Flat market (no trend, low volatility)
        np.random.seed(123)
        dates = pd.date_range("2025-01-01", periods=100, freq="1D")
        prices = 50000 + np.random.normal(0, 100, 100).cumsum()
        # Keep prices bounded
        prices = np.clip(prices, 48000, 52000)
        df = pd.DataFrame({
            "open": prices,
            "high": prices * 1.003,
            "low": prices * 0.997,
            "close": prices,
            "volume": np.random.uniform(100, 200, 100),
        }, index=dates)

        factors, score = strategy.analyze_and_score(df, "BTC/USDT")
        # Should detect ranging or low volatility
        assert score.regime in (MarketRegime.RANGING, MarketRegime.LOW_VOLATILITY)

    def test_grid_suitability_ranging_market(self):
        """Ranging markets should have higher grid suitability."""
        strategy = FactorStrategy()

        # Create a ranging market factor result
        ranging_factors = FactorResult(
            symbol="BTC/USDT",
            momentum_score=0.05,  # Near zero = no trend
            volatility_score=0.35,  # Moderate volatility
            rsi_14=48.0,  # Near 50 = neutral
            rsi_signal=0.0,
            volume_sma_ratio=1.0,
        )
        score = strategy.score(ranging_factors)
        assert score.grid_suitability >= 0.5

    def test_grid_suitability_high_vol(self):
        """High volatility should reduce grid suitability."""
        strategy = FactorStrategy()

        high_vol = FactorResult(
            symbol="BTC/USDT",
            momentum_score=0.0,
            volatility_score=0.8,
            rsi_14=50.0,
            rsi_signal=0.0,
            volume_sma_ratio=1.0,
        )
        score = strategy.score(high_vol)
        assert score.grid_suitability < 0.5

    def test_pause_action_when_unsuitable(self):
        """Should recommend PAUSE when suitability is very low."""
        strategy = FactorStrategy(grid_suitability_threshold=0.4)

        bad_factors = FactorResult(
            symbol="BTC/USDT",
            momentum_score=0.8,  # Strong trend
            volatility_score=0.9,  # Extreme volatility
            rsi_14=85.0,  # Overbought
            rsi_signal=1.0,
            volume_sma_ratio=3.0,  # Abnormal volume
        )
        score = strategy.score(bad_factors)
        assert score.action == GridAction.PAUSE

    def test_risk_score_bounds(self):
        strategy = FactorStrategy()

        # Low risk scenario
        low_risk = FactorResult(
            symbol="BTC/USDT",
            momentum_score=0.0,
            volatility_score=0.1,
            rsi_14=50.0,
            volume_sma_ratio=1.0,
        )
        score = strategy.score(low_risk)
        assert score.risk_score < 0.5

        # High risk scenario
        high_risk = FactorResult(
            symbol="BTC/USDT",
            momentum_score=0.9,
            volatility_score=0.9,
            rsi_14=85.0,
            volume_sma_ratio=3.0,
        )
        score = strategy.score(high_risk)
        assert score.risk_score > 0.5

    def test_reasoning_not_empty(self):
        strategy = FactorStrategy()
        df = _make_ohlcv_df(100)
        _, score = strategy.analyze_and_score(df, "BTC/USDT")
        assert len(score.reasoning) > 0

    def test_to_ai_context(self):
        strategy = FactorStrategy()
        df = _make_ohlcv_df(100)
        factors, score = strategy.analyze_and_score(df, "BTC/USDT")
        context = strategy.to_ai_context(factors, score)

        assert "Factor Analysis" in context
        assert "Momentum" in context
        assert "Volatility" in context
        assert "Grid Recommendation" in context

    def test_widen_action_in_high_vol(self):
        """High volatility should trigger WIDEN or PAUSE."""
        strategy = FactorStrategy()

        high_vol_ranging = FactorResult(
            symbol="BTC/USDT",
            momentum_score=0.0,
            volatility_score=0.75,  # High but not extreme
            rsi_14=50.0,
            rsi_signal=0.0,
            volume_sma_ratio=1.0,
        )
        score = strategy.score(high_vol_ranging)
        assert score.action in (GridAction.WIDEN, GridAction.PAUSE)
