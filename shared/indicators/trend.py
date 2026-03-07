"""Trend indicators for technical analysis."""

import numpy as np
import pandas as pd


def sma(df: pd.DataFrame, period: int = 20, column: str = "close") -> pd.Series:
    """Simple Moving Average."""
    return df[column].rolling(window=period).mean()


def ema(df: pd.DataFrame, period: int = 20, column: str = "close") -> pd.Series:
    """Exponential Moving Average."""
    return df[column].ewm(span=period, adjust=False).mean()


def wma(df: pd.DataFrame, period: int = 20, column: str = "close") -> pd.Series:
    """Weighted Moving Average — recent prices weighted more heavily."""
    weights = np.arange(1, period + 1, dtype=float)
    return df[column].rolling(window=period).apply(
        lambda x: np.dot(x, weights) / weights.sum(), raw=True
    )


def dema(df: pd.DataFrame, period: int = 20, column: str = "close") -> pd.Series:
    """Double Exponential Moving Average — reduced lag vs EMA."""
    ema1 = df[column].ewm(span=period, adjust=False).mean()
    ema2 = ema1.ewm(span=period, adjust=False).mean()
    return 2 * ema1 - ema2


def tema(df: pd.DataFrame, period: int = 20, column: str = "close") -> pd.Series:
    """Triple Exponential Moving Average — even less lag than DEMA."""
    ema1 = df[column].ewm(span=period, adjust=False).mean()
    ema2 = ema1.ewm(span=period, adjust=False).mean()
    ema3 = ema2.ewm(span=period, adjust=False).mean()
    return 3 * ema1 - 3 * ema2 + ema3


def kama(df: pd.DataFrame, period: int = 10, column: str = "close") -> pd.Series:
    """Kaufman Adaptive Moving Average — adapts to market volatility."""
    close = df[column]
    fast_sc = 2.0 / (2 + 1)   # fast EMA constant
    slow_sc = 2.0 / (30 + 1)  # slow EMA constant

    result = pd.Series(np.nan, index=close.index)
    result.iloc[period - 1] = close.iloc[period - 1]

    for i in range(period, len(close)):
        direction = abs(close.iloc[i] - close.iloc[i - period])
        volatility = close.diff().abs().iloc[i - period + 1 : i + 1].sum()

        if volatility == 0:
            er = 0.0
        else:
            er = direction / volatility

        sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2
        result.iloc[i] = result.iloc[i - 1] + sc * (close.iloc[i] - result.iloc[i - 1])

    return result


def vwap(df: pd.DataFrame) -> pd.Series:
    """Volume Weighted Average Price."""
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    cum_tp_vol = (typical_price * df["volume"]).cumsum()
    cum_vol = df["volume"].cumsum()
    return cum_tp_vol / cum_vol


def supertrend(
    df: pd.DataFrame, period: int = 10, multiplier: float = 3.0
) -> pd.DataFrame:
    """Supertrend indicator.

    Returns DataFrame with columns: supertrend, direction (1=up, -1=down).
    """
    hl2 = (df["high"] + df["low"]) / 2
    high = df["high"]
    low = df["low"]
    close = df["close"]

    # ATR
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, min_periods=period).mean()

    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr

    st = pd.Series(np.nan, index=df.index)
    direction = pd.Series(1, index=df.index)

    for i in range(period, len(df)):
        if i == period:
            st.iloc[i] = upper_band.iloc[i]
            direction.iloc[i] = -1 if close.iloc[i] > upper_band.iloc[i] else 1
            continue

        prev_st = st.iloc[i - 1]

        if direction.iloc[i - 1] == 1:  # previous was downtrend
            new_lower = lower_band.iloc[i]
            if not np.isnan(prev_st):
                new_lower = max(new_lower, prev_st)
            if close.iloc[i] > new_lower:
                st.iloc[i] = new_lower
                direction.iloc[i] = 1
            else:
                st.iloc[i] = upper_band.iloc[i]
                direction.iloc[i] = -1
        else:  # previous was uptrend
            new_upper = upper_band.iloc[i]
            if not np.isnan(prev_st):
                new_upper = min(new_upper, prev_st)
            if close.iloc[i] < new_upper:
                st.iloc[i] = new_upper
                direction.iloc[i] = -1
            else:
                st.iloc[i] = lower_band.iloc[i]
                direction.iloc[i] = 1

    return pd.DataFrame({"supertrend": st, "direction": direction}, index=df.index)


