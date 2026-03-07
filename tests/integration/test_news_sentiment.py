"""Integration tests for news sentiment analysis pipeline.

Tests: Mock news fetch -> Sentiment analysis -> Verify context string.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from shared.vector_db.news_fetcher import NewsArticle, NewsFetcher
from shared.vector_db.sentiment import (
    SentimentAnalyzer,
    SentimentLevel,
    SentimentResult,
)


@pytest.mark.integration
class TestNewsSentimentIntegration:
    """Integration: Fetch news -> Analyze sentiment -> Generate context."""

    @pytest.mark.asyncio
    async def test_fetch_and_analyze_bullish(self):
        """Mock bullish news -> Analyze -> Verify bullish sentiment."""
        mock_response = {
            "Data": [
                {
                    "title": "Bitcoin surges past $100k amid institutional adoption rally",
                    "body": "Major institutions are buying Bitcoin as the price surges to new all-time highs. ETF approval drives massive inflows.",
                    "source": "TestSource",
                    "url": "https://example.com/btc-surge",
                    "published_on": int(datetime.now(timezone.utc).timestamp()),
                    "categories": "BTC|Trading",
                    "tags": "BTC|crypto",
                },
                {
                    "title": "Ethereum breakout signals bullish momentum",
                    "body": "ETH breaks key resistance with strong volume. Analysts predict further gains as adoption grows.",
                    "source": "TestSource",
                    "url": "https://example.com/eth-breakout",
                    "published_on": int(datetime.now(timezone.utc).timestamp()),
                    "categories": "ETH",
                    "tags": "ETH",
                },
            ]
        }

        fetcher = NewsFetcher(rate_limit_seconds=0)

        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=mock_response)
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=None)

            # CoinGecko returns empty trending
            mock_resp_trending = AsyncMock()
            mock_resp_trending.status = 200
            mock_resp_trending.json = AsyncMock(return_value={"coins": []})
            mock_resp_trending.__aenter__ = AsyncMock(return_value=mock_resp_trending)
            mock_resp_trending.__aexit__ = AsyncMock(return_value=None)

            mock_session = AsyncMock()
            call_count = 0

            def get_side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if "trending" in str(args):
                    return mock_resp_trending
                return mock_resp

            mock_session.get = get_side_effect
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)

            mock_session_cls.return_value = mock_session

            articles = await fetcher.fetch_cryptocompare()

        assert len(articles) >= 1

        # Analyze sentiment
        analyzer = SentimentAnalyzer()
        article_dicts = [
            {
                "text": a.full_text,
                "metadata": a.to_metadata(),
            }
            for a in articles
        ]
        result = analyzer.analyze_articles(article_dicts, max_age_hours=48)

        assert result.article_count >= 1
        assert result.score > 0
        assert result.level in (SentimentLevel.BULLISH, SentimentLevel.VERY_BULLISH)

    @pytest.mark.asyncio
    async def test_fetch_and_analyze_bearish(self):
        """Mock bearish news -> Analyze -> Verify bearish sentiment."""
        mock_response = {
            "Data": [
                {
                    "title": "Crypto crash: Bitcoin plunges 30% in massive liquidation wave",
                    "body": "Fear and panic grip the market as Bitcoin crashes below support. Billions in liquidations reported.",
                    "source": "TestSource",
                    "url": "https://example.com/btc-crash",
                    "published_on": int(datetime.now(timezone.utc).timestamp()),
                    "categories": "BTC",
                    "tags": "BTC",
                },
            ]
        }

        fetcher = NewsFetcher(rate_limit_seconds=0)

        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=mock_response)
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=None)

            mock_session = AsyncMock()
            mock_session.get = lambda *args, **kwargs: mock_resp
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)

            mock_session_cls.return_value = mock_session

            articles = await fetcher.fetch_cryptocompare()

        analyzer = SentimentAnalyzer()
        article_dicts = [
            {"text": a.full_text, "metadata": a.to_metadata()}
            for a in articles
        ]
        result = analyzer.analyze_articles(article_dicts, max_age_hours=48)

        assert result.score < 0
        assert result.level in (SentimentLevel.BEARISH, SentimentLevel.VERY_BEARISH)

    def test_sentiment_to_ai_context(self):
        """Verify context string generated from sentiment analysis."""
        analyzer = SentimentAnalyzer()
        sentiment = SentimentResult(
            level=SentimentLevel.BULLISH,
            score=0.45,
            confidence=0.7,
            article_count=10,
            positive_count=7,
            negative_count=1,
            neutral_count=2,
            summary="Analyzed 10 articles: 7 positive, 1 negative, 2 neutral. Overall sentiment: bullish (score: +0.45).",
            top_headlines=["BTC rallies", "ETH breakout", "Institutional buying"],
        )

        context = analyzer.to_ai_context(sentiment)

        assert isinstance(context, str)
        assert "News Sentiment Analysis" in context
        assert "bullish" in context
        assert "BTC rallies" in context
        assert "Institutional buying" in context
        assert "7 positive" in context

    def test_sentiment_to_trading_signal(self):
        """Verify sentiment generates a trading signal with reasoning."""
        analyzer = SentimentAnalyzer()
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

        signal = analyzer.get_trading_signal(sentiment)

        assert signal["signal"] == "BULLISH"
        assert signal["strength"] > 0
        assert signal["sentiment_level"] == "bullish"
        assert "reasoning" in signal

    def test_sentiment_rsi_confluence(self):
        """Verify RSI confluence amplifies sentiment signal."""
        analyzer = SentimentAnalyzer()
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

        # With oversold RSI
        signal = analyzer.get_trading_signal(sentiment, current_rsi=25.0)
        assert signal["signal"] == "BULLISH"
        assert "RSI oversold" in signal["reasoning"]

        # With overbought RSI for bearish sentiment
        bearish_sentiment = SentimentResult(
            level=SentimentLevel.BEARISH,
            score=-0.3,
            confidence=0.5,
            article_count=3,
            positive_count=0,
            negative_count=2,
            neutral_count=1,
            summary="test",
            top_headlines=[],
        )
        signal = analyzer.get_trading_signal(bearish_sentiment, current_rsi=75.0)
        assert signal["signal"] == "BEARISH"
        assert "RSI overbought" in signal["reasoning"]

    def test_empty_news_neutral_sentiment(self):
        """Empty news should produce neutral sentiment."""
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze_articles([])

        assert result.level == SentimentLevel.NEUTRAL
        assert result.score == 0.0
        assert result.article_count == 0

        signal = analyzer.get_trading_signal(result)
        assert signal["signal"] == "NEUTRAL"
