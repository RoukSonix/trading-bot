"""ChromaDB vector store for local semantic search.

Stores news articles and market text with embeddings for
similarity-based retrieval.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger


# Lazy-loaded client
_client = None
_persist_dir: str = "data/chroma"


def set_persist_dir(path: str) -> None:
    """Set the ChromaDB persistence directory."""
    global _persist_dir, _client
    _persist_dir = path
    _client = None  # Force re-init


def _get_client():
    """Lazy-load ChromaDB client with persistence."""
    global _client
    if _client is None:
        try:
            import chromadb
            from chromadb.config import Settings

            persist_path = Path(_persist_dir)
            persist_path.mkdir(parents=True, exist_ok=True)

            _client = chromadb.PersistentClient(
                path=str(persist_path),
                settings=Settings(anonymized_telemetry=False),
            )
            logger.info(f"ChromaDB initialized at {persist_path}")
        except ImportError:
            logger.error(
                "chromadb not installed. Run: pip install chromadb"
            )
            raise
    return _client


class VectorStore:
    """ChromaDB-backed vector store for news and market text."""

    def __init__(
        self,
        collection_name: str = "crypto_news",
        persist_dir: str | None = None,
    ):
        """Initialize vector store.

        Args:
            collection_name: Name of the ChromaDB collection.
            persist_dir: Override persistence directory.
        """
        if persist_dir:
            set_persist_dir(persist_dir)

        self.collection_name = collection_name
        self._collection = None

    @property
    def collection(self):
        """Get or create the ChromaDB collection."""
        if self._collection is None:
            client = _get_client()
            self._collection = client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.debug(
                f"Collection '{self.collection_name}' has {self._collection.count()} documents"
            )
        return self._collection

    def add(
        self,
        texts: list[str],
        metadatas: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
        embeddings: list[list[float]] | None = None,
    ) -> list[str]:
        """Add documents to the vector store.

        Args:
            texts: Document texts.
            metadatas: Optional metadata dicts for each document.
            ids: Optional unique IDs. Auto-generated if not provided.
            embeddings: Pre-computed embeddings. If None, ChromaDB will compute them.

        Returns:
            List of document IDs.
        """
        if not texts:
            return []

        # Generate IDs if not provided
        if ids is None:
            from shared.vector_db.embeddings import text_hash

            ids = [f"doc_{text_hash(t)}_{i}" for i, t in enumerate(texts)]

        # Add timestamps to metadata
        if metadatas is None:
            metadatas = [{}] * len(texts)
        for meta in metadatas:
            if "added_at" not in meta:
                meta["added_at"] = datetime.now(timezone.utc).isoformat()

        kwargs: dict[str, Any] = {
            "documents": texts,
            "metadatas": metadatas,
            "ids": ids,
        }

        if embeddings is not None:
            kwargs["embeddings"] = embeddings

        self.collection.upsert(**kwargs)
        logger.info(f"Added {len(texts)} documents to '{self.collection_name}'")
        return ids

    def add_with_embeddings(
        self,
        texts: list[str],
        metadatas: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
        batch_size: int = 32,
    ) -> list[str]:
        """Add documents with Ollama embeddings.

        Uses our embeddings module (Ollama nomic-embed-text) instead of ChromaDB's default.

        Args:
            texts: Document texts.
            metadatas: Optional metadata dicts.
            ids: Optional unique IDs.
            batch_size: Embedding batch size.

        Returns:
            List of document IDs.
        """
        from shared.vector_db.embeddings import generate_embeddings

        embeddings = generate_embeddings(texts, batch_size=batch_size)
        return self.add(texts, metadatas=metadatas, ids=ids, embeddings=embeddings)

    def query(
        self,
        query_text: str,
        n_results: int = 5,
        where: dict | None = None,
        embedding: list[float] | None = None,
    ) -> list[dict[str, Any]]:
        """Query the vector store for similar documents.

        Args:
            query_text: Query text to find similar documents.
            n_results: Number of results to return.
            where: Optional metadata filter.
            embedding: Pre-computed query embedding.

        Returns:
            List of result dicts with keys: id, text, metadata, distance.
        """
        kwargs: dict[str, Any] = {"n_results": min(n_results, self.count() or 1)}

        if embedding is not None:
            kwargs["query_embeddings"] = [embedding]
        else:
            kwargs["query_texts"] = [query_text]

        if where:
            kwargs["where"] = where

        try:
            results = self.collection.query(**kwargs)
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return []

        # Flatten results into list of dicts
        docs = []
        if results and results["ids"]:
            for i, doc_id in enumerate(results["ids"][0]):
                docs.append({
                    "id": doc_id,
                    "text": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0.0,
                })

        return docs

    def query_with_embedding(
        self,
        query_text: str,
        n_results: int = 5,
        where: dict | None = None,
    ) -> list[dict[str, Any]]:
        """Query using Ollama embedding.

        Args:
            query_text: Query text.
            n_results: Number of results.
            where: Optional metadata filter.

        Returns:
            List of result dicts.
        """
        from shared.vector_db.embeddings import generate_embedding

        embedding = generate_embedding(query_text)
        return self.query(
            query_text=query_text,
            n_results=n_results,
            where=where,
            embedding=embedding,
        )

    def count(self) -> int:
        """Get the number of documents in the collection."""
        return self.collection.count()

    def delete(self, ids: list[str]) -> None:
        """Delete documents by ID."""
        if ids:
            self.collection.delete(ids=ids)
            logger.info(f"Deleted {len(ids)} documents from '{self.collection_name}'")

    def clear(self) -> None:
        """Delete all documents in the collection."""
        client = _get_client()
        client.delete_collection(self.collection_name)
        self._collection = None
        logger.info(f"Cleared collection '{self.collection_name}'")

    def get_recent(
        self,
        n: int = 10,
        source: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get most recently added documents.

        Args:
            n: Number of documents to return.
            source: Optional source filter.

        Returns:
            List of document dicts.
        """
        where = {"source": source} if source else None

        try:
            results = self.collection.get(
                where=where,
                limit=n,
                include=["documents", "metadatas"],
            )
        except Exception as e:
            logger.error(f"Get recent failed: {e}")
            return []

        docs = []
        if results and results["ids"]:
            for i, doc_id in enumerate(results["ids"]):
                docs.append({
                    "id": doc_id,
                    "text": results["documents"][i] if results["documents"] else "",
                    "metadata": results["metadatas"][i] if results["metadatas"] else {},
                })

        # Sort by added_at descending
        docs.sort(
            key=lambda d: d.get("metadata", {}).get("added_at", ""),
            reverse=True,
        )

        return docs[:n]


# Global instance
news_store = VectorStore(collection_name="crypto_news")