def psar(
    df: pd.DataFrame, af: float = 0.02, max_af: float = 0.2
) -> pd.Series:
    """Parabolic SAR."""
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    n = len(df)

    psar_arr = np.full(n, np.nan)
    direction = np.ones(n)  # 1 = long, -1 = short
    af_val = af
    ep = low[0]

    psar_arr[0] = high[0]
    direction[0] = -1

    for i in range(1, n):
        prev_psar = psar_arr[i - 1]

        if direction[i - 1] == 1:  # long
            psar_arr[i] = prev_psar + af_val * (ep - prev_psar)
            psar_arr[i] = min(psar_arr[i], low[i - 1])
            if i >= 2:
                psar_arr[i] = min(psar_arr[i], low[i - 2])

            if low[i] < psar_arr[i]:
                direction[i] = -1
                psar_arr[i] = ep
                ep = low[i]
                af_val = af
            else:
                direction[i] = 1
                if high[i] > ep:
                    ep = high[i]
                    af_val = min(af_val + af, max_af)
        else:  # short
            psar_arr[i] = prev_psar + af_val * (ep - prev_psar)
            psar_arr[i] = max(psar_arr[i], high[i - 1])
            if i >= 2:
                psar_arr[i] = max(psar_arr[i], high[i - 2])

            if high[i] > psar_arr[i]:
                direction[i] = 1
                psar_arr[i] = ep
                ep = high[i]
                af_val = af
            else:
                direction[i] = -1
                if low[i] < ep:
                    ep = low[i]
                    af_val = min(af_val + af, max_af)

    return pd.Series(psar_arr, index=df.index, name="psar")


def ichimoku(
    df: pd.DataFrame,
    tenkan: int = 9,
    kijun: int = 26,
    senkou: int = 52,
) -> pd.DataFrame:
    """Ichimoku Cloud.

    Returns DataFrame with: tenkan_sen, kijun_sen, senkou_a, senkou_b, chikou.
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]

    tenkan_sen = (high.rolling(tenkan).max() + low.rolling(tenkan).min()) / 2
    kijun_sen = (high.rolling(kijun).max() + low.rolling(kijun).min()) / 2
    senkou_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun)
    senkou_b = ((high.rolling(senkou).max() + low.rolling(senkou).min()) / 2).shift(kijun)
    chikou = close.shift(-kijun)

    return pd.DataFrame({
        "tenkan_sen": tenkan_sen,
        "kijun_sen": kijun_sen,
        "senkou_a": senkou_a,
        "senkou_b": senkou_b,
        "chikou": chikou,
    }, index=df.index)


def adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Average Directional Index.

    Returns DataFrame with: adx, plus_di, minus_di.
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]

    plus_dm = high.diff()
    minus_dm = -low.diff()

    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1 / period, min_periods=period).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, min_periods=period).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, min_periods=period).mean() / atr

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx_val = dx.ewm(alpha=1 / period, min_periods=period).mean()

    return pd.DataFrame({
        "adx": adx_val,
        "plus_di": plus_di,
        "minus_di": minus_di,
    }, index=df.index)


def aroon(df: pd.DataFrame, period: int = 25) -> pd.DataFrame:
    """Aroon Up/Down indicator.

    Returns DataFrame with: aroon_up, aroon_down.
    """
    high = df["high"]
    low = df["low"]

    aroon_up = high.rolling(period + 1).apply(
        lambda x: x.argmax() / period * 100, raw=True
    )
    aroon_down = low.rolling(period + 1).apply(
        lambda x: x.argmin() / period * 100, raw=True
    )

    return pd.DataFrame({
        "aroon_up": aroon_up,
        "aroon_down": aroon_down,
    }, index=df.index)


def cci(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Commodity Channel Index."""
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    sma_tp = typical_price.rolling(period).mean()
    mad = typical_price.rolling(period).apply(
        lambda x: np.abs(x - x.mean()).mean(), raw=True
    )
    return (typical_price - sma_tp) / (0.015 * mad)
