"""Tests for news_fetcher module."""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from shared.vector_db.news_fetcher import NewsArticle, NewsFetcher


class TestNewsArticle:
    """Tests for NewsArticle dataclass."""

    def test_full_text(self):
        article = NewsArticle(
            title="Bitcoin Surges",
            description="Price hits new high",
            source="TestSource",
            url="https://example.com/1",
        )
        assert article.full_text == "Bitcoin Surges. Price hits new high"

    def test_to_metadata(self):
        article = NewsArticle(
            title="Test",
            description="Desc",
            source="Source",
            url="https://example.com",
            published_at=datetime(2026, 3, 5, 12, 0),
            categories=["BTC", "crypto"],
            symbols=["BTC"],
        )
        meta = article.to_metadata()
        assert meta["title"] == "Test"
        assert meta["source"] == "Source"
        assert "2026-03-05" in meta["published_at"]
        assert meta["categories"] == "BTC,crypto"
        assert meta["symbols"] == "BTC"


class TestNewsFetcher:
    """Tests for NewsFetcher."""

    def test_init_defaults(self):
        fetcher = NewsFetcher()
        assert fetcher.rate_limit_seconds == 2.0
        assert fetcher.max_articles == 50

    def test_clear_seen(self):
        fetcher = NewsFetcher()
        fetcher._seen_urls.add("https://example.com/1")
        fetcher.clear_seen()
        assert len(fetcher._seen_urls) == 0

    @pytest.mark.asyncio
    async def test_fetch_cryptocompare_success(self):
        """Test CryptoCompare fetch with mocked response."""
        mock_response = {
            "Data": [
                {
                    "title": "Test Article",
                    "body": "Test body content about Bitcoin",
                    "source": "TestSource",
                    "url": "https://example.com/test1",
                    "published_on": 1709640000,
                    "categories": "BTC|Trading",
                    "tags": "BTC|crypto",
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
            assert len(articles) == 1
            assert articles[0].title == "Test Article"
            assert articles[0].source == "TestSource"

    @pytest.mark.asyncio
    async def test_fetch_cryptocompare_api_error(self):
        """Test graceful handling of API errors."""
        fetcher = NewsFetcher(rate_limit_seconds=0)

        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 500
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=None)

            mock_session = AsyncMock()
            mock_session.get = lambda *args, **kwargs: mock_resp
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)

            mock_session_cls.return_value = mock_session

            articles = await fetcher.fetch_cryptocompare()
            assert articles == []

    @pytest.mark.asyncio
    async def test_deduplication(self):
        """Test that duplicate URLs are filtered."""
        fetcher = NewsFetcher(rate_limit_seconds=0)
        fetcher._seen_urls.add("https://example.com/test1")

        mock_response = {
            "Data": [
                {
                    "title": "Duplicate",
                    "body": "Already seen",
                    "source": "TestSource",
                    "url": "https://example.com/test1",  # Already seen
                    "published_on": 1709640000,
                    "categories": "",
                    "tags": "",
                },
                {
                    "title": "New Article",
                    "body": "Fresh content",
                    "source": "TestSource",
                    "url": "https://example.com/test2",  # New
                    "published_on": 1709640000,
                    "categories": "",
                    "tags": "",
                },
            ]
        }

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
            assert len(articles) == 1
            assert articles[0].title == "New Article"
