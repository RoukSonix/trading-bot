"""Indicator correlation analysis to avoid redundancy."""

from typing import Callable

import pandas as pd


class IndicatorCorrelation:
    """Analyze correlation between indicators to avoid redundancy."""

    def calculate_matrix(
        self,
        df: pd.DataFrame,
        indicators: list[tuple[str, Callable, dict]],
    ) -> pd.DataFrame:
        """Calculate correlation matrix between indicator outputs.

        Args:
            df: OHLCV DataFrame.
            indicators: List of (name, function, kwargs) tuples.

        Returns:
            Correlation matrix as a DataFrame.
        """
        series_dict = {}
        for name, fn, kwargs in indicators:
            raw = fn(df, **kwargs)
            if isinstance(raw, pd.Series):
                series_dict[name] = raw
            elif isinstance(raw, pd.DataFrame):
                series_dict[name] = raw.iloc[:, 0]
            elif isinstance(raw, tuple):
                first = raw[0]
                if isinstance(first, pd.Series):
                    series_dict[name] = first
            # Skip dicts/scalars

        combined = pd.DataFrame(series_dict)
        return combined.corr()

    def find_redundant(
        self, matrix: pd.DataFrame, threshold: float = 0.9
    ) -> list[tuple[str, str, float]]:
        """Find highly correlated (redundant) indicator pairs.

        Returns list of (indicator_a, indicator_b, correlation) tuples.
        """
        redundant = []
        cols = matrix.columns
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                corr = abs(matrix.iloc[i, j])
                if corr >= threshold:
                    redundant.append((cols[i], cols[j], round(float(matrix.iloc[i, j]), 4)))
        return redundant

    def suggest_best_combination(
        self,
        df: pd.DataFrame,
        indicators: list[tuple[str, Callable, dict]],
        n: int = 5,
    ) -> list[str]:
        """Suggest best N non-correlated indicators using greedy selection.

        Picks indicators that are least correlated with already-selected ones.
        """
        matrix = self.calculate_matrix(df, indicators)
        if matrix.empty:
            return []

        names = list(matrix.columns)
        if len(names) <= n:
            return names

        # Start with the indicator that has lowest average absolute correlation
        avg_corr = matrix.abs().mean()
        selected = [avg_corr.idxmin()]

        while len(selected) < n and len(selected) < len(names):
            remaining = [name for name in names if name not in selected]
            if not remaining:
                break

            # Pick the remaining indicator with lowest max correlation to selected
            best_name = None
            best_max_corr = float("inf")
            for name in remaining:
                max_corr = max(abs(matrix.loc[name, s]) for s in selected)
                if max_corr < best_max_corr:
                    best_max_corr = max_corr
                    best_name = name

            if best_name:
                selected.append(best_name)
            else:
                break

        return selected
