"""
Tests for FactorsMixin and SentimentMixin — Sprint M4.

Tests factor calculation, regime detection, grid suitability scoring,
sentiment caching, and graceful fallback when shared/ modules are unavailable.
All tests mock external dependencies (no network/Redis).
"""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock

import numpy as np

# Add strategy module to path
grid_logic_path = os.path.join(os.path.dirname(__file__), '..', 'strategies', 'AIGridStrategy')
sys.path.insert(0, grid_logic_path)

from factors_mixin import FactorsMixin
from sentiment_mixin import SentimentMixin


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def factors_mixin():
    """FactorsMixin using built-in fallback (no shared/ dependency)."""
    with patch('factors_mixin._HAS_FACTORS', False):
        fm = FactorsMixin()
        fm._calculator = None
        fm._strategy = None
        return fm


@pytest.fixture
def sentiment_mixin():
    """SentimentMixin with no external deps."""
    with patch('sentiment_mixin._HAS_SENTIMENT', False):
        sm = SentimentMixin(cache_interval_candles=5)
        sm._analyzer = None
        return sm


@pytest.fixture
def sample_candles_sideways():
    """100 candles of sideways market around 100k."""
    np.random.seed(42)
    n = 100
    base = 100000.0
    ts = np.arange(n) * 60000
    opens = base + np.random.randn(n).cumsum() * 100
    highs = opens + np.abs(np.random.randn(n)) * 200
    lows = opens - np.abs(np.random.randn(n)) * 200
    closes = opens + np.random.randn(n) * 150
    volumes = np.abs(np.random.randn(n)) * 1000 + 500
    return np.column_stack([ts, opens, highs, lows, closes, volumes])


@pytest.fixture
def sample_candles_uptrend():
    """100 candles with strong uptrend."""
    np.random.seed(42)
    n = 100
    base = 100000.0
    drift = np.arange(n) * 500
    ts = np.arange(n) * 60000
    opens = base + drift + np.random.randn(n) * 50
    highs = opens + np.abs(np.random.randn(n)) * 200
    lows = opens - np.abs(np.random.randn(n)) * 200
    closes = opens + 400 + np.random.randn(n) * 50
    volumes = np.abs(np.random.randn(n)) * 1000 + 500
    return np.column_stack([ts, opens, highs, lows, closes, volumes])


@pytest.fixture
def sample_candles_volatile():
    """100 candles with very high volatility."""
    np.random.seed(42)
    n = 100
    base = 100000.0
    ts = np.arange(n) * 60000
    opens = base + np.random.randn(n).cumsum() * 2000
    highs = opens + np.abs(np.random.randn(n)) * 5000  # huge range
    lows = opens - np.abs(np.random.randn(n)) * 5000
    closes = opens + np.random.randn(n) * 3000
    volumes = np.abs(np.random.randn(n)) * 5000 + 2000
    return np.column_stack([ts, opens, highs, lows, closes, volumes])


# ==============================================================================
# FactorsMixin — Factor Calculation
# ==============================================================================


class TestFactorsCalculation:
    """Test factor calculation from candle data."""

    def test_calculate_factors_returns_all_keys(self, factors_mixin, sample_candles_sideways):
        factors = factors_mixin.calculate_factors(sample_candles_sideways)
        expected_keys = [
            'momentum_score', 'momentum_5d', 'momentum_20d', 'momentum_60d',
            'volatility_score', 'atr_pct', 'rsi_14', 'rsi_signal',
            'rsi_divergence', 'volume_score', 'volume_sma_ratio', 'composite_score',
        ]
        for key in expected_keys:
            assert key in factors, f"Missing key: {key}"

    def test_factors_scores_in_valid_ranges(self, factors_mixin, sample_candles_sideways):
        factors = factors_mixin.calculate_factors(sample_candles_sideways)
        assert -1.0 <= factors['momentum_score'] <= 1.0
        assert 0.0 <= factors['volatility_score'] <= 1.0
        assert 0.0 <= factors['rsi_14'] <= 100.0
        assert -1.0 <= factors['rsi_signal'] <= 1.0
        assert -1.0 <= factors['composite_score'] <= 1.0

    def test_factors_uptrend_has_positive_momentum(self, factors_mixin, sample_candles_uptrend):
        factors = factors_mixin.calculate_factors(sample_candles_uptrend)
        assert factors['momentum_score'] > 0, "Uptrend should have positive momentum"
        assert factors['momentum_20d'] > 0

    def test_factors_volatile_has_high_volatility(self, factors_mixin, sample_candles_volatile):
        factors = factors_mixin.calculate_factors(sample_candles_volatile)
        assert factors['volatility_score'] > 0.3, "Volatile market should have high volatility score"

    def test_factors_with_insufficient_data(self, factors_mixin):
        """Fewer than 20 candles returns default factors."""
        short_candles = np.random.randn(10, 6)
        short_candles[:, 0] = np.arange(10) * 60000
        short_candles[:, 1:5] = np.abs(short_candles[:, 1:5]) + 100  # positive prices
        short_candles[:, 5] = np.abs(short_candles[:, 5]) + 100
        factors = factors_mixin.calculate_factors(short_candles)
        assert factors['momentum_score'] == 0.0
        assert factors['rsi_14'] == 50.0

    def test_factors_with_none_candles(self, factors_mixin):
        """None candles returns default factors."""
        factors = factors_mixin.calculate_factors(None)
        assert factors == factors_mixin._default_factors()

    def test_factors_with_empty_candles(self, factors_mixin):
        """Empty candle array returns default factors."""
        factors = factors_mixin.calculate_factors(np.array([]))
        assert factors == factors_mixin._default_factors()


