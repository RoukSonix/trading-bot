"""
Sentiment Mixin for AIGridStrategy — wraps shared/vector_db/sentiment.py.

Provides news sentiment analysis for grid trading decisions.
Caches results to avoid fetching on every candle.
Falls back gracefully when shared/vector_db/ is unavailable.
"""

import logging
import time

logger = logging.getLogger(__name__)

# Try importing shared sentiment modules; may not be available in all envs
try:
    from shared.vector_db.sentiment import SentimentAnalyzer, SentimentResult
    _HAS_SENTIMENT = True
except ImportError:
    _HAS_SENTIMENT = False
    logger.info("shared.vector_db.sentiment not available — sentiment disabled")

try:
    from shared.vector_db.news_fetcher import NewsFetcher
    _HAS_NEWS_FETCHER = True
except ImportError:
    _HAS_NEWS_FETCHER = False

try:
    from shared.vector_db.vector_store import VectorStore
    _HAS_VECTOR_STORE = True
except ImportError:
    _HAS_VECTOR_STORE = False


class SentimentMixin:
    """Mixin providing news sentiment analysis to the Jesse strategy.

    Wraps shared/vector_db/sentiment.py with caching and error handling.
    All methods return plain dicts/floats/strings so the strategy doesn't
    depend on shared module dataclasses.
    """

    def __init__(self, cache_interval_candles: int = 60):
        """Initialize sentiment mixin.

        Args:
            cache_interval_candles: How many candles between sentiment refreshes.
                Default 60 (= 1 hour for 1m candles, 60 hours for 1h candles).
        """
        self._analyzer = None
        self._news_fetcher = None
        self._vector_store = None
        self._cache_interval = cache_interval_candles

        # Cached state
        self._cached_score: float = 0.0
        self._cached_summary: str = "No sentiment data available."
        self._cached_result: dict | None = None
        self._last_fetch_candle: int = -999  # Force first fetch
        self._candle_counter: int = 0

        if _HAS_SENTIMENT:
            try:
                self._analyzer = SentimentAnalyzer()
            except Exception as e:
                logger.warning(f"Failed to initialize SentimentAnalyzer: {e}")

        if _HAS_NEWS_FETCHER:
            try:
                self._news_fetcher = NewsFetcher()
            except Exception as e:
                logger.warning(f"Failed to initialize NewsFetcher: {e}")

        if _HAS_VECTOR_STORE:
            try:
                self._vector_store = VectorStore()
            except Exception as e:
                logger.warning(f"Failed to initialize VectorStore: {e}")

    @property
    def sentiment_available(self) -> bool:
        """Check if sentiment analysis is available."""
        return self._analyzer is not None

    def tick(self) -> None:
        """Increment candle counter. Call this once per candle in before()."""
        self._candle_counter += 1

    def get_sentiment_score(self) -> float:
        """Get current sentiment score.

        Returns:
            Float -1.0 to 1.0 (-1 = very bearish, 1 = very bullish).
            Returns cached value if not time to refresh.
        """
        self._maybe_refresh()
        return self._cached_score

    def get_recent_news_summary(self) -> str:
        """Get summary of recent news sentiment.

        Returns:
            Human-readable summary string.
        """
        self._maybe_refresh()
        return self._cached_summary

    def get_sentiment_detail(self) -> dict:
        """Get detailed sentiment analysis result.

        Returns:
            Dict with score, level, confidence, article_count, summary,
            top_headlines.
        """
        self._maybe_refresh()
        if self._cached_result is not None:
            return self._cached_result
        return self._default_sentiment()

    def sentiment_to_ai_context(self) -> str:
        """Format sentiment for AI prompt context.

        Returns:
            Formatted string for AI prompt.
        """
        detail = self.get_sentiment_detail()
        headlines = detail.get('top_headlines', [])
        headlines_str = "\n".join(f"  - {h}" for h in headlines) or "  None available"

        return (
            f"## News Sentiment\n"
            f"- Overall: {detail.get('level', 'neutral')} "
            f"(score: {detail.get('score', 0):+.2f})\n"
            f"- Confidence: {detail.get('confidence', 0):.0%}\n"
            f"- Articles: {detail.get('article_count', 0)}\n"
            f"### Headlines\n{headlines_str}\n"
        )

    # ==================== Internal ====================

    def _maybe_refresh(self) -> None:
        """Refresh sentiment if enough candles have passed since last fetch."""
        if self._candle_counter - self._last_fetch_candle < self._cache_interval:
            return

        self._last_fetch_candle = self._candle_counter
        self._refresh_sentiment()

    def _refresh_sentiment(self) -> None:
        """Fetch and analyze latest sentiment data."""
        if not self.sentiment_available:
            return

        try:
            articles = self._get_articles()
            if not articles:
                self._cached_result = self._default_sentiment()
                self._cached_score = 0.0
                self._cached_summary = "No recent articles available."
                return

            result = self._analyzer.analyze_articles(articles)

            self._cached_score = result.score
            self._cached_summary = result.summary
            self._cached_result = {
                'score': result.score,
                'level': result.level.value,
                'confidence': result.confidence,
                'article_count': result.article_count,
                'positive_count': result.positive_count,
                'negative_count': result.negative_count,
                'neutral_count': result.neutral_count,
                'summary': result.summary,
                'top_headlines': result.top_headlines,
            }

            logger.info(
                f"Sentiment refreshed: {result.level.value} "
                f"(score={result.score:+.2f}, "
                f"articles={result.article_count})"
            )

        except Exception as e:
            logger.warning(f"Sentiment refresh failed: {e}")

    def _get_articles(self) -> list[dict]:
        """Get articles from vector store or return empty list."""
        if self._vector_store is not None:
            try:
                docs = self._vector_store.get_recent(limit=20)
                return [
                    {'text': doc.get('text', doc.get('document', '')),
                     'metadata': doc.get('metadata', {})}
                    for doc in docs
                ]
            except Exception as e:
                logger.warning(f"Vector store query failed: {e}")

        return []

    @staticmethod
    def _default_sentiment() -> dict:
        """Return default (neutral) sentiment values."""
        return {
            'score': 0.0,
            'level': 'neutral',
            'confidence': 0.0,
            'article_count': 0,
            'positive_count': 0,
            'negative_count': 0,
            'neutral_count': 0,
            'summary': 'No sentiment data available.',
            'top_headlines': [],
        }
