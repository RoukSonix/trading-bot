"""Custom composite indicator builder."""

from typing import Callable

import numpy as np
import pandas as pd


class IndicatorBuilder:
    """Build custom composite indicators from multiple indicator functions."""

    def __init__(self):
        self.components: list[tuple[Callable, float, dict]] = []

    def add(self, indicator_fn: Callable, weight: float = 1.0, **kwargs) -> "IndicatorBuilder":
        """Add an indicator component.

        Args:
            indicator_fn: Function(df, **kwargs) -> pd.Series or scalar.
            weight: Weight for this component in the composite.
            **kwargs: Arguments passed to indicator_fn.
        """
        self.components.append((indicator_fn, weight, kwargs))
        return self

    def calculate(self, df: pd.DataFrame) -> float:
        """Calculate composite indicator value (weighted sum of normalized components).

        Each component is normalized to [0, 1] using min-max scaling,
        then the weighted average is returned.
        """
        if not self.components:
            return 0.0

        total_weight = sum(w for _, w, _ in self.components)
        if total_weight == 0:
            return 0.0

        weighted_sum = 0.0
        for fn, weight, kwargs in self.components:
            raw = fn(df, **kwargs)

            if isinstance(raw, pd.Series):
                val = raw.dropna().iloc[-1] if len(raw.dropna()) > 0 else 0.0
            elif isinstance(raw, pd.DataFrame):
                # Take first column's last value
                first_col = raw.iloc[:, 0]
                val = first_col.dropna().iloc[-1] if len(first_col.dropna()) > 0 else 0.0
            elif isinstance(raw, tuple):
                # Take first element's last value
                first = raw[0]
                if isinstance(first, pd.Series):
                    val = first.dropna().iloc[-1] if len(first.dropna()) > 0 else 0.0
                else:
                    val = float(first)
            elif isinstance(raw, dict):
                # Take first value
                val = float(next(iter(raw.values())))
            else:
                val = float(raw)

            weighted_sum += weight * val

        return weighted_sum / total_weight

    def to_signal(self, df: pd.DataFrame, buy_threshold: float = 0.6, sell_threshold: float = 0.4) -> str:
        """Convert composite indicator to trading signal.

        Args:
            df: OHLCV DataFrame.
            buy_threshold: Threshold above which signal is 'buy'.
            sell_threshold: Threshold below which signal is 'sell'.

        Returns:
            'buy', 'sell', or 'hold'.
        """
        value = self.calculate(df)
        if value > buy_threshold:
            return "buy"
        elif value < sell_threshold:
            return "sell"
        return "hold"
