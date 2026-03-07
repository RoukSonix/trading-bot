"""Support and resistance level indicators."""

import numpy as np
import pandas as pd


def pivot_points(df: pd.DataFrame) -> dict[str, float]:
    """Standard Pivot Points from the most recent bar.

    Returns dict with keys: P, R1, R2, R3, S1, S2, S3.
    """
    high = df["high"].iloc[-1]
    low = df["low"].iloc[-1]
    close = df["close"].iloc[-1]

    p = (high + low + close) / 3
    r1 = 2 * p - low
    s1 = 2 * p - high
    r2 = p + (high - low)
    s2 = p - (high - low)
    r3 = high + 2 * (p - low)
    s3 = low - 2 * (high - p)

    return {"P": p, "R1": r1, "R2": r2, "R3": r3, "S1": s1, "S2": s2, "S3": s3}


def fibonacci_retracement(high: float, low: float) -> dict[str, float]:
    """Fibonacci retracement levels between a swing high and swing low.

    Returns dict with level names as keys and price levels as values.
    """
    diff = high - low
    return {
        "0.0": high,
        "23.6": high - 0.236 * diff,
        "38.2": high - 0.382 * diff,
        "50.0": high - 0.500 * diff,
        "61.8": high - 0.618 * diff,
        "78.6": high - 0.786 * diff,
        "100.0": low,
    }


def fibonacci_extension(
    high: float, low: float, retracement: float
) -> dict[str, float]:
    """Fibonacci extension levels.

    Args:
        high: Swing high price.
        low: Swing low price.
        retracement: Retracement point price.
    """
    diff = high - low
    return {
        "61.8": retracement + 0.618 * diff,
        "100.0": retracement + 1.000 * diff,
        "138.2": retracement + 1.382 * diff,
        "161.8": retracement + 1.618 * diff,
        "200.0": retracement + 2.000 * diff,
        "261.8": retracement + 2.618 * diff,
    }


def support_resistance_levels(
    df: pd.DataFrame, window: int = 20
) -> dict[str, list[float]]:
    """Auto-detect support and resistance levels from price action.

    Uses rolling window local minima/maxima detection.

    Returns dict with 'support' and 'resistance' lists.
    """
    high = df["high"]
    low = df["low"]

    # Find local maxima (resistance)
    resistance = []
    for i in range(window, len(df) - window):
        if high.iloc[i] == high.iloc[i - window : i + window + 1].max():
            resistance.append(float(high.iloc[i]))

    # Find local minima (support)
    support = []
    for i in range(window, len(df) - window):
        if low.iloc[i] == low.iloc[i - window : i + window + 1].min():
            support.append(float(low.iloc[i]))

    # Remove duplicates within 0.5% tolerance
    def deduplicate(levels: list[float], tol: float = 0.005) -> list[float]:
        if not levels:
            return []
        levels = sorted(levels)
        result = [levels[0]]
        for level in levels[1:]:
            if abs(level - result[-1]) / result[-1] > tol:
                result.append(level)
        return result

    return {
        "support": deduplicate(support),
        "resistance": deduplicate(resistance),
    }
