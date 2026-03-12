"""Crypto news fetching from free APIs.

Supports multiple free news sources with rate limiting
and deduplication.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from loguru import logger


@dataclass
class NewsArticle:
    """Parsed news article."""

    title: str
    description: str
    source: str
    url: str
    published_at: datetime | None = None
    categories: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        """Combined text for embedding."""
        return f"{self.title}. {self.description}"

    def to_metadata(self) -> dict[str, Any]:
        """Convert to metadata dict for vector store."""
        return {
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "published_at": self.published_at.isoformat() if self.published_at else "",
            "categories": ",".join(self.categories),
            "symbols": ",".join(self.symbols),
        }


class NewsFetcher:
    """Fetch crypto news from multiple free APIs."""

    # CryptoCompare News API (free, no key required for basic use)
    CRYPTOCOMPARE_URL = "https://min-api.cryptocompare.com/data/v2/news/"

    # CoinGecko status updates (free, no key required)
    COINGECKO_URL = "https://api.coingecko.com/api/v3"

    def __init__(
        self,
        rate_limit_seconds: float = 2.0,
        max_articles_per_fetch: int = 50,
        timeout_seconds: float = 15.0,
    ):
        """Initialize news fetcher.

        Args:
            rate_limit_seconds: Minimum seconds between API calls.
            max_articles_per_fetch: Max articles to return per fetch.
            timeout_seconds: HTTP request timeout.
        """
        self.rate_limit_seconds = rate_limit_seconds
        self.max_articles = max_articles_per_fetch
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._last_fetch: dict[str, datetime] = {}
        self._seen_urls: set[str] = set()

    async def _rate_limit(self, source: str) -> None:
        """Enforce rate limiting per source."""
        if source in self._last_fetch:
            elapsed = (datetime.now(timezone.utc) - self._last_fetch[source]).total_seconds()
            if elapsed < self.rate_limit_seconds:
                await asyncio.sleep(self.rate_limit_seconds - elapsed)
        self._last_fetch[source] = datetime.now(timezone.utc)

    async def fetch_cryptocompare(
        self,
        categories: list[str] | None = None,
    ) -> list[NewsArticle]:
        """Fetch news from CryptoCompare API.

        Args:
            categories: Optional category filters (e.g., ["BTC", "ETH"]).

        Returns:
            List of NewsArticle objects.
        """
        await self._rate_limit("cryptocompare")

        params: dict[str, Any] = {"lang": "EN"}
        if categories:
            params["categories"] = ",".join(categories)

        articles = []
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(
                    self.CRYPTOCOMPARE_URL, params=params
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"CryptoCompare API returned {resp.status}")
                        return []

                    data = await resp.json()
                    news_items = data.get("Data", [])

                    for item in news_items[: self.max_articles]:
                        url = item.get("url", "")
                        if url in self._seen_urls:
                            continue
                        self._seen_urls.add(url)

                        published = None
                        if "published_on" in item:
                            try:
                                published = datetime.fromtimestamp(
                                    item["published_on"], tz=timezone.utc
                                )
                            except (ValueError, OSError):
                                pass

                        article = NewsArticle(
                            title=item.get("title", ""),
                            description=item.get("body", "")[:500],
                            source=item.get("source", "CryptoCompare"),
                            url=url,
                            published_at=published,
                            categories=item.get("categories", "").split("|"),
                            symbols=[
                                s.strip()
                                for s in item.get("tags", "").split("|")
                                if s.strip()
                            ],
                        )
                        articles.append(article)

            logger.info(f"Fetched {len(articles)} articles from CryptoCompare")

        except asyncio.TimeoutError:
            logger.warning("CryptoCompare request timed out")
        except aiohttp.ClientError as e:
            logger.warning(f"CryptoCompare request failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fetching CryptoCompare: {e}")

        return articles

    async def fetch_coingecko_trending(self) -> list[NewsArticle]:
        """Fetch trending coins from CoinGecko as pseudo-news.

        Returns:
            List of NewsArticle objects representing trending activity.
        """
        await self._rate_limit("coingecko")

        articles = []
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(
                    f"{self.COINGECKO_URL}/search/trending"
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"CoinGecko API returned {resp.status}")
                        return []

                    data = await resp.json()
                    coins = data.get("coins", [])

                    for coin_data in coins[:10]:
                        item = coin_data.get("item", {})
                        coin_id = item.get("id", "")
                        url = f"https://www.coingecko.com/en/coins/{coin_id}"

                        if url in self._seen_urls:
                            continue
                        self._seen_urls.add(url)

                        symbol = item.get("symbol", "").upper()
                        name = item.get("name", "")
                        rank = item.get("market_cap_rank", "N/A")
                        score = item.get("score", 0)

                        article = NewsArticle(
                            title=f"{name} ({symbol}) trending on CoinGecko",
                            description=(
                                f"{name} is trending (rank #{score + 1}). "
                                f"Market cap rank: {rank}. "
                                f"This indicates increased market interest and search activity."
                            ),
                            source="CoinGecko Trending",
                            url=url,
                            published_at=datetime.now(timezone.utc),
                            categories=["trending"],
                            symbols=[symbol],
                        )
                        articles.append(article)

            logger.info(f"Fetched {len(articles)} trending items from CoinGecko")

        except asyncio.TimeoutError:
            logger.warning("CoinGecko request timed out")
        except aiohttp.ClientError as e:
            logger.warning(f"CoinGecko request failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fetching CoinGecko: {e}")

        return articles

    async def fetch_all(
        self,
        categories: list[str] | None = None,
    ) -> list[NewsArticle]:
        """Fetch news from all available sources.

        Args:
            categories: Optional category filters for CryptoCompare.

        Returns:
            Combined list of NewsArticle objects, sorted by published_at.
        """
        results = await asyncio.gather(
            self.fetch_cryptocompare(categories=categories),
            self.fetch_coingecko_trending(),
            return_exceptions=True,
        )

        articles = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"News fetch failed: {result}")
            else:
                articles.extend(result)

        # Sort by published_at (newest first)
        articles.sort(
            key=lambda a: a.published_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

        logger.info(f"Total articles fetched: {len(articles)}")
        return articles

    def clear_seen(self) -> None:
        """Clear the deduplication cache."""
        self._seen_urls.clear()

    async def fetch_and_store(
        self,
        store: Any,
        categories: list[str] | None = None,
        use_ollama: bool = True,
    ) -> int:
        """Fetch news and store in vector database.

        Args:
            store: VectorStore instance.
            categories: Optional category filters.
            use_ollama: Whether to generate embeddings via Ollama.

        Returns:
            Number of articles stored.
        """
        articles = await self.fetch_all(categories=categories)

        if not articles:
            return 0

        texts = [a.full_text for a in articles]
        metadatas = [a.to_metadata() for a in articles]
        ids = [f"news_{a.source}_{hash(a.url) & 0xFFFFFFFF}" for a in articles]

        if use_ollama:
            store.add_with_embeddings(texts, metadatas=metadatas, ids=ids)
        else:
            store.add(texts, metadatas=metadatas, ids=ids)

        return len(articles)


# Global instance
news_fetcher = NewsFetcher()
