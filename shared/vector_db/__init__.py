"""Vector database module for news storage and sentiment analysis."""

from shared.vector_db.embeddings import (
    cosine_similarity,
    generate_embedding,
    generate_embeddings,
    get_embedding_dimension,
    set_model_name,
    text_hash,
)
from shared.vector_db.news_fetcher import (
    NewsArticle,
    NewsFetcher,
    news_fetcher,
)
from shared.vector_db.sentiment import (
    SentimentAnalyzer,
    SentimentLevel,
    SentimentResult,
    sentiment_analyzer,
)
from shared.vector_db.vector_store import (
    VectorStore,
    news_store,
    set_persist_dir,
)

__all__ = [
    # Embeddings
    "generate_embedding",
    "generate_embeddings",
    "cosine_similarity",
    "get_embedding_dimension",
    "set_model_name",
    "text_hash",
    # Vector Store
    "VectorStore",
    "news_store",
    "set_persist_dir",
    # News Fetcher
    "NewsArticle",
    "NewsFetcher",
    "news_fetcher",
    # Sentiment
    "SentimentAnalyzer",
    "SentimentLevel",
    "SentimentResult",
    "sentiment_analyzer",
]
