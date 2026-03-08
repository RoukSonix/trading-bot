"""
Conftest for jesse-bot tests.

Adds the jesse-bot directory to PYTHONPATH so strategy imports work.
Provides shared fixtures for grid, AI, and trailing stop tests.
"""

import sys
import os

import numpy as np
import pytest

# Add jesse-bot root to path for strategy imports
jesse_bot_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if jesse_bot_dir not in sys.path:
    sys.path.insert(0, jesse_bot_dir)

# Add grid_logic module directly (avoid __init__.py which imports Jesse)
grid_logic_path = os.path.join(jesse_bot_dir, 'strategies', 'AIGridStrategy')
if grid_logic_path not in sys.path:
    sys.path.insert(0, grid_logic_path)

from grid_logic import GridManager, GridConfig, TrailingStopManager


@pytest.fixture
def grid_config():
    """Default grid config."""
    return GridConfig()


@pytest.fixture
def grid_manager():
    """Pre-configured GridManager with default config."""
    return GridManager(GridConfig(grid_levels_count=5, grid_spacing_pct=1.0))


@pytest.fixture
def grid_manager_with_levels():
    """GridManager with grid levels already set up at 100k center."""
    gm = GridManager(GridConfig(grid_levels_count=5, grid_spacing_pct=1.0))
    gm.setup_grid(100000.0)
    return gm


@pytest.fixture
def trailing_stop():
    """TrailingStopManager instance with default params."""
    return TrailingStopManager(activation_pct=1.0, distance_pct=0.5)


@pytest.fixture
def mock_ai_response():
    """Typical AI analysis response dict."""
    return {
        'recommendation': 'TRADE',
        'confidence': 0.75,
        'grid_params': {'direction': 'both'},
        'trend': 'neutral',
        'reasoning': 'Market is range-bound, grid trading recommended.',
    }


@pytest.fixture
def mock_ai_response_bearish():
    """Bearish AI analysis response."""
    return {
        'recommendation': 'WAIT',
        'confidence': 0.4,
        'grid_params': {'direction': 'short_only'},
        'trend': 'downtrend',
        'reasoning': 'Strong bearish momentum, avoid long positions.',
    }


@pytest.fixture
def mock_ai_response_bullish():
    """Bullish AI analysis response."""
    return {
        'recommendation': 'TRADE',
        'confidence': 0.85,
        'grid_params': {'direction': 'long_only'},
        'trend': 'uptrend',
        'reasoning': 'Strong uptrend detected, favor long grid.',
    }


@pytest.fixture
def sample_candles():
    """Numpy array of 100 OHLCV candles for testing.

    Format: [timestamp, open, high, low, close, volume]
    Simulates sideways market around 100k.
    """
    np.random.seed(42)
    n = 100
    base_price = 100000.0
    timestamps = np.arange(n) * 60000  # 1m candles
    opens = base_price + np.random.randn(n).cumsum() * 100
    highs = opens + np.abs(np.random.randn(n)) * 200
    lows = opens - np.abs(np.random.randn(n)) * 200
    closes = opens + np.random.randn(n) * 150
    volumes = np.abs(np.random.randn(n)) * 1000 + 500

    candles = np.column_stack([timestamps, opens, highs, lows, closes, volumes])
    return candles


@pytest.fixture
def sample_candles_uptrend():
    """OHLCV candles with uptrend (drift +0.5% per candle)."""
    np.random.seed(42)
    n = 100
    base_price = 100000.0
    drift = np.arange(n) * 500  # steady rise
    timestamps = np.arange(n) * 60000
    opens = base_price + drift + np.random.randn(n) * 50
    highs = opens + np.abs(np.random.randn(n)) * 200
    lows = opens - np.abs(np.random.randn(n)) * 200
    closes = opens + 400 + np.random.randn(n) * 50  # close > open bias
    volumes = np.abs(np.random.randn(n)) * 1000 + 500

    return np.column_stack([timestamps, opens, highs, lows, closes, volumes])


@pytest.fixture
def sample_candles_downtrend():
    """OHLCV candles with downtrend."""
    np.random.seed(42)
    n = 100
    base_price = 150000.0
    drift = np.arange(n) * -500
    timestamps = np.arange(n) * 60000
    opens = base_price + drift + np.random.randn(n) * 50
    highs = opens + np.abs(np.random.randn(n)) * 200
    lows = opens - np.abs(np.random.randn(n)) * 200
    closes = opens - 400 + np.random.randn(n) * 50
    volumes = np.abs(np.random.randn(n)) * 1000 + 500

    return np.column_stack([timestamps, opens, highs, lows, closes, volumes])
