"""Momentum indicators for technical analysis."""

import numpy as np
import pandas as pd


def rsi(df: pd.DataFrame, period: int = 14, column: str = "close") -> pd.Series:
    """Relative Strength Index (0-100)."""
    delta = df[column].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))
    return result.fillna(100.0)


def macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    column: str = "close",
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD — returns (macd_line, signal_line, histogram)."""
    ema_fast = df[column].ewm(span=fast, adjust=False).mean()
    ema_slow = df[column].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def stochastic(
    df: pd.DataFrame, k: int = 14, d: int = 3
) -> pd.DataFrame:
    """Stochastic Oscillator.

    Returns DataFrame with: stoch_k, stoch_d.
    """
    low_min = df["low"].rolling(k).min()
    high_max = df["high"].rolling(k).max()
    denom = (high_max - low_min).replace(0, np.nan)
    stoch_k = 100 * (df["close"] - low_min) / denom
    stoch_k = stoch_k.fillna(50.0)
    stoch_d = stoch_k.rolling(d).mean()
    return pd.DataFrame({"stoch_k": stoch_k, "stoch_d": stoch_d}, index=df.index)


def stoch_rsi(
    df: pd.DataFrame, period: int = 14, k: int = 3, d: int = 3, column: str = "close"
) -> pd.DataFrame:
    """Stochastic RSI.

    Returns DataFrame with: stoch_rsi_k, stoch_rsi_d.
    """
    rsi_val = rsi(df, period, column)
    rsi_min = rsi_val.rolling(period).min()
    rsi_max = rsi_val.rolling(period).max()
    stoch_rsi_raw = (rsi_val - rsi_min) / (rsi_max - rsi_min).replace(0, np.nan)
    stoch_rsi_raw = stoch_rsi_raw.fillna(0.5)
    stoch_rsi_k = stoch_rsi_raw.rolling(k).mean()
    stoch_rsi_d = stoch_rsi_k.rolling(d).mean()
    return pd.DataFrame(
        {"stoch_rsi_k": stoch_rsi_k, "stoch_rsi_d": stoch_rsi_d}, index=df.index
    )


def williams_r(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Williams %R (-100 to 0)."""
    high_max = df["high"].rolling(period).max()
    low_min = df["low"].rolling(period).min()
    denom = (high_max - low_min).replace(0, np.nan)
    result = -100 * (high_max - df["close"]) / denom
    return result.fillna(-50.0)


def mfi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Money Flow Index (volume-weighted RSI, 0-100)."""
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    raw_money_flow = typical_price * df["volume"]

    positive_flow = raw_money_flow.where(typical_price.diff() > 0, 0)
    negative_flow = raw_money_flow.where(typical_price.diff() < 0, 0)

    positive_mf = positive_flow.rolling(period).sum()
    negative_mf = negative_flow.rolling(period).sum()

    money_ratio = positive_mf / negative_mf.replace(0, np.nan)
    result = 100 - (100 / (1 + money_ratio))
    return result.fillna(100.0)


def roc(df: pd.DataFrame, period: int = 12, column: str = "close") -> pd.Series:
    """Rate of Change (percentage)."""
    return df[column].pct_change(periods=period) * 100


def tsi(
    df: pd.DataFrame, long: int = 25, short: int = 13, column: str = "close"
) -> pd.Series:
    """True Strength Index (-100 to 100)."""
    delta = df[column].diff()
    double_smoothed = delta.ewm(span=long, adjust=False).mean().ewm(
        span=short, adjust=False
    ).mean()
    double_smoothed_abs = delta.abs().ewm(span=long, adjust=False).mean().ewm(
        span=short, adjust=False
    ).mean()
    result = 100 * double_smoothed / double_smoothed_abs.replace(0, np.nan)
    return result.fillna(0.0)


def ultimate(
    df: pd.DataFrame, p1: int = 7, p2: int = 14, p3: int = 28
) -> pd.Series:
    """Ultimate Oscillator (0-100)."""
    close = df["close"]
    high = df["high"]
    low = df["low"]

    bp = close - pd.concat([low, close.shift()], axis=1).min(axis=1)
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)

    avg1 = bp.rolling(p1).sum() / tr.rolling(p1).sum()
    avg2 = bp.rolling(p2).sum() / tr.rolling(p2).sum()
    avg3 = bp.rolling(p3).sum() / tr.rolling(p3).sum()

    return 100 * (4 * avg1 + 2 * avg2 + avg3) / 7


def ao(df: pd.DataFrame) -> pd.Series:
    """Awesome Oscillator (5-period SMA of midpoint minus 34-period SMA)."""
    midpoint = (df["high"] + df["low"]) / 2
    return midpoint.rolling(5).mean() - midpoint.rolling(34).mean()


def momentum(df: pd.DataFrame, period: int = 10, column: str = "close") -> pd.Series:
    """Simple Momentum (price difference over N periods)."""
    return df[column].diff(periods=period)
