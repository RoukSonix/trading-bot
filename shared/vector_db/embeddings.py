"""Text embedding generation using Ollama.

Provides embedding functionality for news articles and market text
to enable semantic search via vector database.

Uses local Ollama instance with nomic-embed-text model.
"""

from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from typing import Optional

import numpy as np
from loguru import logger


# Ollama configuration
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

# Lazy-loaded embeddings instance
_embeddings = None


def _get_embeddings():
    """Lazy-load the Ollama embeddings instance."""
    global _embeddings
    if _embeddings is None:
        try:
            from langchain_ollama import OllamaEmbeddings

            logger.info(f"Initializing Ollama embeddings: {OLLAMA_EMBED_MODEL}")
            _embeddings = OllamaEmbeddings(
                model=OLLAMA_EMBED_MODEL,
                base_url=OLLAMA_BASE_URL,
            )
            logger.info(f"Ollama embeddings ready (model={OLLAMA_EMBED_MODEL})")
        except ImportError:
            logger.error(
                "langchain-ollama not installed. "
                "Run: pip install langchain-ollama"
            )
            raise
        except Exception as e:
            logger.error(f"Failed to initialize Ollama embeddings: {e}")
            raise
    return _embeddings


def generate_embedding(text: str) -> list[float]:
    """Generate embedding vector for a single text.

    Args:
        text: Input text to embed.

    Returns:
        List of floats representing the embedding vector.
    """
    embeddings = _get_embeddings()
    try:
        vector = embeddings.embed_query(text)
        return vector
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        raise


def generate_embeddings(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Generate embeddings for multiple texts.

    Args:
        texts: List of input texts.
        batch_size: Batch size for encoding (handled by Ollama).

    Returns:
        List of embedding vectors.
    """
    if not texts:
        return []

    embeddings = _get_embeddings()
    try:
        vectors = embeddings.embed_documents(texts)
        return vectors
    except Exception as e:
        logger.error(f"Batch embedding generation failed: {e}")
        raise


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Calculate cosine similarity between two vectors.

    Args:
        a: First embedding vector.
        b: Second embedding vector.

    Returns:
        Cosine similarity score [-1, 1].
    """
    a_arr = np.array(a)
    b_arr = np.array(b)
    dot = np.dot(a_arr, b_arr)
    norm_a = np.linalg.norm(a_arr)
    norm_b = np.linalg.norm(b_arr)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def get_embedding_dimension() -> int:
    """Get the dimension of nomic-embed-text model.
    
    nomic-embed-text produces 768-dimensional vectors.
    """
    return 768


def text_hash(text: str) -> str:
    """Generate a deterministic hash for deduplication."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def check_ollama_available() -> bool:
    """Check if Ollama is available and model is loaded."""
    try:
        import httpx
        response = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5.0)
        if response.status_code == 200:
            models = response.json().get("models", [])
            model_names = [m.get("name", "") for m in models]
            if any(OLLAMA_EMBED_MODEL in name for name in model_names):
                return True
            logger.warning(f"Ollama model {OLLAMA_EMBED_MODEL} not found")
        return False
    except Exception as e:
        logger.warning(f"Ollama not available: {e}")
        return False
