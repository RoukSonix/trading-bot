"""Volatility indicators for technical analysis."""

import numpy as np
import pandas as pd


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    """True Range (single period)."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def bollinger_bands(
    df: pd.DataFrame,
    period: int = 20,
    std_dev: float = 2.0,
    column: str = "close",
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Bollinger Bands — returns (upper, middle, lower)."""
    middle = df[column].rolling(window=period).mean()
    std = df[column].rolling(window=period).std()
    upper = middle + std * std_dev
    lower = middle - std * std_dev
    return upper, middle, lower


def keltner(
    df: pd.DataFrame,
    ema_period: int = 20,
    atr_period: int = 10,
    multiplier: float = 1.5,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Keltner Channels — returns (upper, middle, lower)."""
    middle = df["close"].ewm(span=ema_period, adjust=False).mean()
    atr_val = atr(df, atr_period)
    upper = middle + multiplier * atr_val
    lower = middle - multiplier * atr_val
    return upper, middle, lower


def donchian(df: pd.DataFrame, period: int = 20) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Donchian Channels — returns (upper, middle, lower)."""
    upper = df["high"].rolling(period).max()
    lower = df["low"].rolling(period).min()
    middle = (upper + lower) / 2
    return upper, middle, lower


def atr_percent(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ATR as percentage of close price."""
    return atr(df, period) / df["close"] * 100


def historical_volatility(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Historical Volatility (annualized, assuming daily data)."""
    log_returns = np.log(df["close"] / df["close"].shift())
    return log_returns.rolling(period).std() * np.sqrt(252)


def chaikin_volatility(df: pd.DataFrame, period: int = 10) -> pd.Series:
    """Chaikin Volatility — rate of change of EMA of high-low range."""
    hl_range = df["high"] - df["low"]
    ema_range = hl_range.ewm(span=period, adjust=False).mean()
    return ema_range.pct_change(periods=period) * 100


def natr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Normalized ATR (ATR / close * 100)."""
    return atr(df, period) / df["close"] * 100
