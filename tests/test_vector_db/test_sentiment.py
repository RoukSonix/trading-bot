"""Tests for sentiment analysis module."""

from datetime import datetime, timedelta, timezone

import pytest

from shared.vector_db.sentiment import (
    SentimentAnalyzer,
    SentimentLevel,
    SentimentResult,
)


def _recent_timestamp(hours_ago: int = 1) -> str:
    """Return an ISO timestamp from `hours_ago` hours before now."""
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


class TestSentimentAnalyzer:
    """Tests for SentimentAnalyzer."""

    def setup_method(self):
        self.analyzer = SentimentAnalyzer()

    def test_bullish_text(self):
        text = "Bitcoin rally continues as price surges past $100,000 amid institutional adoption"
        score, confidence = self.analyzer.analyze_text(text)
        assert score > 0
        assert confidence > 0

    def test_bearish_text(self):
        text = "Crypto market crash: Bitcoin plunges 20% amid fear and panic selling"
        score, confidence = self.analyzer.analyze_text(text)
        assert score < 0
        assert confidence > 0

    def test_neutral_text(self):
        text = "The weather in London was cloudy today with light rain expected tomorrow"
        score, confidence = self.analyzer.analyze_text(text)
        assert score == 0.0
        assert confidence == 0.0

    def test_mixed_sentiment(self):
        text = "Bitcoin rally slows as concerns about regulation emerge amid growth"
        score, confidence = self.analyzer.analyze_text(text)
        # Mixed signals — score should be moderate
        assert -0.5 < score < 0.5

    def test_analyze_articles_empty(self):
        result = self.analyzer.analyze_articles([])
        assert result.level == SentimentLevel.NEUTRAL
        assert result.article_count == 0

    def test_analyze_articles_bullish(self):
        articles = [
            {
                "text": "Bitcoin rally surges as institutional adoption increases",
                "metadata": {"title": "BTC Rally", "published_at": _recent_timestamp(1)},
            },
            {
                "text": "Ethereum breakout signals bullish momentum",
                "metadata": {"title": "ETH Breakout", "published_at": _recent_timestamp(2)},
            },
        ]
        result = self.analyzer.analyze_articles(articles, max_age_hours=48)

        assert result.article_count == 2
        assert result.score > 0
        assert result.level in (SentimentLevel.BULLISH, SentimentLevel.VERY_BULLISH)

    def test_analyze_articles_bearish(self):
        articles = [
            {
                "text": "Crypto crash liquidation wave wipes out billions",
                "metadata": {"title": "Crash", "published_at": _recent_timestamp(1)},
            },
            {
                "text": "Bitcoin plunges amid panic selling and fear",
                "metadata": {"title": "Plunge", "published_at": _recent_timestamp(2)},
            },
        ]
        result = self.analyzer.analyze_articles(articles, max_age_hours=48)

        assert result.score < 0
        assert result.level in (SentimentLevel.BEARISH, SentimentLevel.VERY_BEARISH)

    def test_classify_levels(self):
        assert self.analyzer._classify(0.6) == SentimentLevel.VERY_BULLISH
        assert self.analyzer._classify(0.3) == SentimentLevel.BULLISH
        assert self.analyzer._classify(0.0) == SentimentLevel.NEUTRAL
        assert self.analyzer._classify(-0.3) == SentimentLevel.BEARISH
        assert self.analyzer._classify(-0.6) == SentimentLevel.VERY_BEARISH

    def test_trading_signal_bullish(self):
        sentiment = SentimentResult(
            level=SentimentLevel.BULLISH,
            score=0.4,
            confidence=0.6,
            article_count=5,
            positive_count=4,
            negative_count=0,
            neutral_count=1,
            summary="test",
            top_headlines=[],
        )
        signal = self.analyzer.get_trading_signal(sentiment)
        assert signal["signal"] == "BULLISH"
        assert signal["strength"] > 0

    def test_trading_signal_with_rsi_confluence(self):
        sentiment = SentimentResult(
            level=SentimentLevel.BULLISH,
            score=0.3,
            confidence=0.5,
            article_count=3,
            positive_count=2,
            negative_count=0,
            neutral_count=1,
            summary="test",
            top_headlines=[],
        )
        # Oversold RSI should amplify bullish signal
        signal = self.analyzer.get_trading_signal(sentiment, current_rsi=25.0)
        assert signal["signal"] == "BULLISH"
        assert "RSI oversold" in signal["reasoning"]

    def test_trading_signal_neutral(self):
        sentiment = SentimentResult(
            level=SentimentLevel.NEUTRAL,
            score=0.0,
            confidence=0.1,
            article_count=2,
            positive_count=1,
            negative_count=1,
            neutral_count=0,
            summary="test",
            top_headlines=[],
        )
        signal = self.analyzer.get_trading_signal(sentiment)
        assert signal["signal"] == "NEUTRAL"

    def test_to_ai_context(self):
        sentiment = SentimentResult(
            level=SentimentLevel.BULLISH,
            score=0.35,
            confidence=0.6,
            article_count=5,
            positive_count=3,
            negative_count=1,
            neutral_count=1,
            summary="Test summary",
            top_headlines=["Headline 1", "Headline 2"],
        )
        context = self.analyzer.to_ai_context(sentiment)
        assert "News Sentiment Analysis" in context
        assert "bullish" in context
        assert "Headline 1" in context

    def test_custom_keywords(self):
        custom_bullish = {"moon": 3.0}
        custom_bearish = {"doom": -3.0}
        analyzer = SentimentAnalyzer(
            bullish_keywords=custom_bullish,
            bearish_keywords=custom_bearish,
        )
        score, conf = analyzer.analyze_text("Bitcoin to the moon!")
        assert score > 0

        score, conf = analyzer.analyze_text("doom for crypto markets")
        assert score < 0
