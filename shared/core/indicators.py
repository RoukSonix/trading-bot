"""Technical analysis indicators."""

import pandas as pd


class Indicators:
    """Technical analysis indicators calculator."""
    
    @staticmethod
    def to_dataframe(candles: list[dict]) -> pd.DataFrame:
        """Convert candles list to DataFrame.
        
        Args:
            candles: List of OHLCV dicts
            
        Returns:
            DataFrame with OHLCV columns and datetime index
        """
        df = pd.DataFrame(candles)
        
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
        """Simple Moving Average.
        
        Args:
            df: OHLCV DataFrame
            period: SMA period
            column: Column to calculate SMA on
            
        Returns:
            SMA series
        """
        return df[column].rolling(window=period).mean()
    
    @staticmethod
    def ema(df: pd.DataFrame, period: int = 20, column: str = "close") -> pd.Series:
        """Exponential Moving Average.
        
        Args:
            df: OHLCV DataFrame
            period: EMA period
            column: Column to calculate EMA on
            
        Returns:
            EMA series
        """
        return df[column].ewm(span=period, adjust=False).mean()
    
    @staticmethod
    def rsi(df: pd.DataFrame, period: int = 14, column: str = "close") -> pd.Series:
        """Relative Strength Index.
        
        Args:
            df: OHLCV DataFrame
            period: RSI period
            column: Column to calculate RSI on
            
        Returns:
            RSI series (0-100)
        """
        delta = df[column].diff()
        
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
        avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    @staticmethod
    def bollinger_bands(
        df: pd.DataFrame,
        period: int = 20,
        std_dev: float = 2.0,
        column: str = "close"
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Bollinger Bands.
        
        Args:
            df: OHLCV DataFrame
            period: SMA period
            std_dev: Standard deviation multiplier
            column: Column to calculate on
            
        Returns:
            Tuple of (upper_band, middle_band, lower_band)
        """
        middle = df[column].rolling(window=period).mean()
        std = df[column].rolling(window=period).std()
        
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        
        return upper, middle, lower
    
    @staticmethod
    def macd(
        df: pd.DataFrame,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
        column: str = "close"
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """MACD (Moving Average Convergence Divergence).
        
        Args:
            df: OHLCV DataFrame
            fast: Fast EMA period
            slow: Slow EMA period
            signal: Signal line period
            column: Column to calculate on
            
        Returns:
            Tuple of (macd_line, signal_line, histogram)
        """
        ema_fast = df[column].ewm(span=fast, adjust=False).mean()
        ema_slow = df[column].ewm(span=slow, adjust=False).mean()
        
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram
    
    @staticmethod
    def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Average True Range (volatility indicator).
        
        Args:
            df: OHLCV DataFrame
            period: ATR period
            
        Returns:
            ATR series
        """
        high = df["high"]
        low = df["low"]
        close = df["close"]
        
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1/period, min_periods=period).mean()
        
        return atr
    
    @classmethod
    def add_all_indicators(cls, df: pd.DataFrame) -> pd.DataFrame:
        """Add all common indicators to DataFrame.
        
        Args:
            df: OHLCV DataFrame
            
        Returns:
            DataFrame with added indicator columns
        """
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
