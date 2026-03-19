"""API key authentication for trading endpoints."""

import os

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(api_key: str = Security(API_KEY_HEADER)) -> str:
    """Validate API key from X-API-Key header.

    Returns the key on success, raises 401/503 on failure.
    """
    expected = os.getenv("TRADING_API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="API key not configured")
    if not api_key or api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key
