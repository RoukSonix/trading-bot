"""Shared test fixtures for trading-bots test suite."""

import os

# Set dummy env vars before any imports that trigger Settings validation
os.environ.setdefault("BINANCE_API_KEY", "test_api_key")
os.environ.setdefault("BINANCE_SECRET_KEY", "test_secret_key")

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.core.database import Base


@pytest.fixture
def in_memory_db():
    """Create an in-memory SQLite database for tests.

    Yields a sessionmaker bound to the in-memory engine.
    Tables are created before tests and dropped after.
    """
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    yield Session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(in_memory_db):
    """Get a database session that rolls back after each test."""
    session = in_memory_db()
    yield session
    session.rollback()
    session.close()


def make_ohlcv_df(
    n: int = 100,
    base_price: float = 50000.0,
    trend: float = 0.0,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing.

    Args:
        n: Number of candles.
        base_price: Starting price.
        trend: Daily drift (e.g., 0.001 = +0.1% per day).
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with OHLCV columns and DatetimeIndex.
    """
    np.random.seed(seed)
    dates = pd.date_range("2025-01-01", periods=n, freq="1D")
    returns = np.random.normal(trend, 0.02, n)
    prices = base_price * np.cumprod(1 + returns)

    df = pd.DataFrame(
        {
            "open": prices * (1 + np.random.uniform(-0.005, 0.005, n)),
            "high": prices * (1 + np.abs(np.random.normal(0, 0.01, n))),
            "low": prices * (1 - np.abs(np.random.normal(0, 0.01, n))),
            "close": prices,
            "volume": np.random.uniform(100, 1000, n),
        },
        index=dates,
    )

    return df


@pytest.fixture
def ohlcv_df():
    """100-candle OHLCV DataFrame with no trend."""
    return make_ohlcv_df(100)


@pytest.fixture
def ohlcv_df_uptrend():
    """100-candle OHLCV DataFrame with uptrend."""
    return make_ohlcv_df(100, trend=0.005)


@pytest.fixture
def ohlcv_df_downtrend():
    """100-candle OHLCV DataFrame with downtrend."""
    return make_ohlcv_df(100, trend=-0.005)