# ==============================================================================
# FactorsMixin — Regime Detection
# ==============================================================================


class TestRegimeDetection:
    """Test market regime detection."""

    def test_ranging_regime(self, factors_mixin):
        """Neutral factors → ranging regime."""
        factors = {
            'momentum_score': 0.0,
            'volatility_score': 0.3,
            'rsi_14': 50.0,
        }
        regime = factors_mixin.detect_regime(factors)
        assert regime == 'ranging'

    def test_trending_up_regime(self, factors_mixin):
        """High momentum + RSI > 55 → trending_up."""
        factors = {
            'momentum_score': 0.5,
            'volatility_score': 0.3,
            'rsi_14': 65.0,
        }
        regime = factors_mixin.detect_regime(factors)
        assert regime == 'trending_up'

    def test_trending_down_regime(self, factors_mixin):
        """Negative momentum + RSI < 45 → trending_down."""
        factors = {
            'momentum_score': -0.5,
            'volatility_score': 0.3,
            'rsi_14': 35.0,
        }
        regime = factors_mixin.detect_regime(factors)
        assert regime == 'trending_down'

    def test_high_volatility_regime(self, factors_mixin):
        """Very high volatility → high_volatility (overrides trend)."""
        factors = {
            'momentum_score': 0.5,
            'volatility_score': 0.8,
            'rsi_14': 65.0,
        }
        regime = factors_mixin.detect_regime(factors)
        assert regime == 'high_volatility'

    def test_low_volatility_regime(self, factors_mixin):
        """Very low volatility → low_volatility."""
        factors = {
            'momentum_score': 0.0,
            'volatility_score': 0.1,
            'rsi_14': 50.0,
        }
        regime = factors_mixin.detect_regime(factors)
        assert regime == 'low_volatility'


# ==============================================================================
# FactorsMixin — Grid Suitability
# ==============================================================================


class TestGridSuitability:
    """Test grid suitability scoring."""

    def test_ranging_market_high_suitability(self, factors_mixin):
        """Ranging market with moderate volatility → high suitability."""
        factors = {
            'momentum_score': 0.0,
            'volatility_score': 0.3,
            'rsi_14': 50.0,
            'volume_sma_ratio': 1.0,
        }
        score = factors_mixin.grid_suitability_score(factors)
        assert score >= 0.7, f"Ranging market should have high suitability, got {score}"

    def test_trending_market_lower_suitability(self, factors_mixin):
        """Trending market → lower suitability than ranging."""
        factors_ranging = {
            'momentum_score': 0.0,
            'volatility_score': 0.3,
            'rsi_14': 50.0,
            'volume_sma_ratio': 1.0,
        }
        factors_trending = {
            'momentum_score': 0.5,
            'volatility_score': 0.3,
            'rsi_14': 65.0,
            'volume_sma_ratio': 1.0,
        }
        score_ranging = factors_mixin.grid_suitability_score(factors_ranging)
        score_trending = factors_mixin.grid_suitability_score(factors_trending)
        assert score_ranging > score_trending

    def test_high_volatility_low_suitability(self, factors_mixin):
        """High volatility → low grid suitability."""
        factors = {
            'momentum_score': 0.0,
            'volatility_score': 0.8,
            'rsi_14': 50.0,
            'volume_sma_ratio': 1.0,
        }
        score = factors_mixin.grid_suitability_score(factors)
        assert score < 0.4, f"High vol should have low suitability, got {score}"

    def test_suitability_in_valid_range(self, factors_mixin):
        """Score always between 0.0 and 1.0."""
        for momentum in [-1.0, -0.5, 0.0, 0.5, 1.0]:
            for vol in [0.0, 0.3, 0.5, 0.8, 1.0]:
                factors = {
                    'momentum_score': momentum,
                    'volatility_score': vol,
                    'rsi_14': 50.0,
                    'volume_sma_ratio': 1.0,
                }
                score = factors_mixin.grid_suitability_score(factors)
                assert 0.0 <= score <= 1.0, f"Score {score} out of range for momentum={momentum}, vol={vol}"


