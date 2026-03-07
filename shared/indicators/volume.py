"""Volume indicators for technical analysis."""

import numpy as np
import pandas as pd


def obv(df: pd.DataFrame) -> pd.Series:
    """On-Balance Volume."""
    return (np.sign(df["close"].diff()) * df["volume"]).cumsum()


def vwap(df: pd.DataFrame) -> pd.Series:
    """Volume Weighted Average Price."""
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    cum_tp_vol = (typical_price * df["volume"]).cumsum()
    cum_vol = df["volume"].cumsum()
    return cum_tp_vol / cum_vol


def ad_line(df: pd.DataFrame) -> pd.Series:
    """Accumulation/Distribution Line."""
    clv = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / (
        df["high"] - df["low"]
    )
    clv = clv.fillna(0)
    return (clv * df["volume"]).cumsum()


def cmf(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Chaikin Money Flow."""
    clv = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / (
        df["high"] - df["low"]
    )
    clv = clv.fillna(0)
    money_flow_vol = clv * df["volume"]
    return money_flow_vol.rolling(period).sum() / df["volume"].rolling(period).sum()


def force_index(df: pd.DataFrame, period: int = 13) -> pd.Series:
    """Force Index."""
    fi = df["close"].diff() * df["volume"]
    return fi.ewm(span=period, adjust=False).mean()


def eom(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Ease of Movement."""
    distance = ((df["high"] + df["low"]) / 2).diff()
    box_ratio = (df["volume"] / 1e6) / (df["high"] - df["low"])
    raw_eom = distance / box_ratio
    return raw_eom.rolling(period).mean()


def volume_profile(df: pd.DataFrame, bins: int = 20) -> pd.DataFrame:
    """Volume Profile — volume distributed across price levels.

    Returns DataFrame with: price_low, price_high, volume, pct.
    """
    price_min = df["low"].min()
    price_max = df["high"].max()
    bin_edges = np.linspace(price_min, price_max, bins + 1)

    volumes = []
    for i in range(bins):
        mask = (df["close"] >= bin_edges[i]) & (df["close"] < bin_edges[i + 1])
        volumes.append(df.loc[mask, "volume"].sum())

    total_vol = sum(volumes)
    pct = [v / total_vol * 100 if total_vol > 0 else 0 for v in volumes]

    return pd.DataFrame({
        "price_low": bin_edges[:-1],
        "price_high": bin_edges[1:],
        "volume": volumes,
        "pct": pct,
    })


def pvt(df: pd.DataFrame) -> pd.Series:
    """Price Volume Trend."""
    return (df["close"].pct_change() * df["volume"]).cumsum()


def nvi(df: pd.DataFrame) -> pd.Series:
    """Negative Volume Index — tracks price changes on down-volume days."""
    result = pd.Series(1000.0, index=df.index)
    for i in range(1, len(df)):
        if df["volume"].iloc[i] < df["volume"].iloc[i - 1]:
            pct = (df["close"].iloc[i] - df["close"].iloc[i - 1]) / df["close"].iloc[i - 1]
            result.iloc[i] = result.iloc[i - 1] * (1 + pct)
        else:
            result.iloc[i] = result.iloc[i - 1]
    return result
