"""Technical analysis indicators.

Backward-compatible wrapper — delegates to shared.indicators module.
"""

import pandas as pd

from shared.indicators import momentum, trend, volatility


class Indicators:
    """Technical analysis indicators calculator.

    Legacy class kept for backward compatibility.
    New code should import directly from shared.indicators.
    """

    @staticmethod
    def to_dataframe(candles: list[dict]) -> pd.DataFrame:
        """Convert candles list to DataFrame.

        Args:
            candles: List of OHLCV dicts

        Returns:
            DataFrame with OHLCV columns and datetime index
        """
        df = pd.DataFrame(candles)
        if df.empty:
            return df

        # Convert timestamp to datetime
        if "timestamp" in df.columns:
            # Handle milliseconds
            if df["timestamp"].iloc[0] > 1e12:
                df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
            else:
                df["datetime"] = pd.to_datetime(df["timestamp"], unit="s")
            df.set_index("datetime", inplace=True)
        elif "datetime" in df.columns:
            df.set_index("datetime", inplace=True)

        return df

    @staticmethod
    def sma(df: pd.DataFrame, period: int = 20, column: str = "close") -> pd.Series:
        """Simple Moving Average."""
        return trend.sma(df, period, column)

    @staticmethod
    def ema(df: pd.DataFrame, period: int = 20, column: str = "close") -> pd.Series:
        """Exponential Moving Average."""
        return trend.ema(df, period, column)

    @staticmethod
    def rsi(df: pd.DataFrame, period: int = 14, column: str = "close") -> pd.Series:
        """Relative Strength Index."""
        return momentum.rsi(df, period, column)

    @staticmethod
    def bollinger_bands(
        df: pd.DataFrame,
        period: int = 20,
        std_dev: float = 2.0,
        column: str = "close",
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Bollinger Bands — returns (upper, middle, lower)."""
        return volatility.bollinger_bands(df, period, std_dev, column)

    @staticmethod
    def macd(
        df: pd.DataFrame,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
        column: str = "close",
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """MACD — returns (macd_line, signal_line, histogram)."""
        return momentum.macd(df, fast, slow, signal, column)

    @staticmethod
    def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Average True Range."""
        return volatility.atr(df, period)

    @classmethod
    def add_all_indicators(cls, df: pd.DataFrame) -> pd.DataFrame:
        """Add all common indicators to DataFrame."""
        df = df.copy()

        # Moving Averages
        df["sma_20"] = cls.sma(df, 20)
        df["sma_50"] = cls.sma(df, 50)
        df["ema_12"] = cls.ema(df, 12)
        df["ema_26"] = cls.ema(df, 26)

        # RSI
        df["rsi"] = cls.rsi(df, 14)

        # Bollinger Bands
        df["bb_upper"], df["bb_middle"], df["bb_lower"] = cls.bollinger_bands(df)

        # MACD
        df["macd"], df["macd_signal"], df["macd_hist"] = cls.macd(df)

        # ATR
        df["atr"] = cls.atr(df)

        return df