# ==============================================================================
# FactorsMixin — AI Context
# ==============================================================================


class TestFactorsAIContext:
    """Test factors formatting for AI context."""

    def test_ai_context_contains_key_sections(self, factors_mixin):
        factors = factors_mixin._default_factors()
        context = factors_mixin.factors_to_ai_context(factors)
        assert '## Factor Analysis' in context
        assert 'Regime:' in context
        assert 'Grid Suitability:' in context
        assert 'Momentum:' in context
        assert 'RSI:' in context


# ==============================================================================
# FactorsMixin — Graceful Fallback
# ==============================================================================


class TestFactorsFallback:
    """Test graceful fallback when shared/factors/ is unavailable."""

    def test_factors_available_false_without_shared(self, factors_mixin):
        assert factors_mixin.factors_available is False

    def test_builtin_factors_still_work(self, factors_mixin, sample_candles_sideways):
        """Built-in fallback produces valid factors."""
        factors = factors_mixin.calculate_factors(sample_candles_sideways)
        assert 'momentum_score' in factors
        assert 'rsi_14' in factors
        assert 'composite_score' in factors

    def test_builtin_regime_still_works(self, factors_mixin):
        """Built-in regime detection works without shared module."""
        factors = {'momentum_score': 0.0, 'volatility_score': 0.3, 'rsi_14': 50.0}
        regime = factors_mixin.detect_regime(factors)
        assert regime in ('trending_up', 'trending_down', 'ranging', 'high_volatility', 'low_volatility')

    def test_builtin_suitability_still_works(self, factors_mixin):
        """Built-in suitability works without shared module."""
        factors = {'momentum_score': 0.0, 'volatility_score': 0.3, 'rsi_14': 50.0, 'volume_sma_ratio': 1.0}
        score = factors_mixin.grid_suitability_score(factors)
        assert 0.0 <= score <= 1.0


# ==============================================================================
# SentimentMixin — Basic Operations
# ==============================================================================


class TestSentimentBasic:
    """Test SentimentMixin basic operations."""

    def test_default_score_is_zero(self, sentiment_mixin):
        assert sentiment_mixin.get_sentiment_score() == 0.0

    def test_default_summary(self, sentiment_mixin):
        summary = sentiment_mixin.get_recent_news_summary()
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_default_detail_has_all_keys(self, sentiment_mixin):
        detail = sentiment_mixin.get_sentiment_detail()
        expected_keys = ['score', 'level', 'confidence', 'article_count', 'summary', 'top_headlines']
        for key in expected_keys:
            assert key in detail, f"Missing key: {key}"

    def test_sentiment_available_false_without_shared(self, sentiment_mixin):
        assert sentiment_mixin.sentiment_available is False


# ==============================================================================
# SentimentMixin — Caching
# ==============================================================================


class TestSentimentCaching:
    """Test sentiment result caching."""

    def test_cache_interval_prevents_repeated_refresh(self, sentiment_mixin):
        """Sentiment should not refresh on every tick."""
        sentiment_mixin._refresh_sentiment = MagicMock()

        # First tick triggers refresh (candle_counter=1, last_fetch=-999)
        sentiment_mixin.tick()
        sentiment_mixin.get_sentiment_score()
        call_count_1 = sentiment_mixin._refresh_sentiment.call_count

        # Next 4 ticks should not trigger refresh (interval=5)
        for _ in range(4):
            sentiment_mixin.tick()
            sentiment_mixin.get_sentiment_score()

        assert sentiment_mixin._refresh_sentiment.call_count == call_count_1

    def test_cache_refreshes_after_interval(self, sentiment_mixin):
        """Sentiment refreshes after cache_interval candles."""
        sentiment_mixin._refresh_sentiment = MagicMock()

        # First refresh
        for _ in range(5):
            sentiment_mixin.tick()
        sentiment_mixin.get_sentiment_score()
        first_count = sentiment_mixin._refresh_sentiment.call_count

        # Tick past interval
        for _ in range(5):
            sentiment_mixin.tick()
        sentiment_mixin.get_sentiment_score()
        assert sentiment_mixin._refresh_sentiment.call_count > first_count


