"""Candlestick pattern detection."""

import pandas as pd


def _body(candle: pd.Series) -> float:
    return abs(candle["close"] - candle["open"])


def _range(candle: pd.Series) -> float:
    return candle["high"] - candle["low"]


def _upper_shadow(candle: pd.Series) -> float:
    return candle["high"] - max(candle["close"], candle["open"])


def _lower_shadow(candle: pd.Series) -> float:
    return min(candle["close"], candle["open"]) - candle["low"]


def _is_bullish(candle: pd.Series) -> bool:
    return candle["close"] > candle["open"]


def doji(candle: pd.Series, threshold: float = 0.05) -> bool:
    """Doji detection — body is very small relative to range."""
    r = _range(candle)
    if r == 0:
        return True
    return _body(candle) / r < threshold


def hammer(candle: pd.Series, body_ratio: float = 0.3, shadow_ratio: float = 2.0) -> str | None:
    """Hammer / Hanging Man detection.

    Returns 'hammer' (bullish), 'hanging_man' (bearish), or None.
    """
    body = _body(candle)
    r = _range(candle)
    lower = _lower_shadow(candle)
    upper = _upper_shadow(candle)

    if r == 0 or body == 0:
        return None

    if body / r > body_ratio:
        return None
    if lower < shadow_ratio * body:
        return None
    if upper > body * 0.5:
        return None

    return "hammer" if _is_bullish(candle) else "hanging_man"


def engulfing(candles: pd.DataFrame) -> str | None:
    """Bullish/Bearish Engulfing from last 2 candles.

    Returns 'bullish_engulfing', 'bearish_engulfing', or None.
    """
    if len(candles) < 2:
        return None

    prev = candles.iloc[-2]
    curr = candles.iloc[-1]

    if (
        not _is_bullish(prev)
        and _is_bullish(curr)
        and curr["open"] <= prev["close"]
        and curr["close"] >= prev["open"]
    ):
        return "bullish_engulfing"

    if (
        _is_bullish(prev)
        and not _is_bullish(curr)
        and curr["open"] >= prev["close"]
        and curr["close"] <= prev["open"]
    ):
        return "bearish_engulfing"

    return None


def morning_star(candles: pd.DataFrame) -> str | None:
    """Morning Star / Evening Star from last 3 candles.

    Returns 'morning_star', 'evening_star', or None.
    """
    if len(candles) < 3:
        return None

    first = candles.iloc[-3]
    second = candles.iloc[-2]
    third = candles.iloc[-1]

    small_body = _body(second) < _body(first) * 0.3

    # Morning Star: bearish, small body, bullish
    if (
        not _is_bullish(first)
        and small_body
        and _is_bullish(third)
        and third["close"] > (first["open"] + first["close"]) / 2
    ):
        return "morning_star"

    # Evening Star: bullish, small body, bearish
    if (
        _is_bullish(first)
        and small_body
        and not _is_bullish(third)
        and third["close"] < (first["open"] + first["close"]) / 2
    ):
        return "evening_star"

    return None


def three_soldiers(candles: pd.DataFrame) -> str | None:
    """Three White Soldiers / Three Black Crows from last 3 candles.

    Returns 'three_white_soldiers', 'three_black_crows', or None.
    """
    if len(candles) < 3:
        return None

    c1 = candles.iloc[-3]
    c2 = candles.iloc[-2]
    c3 = candles.iloc[-1]

    # Three White Soldiers: 3 consecutive bullish candles, each closing higher
    if (
        _is_bullish(c1) and _is_bullish(c2) and _is_bullish(c3)
        and c2["close"] > c1["close"]
        and c3["close"] > c2["close"]
        and c2["open"] > c1["open"]
        and c3["open"] > c2["open"]
    ):
        return "three_white_soldiers"

    # Three Black Crows: 3 consecutive bearish candles, each closing lower
    if (
        not _is_bullish(c1) and not _is_bullish(c2) and not _is_bullish(c3)
        and c2["close"] < c1["close"]
        and c3["close"] < c2["close"]
        and c2["open"] < c1["open"]
        and c3["open"] < c2["open"]
    ):
        return "three_black_crows"

    return None
