"""Integration tests for factor analysis pipeline.

Tests: OHLCV data -> Calculate factors -> Verify factors passed to strategy.
"""

import numpy as np
import pandas as pd
import pytest

from shared.core.indicators import Indicators
from shared.factors.factor_calculator import FactorCalculator, FactorResult
from shared.factors.factor_strategy import (
    FactorScore,
    FactorStrategy,
    GridAction,
    MarketRegime,
)
from tests.conftest import make_ohlcv_df


@pytest.mark.integration
class TestFactorIntegration:
    """Integration: Fetch OHLCV -> Calculate factors -> Verify passed to AI."""

    def test_ohlcv_to_factors_pipeline(self):
        """Generate OHLCV -> Add indicators -> Calculate factors."""
        # Step 1: Create OHLCV data (simulating fetch)
        df = make_ohlcv_df(100, base_price=50000.0)

        # Step 2: Add technical indicators
        df_with_indicators = Indicators.add_all_indicators(df)
        assert "rsi" in df_with_indicators.columns
        assert "macd" in df_with_indicators.columns

        # Step 3: Calculate factors
        calc = FactorCalculator()
        factors = calc.calculate(df_with_indicators, "BTC/USDT")

        assert isinstance(factors, FactorResult)
        assert factors.symbol == "BTC/USDT"
        assert factors.atr_14 > 0
        assert 0 <= factors.rsi_14 <= 100

    def test_factors_to_strategy_pipeline(self):
        """Factors -> Strategy scoring -> Grid recommendations."""
        df = make_ohlcv_df(100, base_price=50000.0)
        strategy = FactorStrategy()

        # One-call pipeline
        factors, score = strategy.analyze_and_score(df, "BTC/USDT")

        assert isinstance(factors, FactorResult)
        assert isinstance(score, FactorScore)
        assert isinstance(score.regime, MarketRegime)
        assert isinstance(score.action, GridAction)
        assert 0.0 <= score.grid_suitability <= 1.0
        assert 0.0 <= score.risk_score <= 1.0

    def test_factors_to_ai_context(self):
        """Factors + Score -> AI context string for prompts."""
        df = make_ohlcv_df(100, base_price=50000.0)
        strategy = FactorStrategy()
        factors, score = strategy.analyze_and_score(df, "BTC/USDT")

        context = strategy.to_ai_context(factors, score)

        assert isinstance(context, str)
        assert "Factor Analysis" in context
        assert "Market Regime" in context
        assert "ATR%" in context
        assert "Grid Recommendation" in context
        assert score.regime.value in context

    def test_uptrend_produces_bullish_factors(self):
        """Strong uptrend should produce positive momentum and bullish signals."""
        df = make_ohlcv_df(100, base_price=50000.0, trend=0.008)
        strategy = FactorStrategy()
        factors, score = strategy.analyze_and_score(df, "BTC/USDT")

        assert factors.momentum_score > 0
        assert factors.momentum_20d > 0
        assert score.trade_score > 0

    def test_downtrend_produces_bearish_factors(self):
        """Strong downtrend should produce negative momentum."""
        df = make_ohlcv_df(100, base_price=50000.0, trend=-0.008)
        strategy = FactorStrategy()
        factors, score = strategy.analyze_and_score(df, "BTC/USDT")

        assert factors.momentum_score < 0
        assert factors.momentum_20d < 0
        assert score.trade_score < 0

    def test_from_candles_list(self):
        """Test factor calculation from raw candle dicts (simulating API response)."""
        np.random.seed(42)
        base_ts = 1700000000000
        candles = []
        price = 50000.0
        for i in range(100):
            change = np.random.normal(0, 0.02)
            price *= (1 + change)
            candles.append({
                "timestamp": base_ts + i * 86400000,
                "open": price * 0.999,
                "high": price * 1.01,
                "low": price * 0.99,
                "close": price,
                "volume": np.random.uniform(100, 1000),
            })

        calc = FactorCalculator()
        result = calc.calculate_from_candles(candles, "BTC/USDT")

        assert isinstance(result, FactorResult)
        assert result.atr_14 > 0
        assert -1.0 <= result.composite_score <= 1.0

    def test_factor_dict_for_ai_prompt(self):
        """Test that factor dict contains all fields needed for AI prompts."""
        df = make_ohlcv_df(100, base_price=50000.0)
        calc = FactorCalculator()
        result = calc.calculate(df, "BTC/USDT")
        d = calc.to_dict(result)

        required_fields = [
            "Momentum (60d)", "Momentum (20d)", "Momentum (5d)", "Momentum Score",
            "ATR (14)", "ATR %", "Volatility (20d StdDev)", "Volatility Score",
            "RSI (14)", "RSI Signal", "RSI Divergence",
            "Volume Ratio", "OBV Trend", "Volume Score",
            "Composite Score",
        ]
        for field in required_fields:
            assert field in d, f"Missing field: {field}"