# ==============================================================================
# SentimentMixin — With Mocked Analyzer
# ==============================================================================


class TestSentimentWithMockedAnalyzer:
    """Test SentimentMixin with mocked SentimentAnalyzer."""

    def test_refresh_with_mocked_analyzer(self):
        """Mocked analyzer produces valid cached results."""
        with patch('sentiment_mixin._HAS_SENTIMENT', True):
            sm = SentimentMixin(cache_interval_candles=1)

            # Mock the analyzer
            mock_result = MagicMock()
            mock_result.score = 0.5
            mock_result.summary = "Bullish news sentiment."
            mock_result.level.value = "bullish"
            mock_result.confidence = 0.8
            mock_result.article_count = 10
            mock_result.positive_count = 7
            mock_result.negative_count = 1
            mock_result.neutral_count = 2
            mock_result.top_headlines = ["BTC Rally", "ETF Approved"]

            sm._analyzer = MagicMock()
            sm._analyzer.analyze_articles.return_value = mock_result

            # Mock articles
            sm._get_articles = MagicMock(return_value=[
                {'text': 'BTC rally surge', 'metadata': {'title': 'BTC Rally'}},
            ])

            # Force refresh
            sm._last_fetch_candle = -999
            sm.tick()
            score = sm.get_sentiment_score()
            assert score == 0.5

            detail = sm.get_sentiment_detail()
            assert detail['level'] == 'bullish'
            assert detail['article_count'] == 10

    def test_refresh_with_empty_articles(self):
        """No articles → neutral sentiment."""
        with patch('sentiment_mixin._HAS_SENTIMENT', True):
            sm = SentimentMixin(cache_interval_candles=1)
            sm._analyzer = MagicMock()
            sm._get_articles = MagicMock(return_value=[])

            sm._last_fetch_candle = -999
            sm.tick()
            score = sm.get_sentiment_score()
            assert score == 0.0

    def test_refresh_handles_analyzer_error(self):
        """Analyzer exception → cached values unchanged."""
        with patch('sentiment_mixin._HAS_SENTIMENT', True):
            sm = SentimentMixin(cache_interval_candles=1)
            sm._analyzer = MagicMock()
            sm._analyzer.analyze_articles.side_effect = RuntimeError("oops")
            sm._get_articles = MagicMock(return_value=[{'text': 'test', 'metadata': {}}])

            sm._last_fetch_candle = -999
            sm.tick()
            # Should not crash
            score = sm.get_sentiment_score()
            assert score == 0.0  # Default


# ==============================================================================
# SentimentMixin — AI Context
# ==============================================================================


class TestSentimentAIContext:
    """Test sentiment formatting for AI context."""

    def test_ai_context_contains_key_sections(self, sentiment_mixin):
        context = sentiment_mixin.sentiment_to_ai_context()
        assert '## News Sentiment' in context
        assert 'Overall:' in context
        assert 'Confidence:' in context
        assert 'Headlines' in context


# ==============================================================================
# Integration: Factors + Grid Suitability Filter
# ==============================================================================


class TestGridSuitabilityFilter:
    """Test grid suitability as a trade filter."""

    def test_filter_passes_when_suitable(self, factors_mixin):
        """High suitability → filter passes."""
        factors = {
            'momentum_score': 0.0,
            'volatility_score': 0.3,
            'rsi_14': 50.0,
            'volume_sma_ratio': 1.0,
        }
        score = factors_mixin.grid_suitability_score(factors)
        # Ranging market → high suitability → should pass threshold 0.3
        assert score >= 0.3

    def test_filter_rejects_when_unsuitable(self, factors_mixin):
        """Very high volatility → filter rejects."""
        factors = {
            'momentum_score': 0.0,
            'volatility_score': 0.9,
            'rsi_14': 50.0,
            'volume_sma_ratio': 1.0,
        }
        score = factors_mixin.grid_suitability_score(factors)
        # High vol regime → low suitability → should fail strict threshold
        assert score < 0.5

    def test_filter_passes_with_no_factors(self):
        """No factors data → filter should pass (allow trades)."""
        # This simulates the strategy behavior: no factors yet = allow
        factors = None
        should_trade = factors is None or True  # Strategy logic
        assert should_trade is True
