"""Market regime detector using multiple indicators (Sprint 22)."""

from enum import Enum

import numpy as np
import pandas as pd


class MarketRegime(Enum):
    """Market regime classification."""
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    BREAKOUT = "breakout"


class MarketRegimeDetector:
    """Detect current market regime using multiple indicators.

    Uses ADX for trend strength, ATR/price for volatility, Bollinger Band
    width for squeeze detection, and volume analysis for breakout confirmation.
    """

    def __init__(self, adx_threshold: float = 25.0, vol_lookback: int = 20):
        self.adx_threshold = adx_threshold
        self.vol_lookback = vol_lookback

    def detect(self, candles: list[dict], indicators: dict) -> MarketRegime:
        """Analyze market and return current regime.

        Args:
            candles: List of OHLCV dicts with at least 'close', 'high', 'low', 'volume'.
            indicators: Dict with precomputed indicator values. Expected keys:
                adx, atr, bb_upper, bb_lower, bb_middle, ema_8, ema_21,
                rsi_14, highest_20, lowest_20, volume_sma.

        Returns:
            Current MarketRegime.
        """
        if not candles or len(candles) < 2:
            return MarketRegime.RANGING

        price = candles[-1]["close"]

        # --- Trend strength via ADX ---
        adx = indicators.get("adx", 0)
        strong_trend = adx > self.adx_threshold

        # --- Trend direction via EMA crossover ---
        ema_fast = indicators.get("ema_8", price)
        ema_slow = indicators.get("ema_21", price)
        trending_up = ema_fast > ema_slow
        trending_down = ema_fast < ema_slow

        # --- Volatility via ATR / price ratio ---
        atr = indicators.get("atr", 0)
        atr_pct = (atr / price * 100) if price > 0 else 0

        # --- BB squeeze detection ---
        bb_upper = indicators.get("bb_upper", price * 1.02)
        bb_lower = indicators.get("bb_lower", price * 0.98)
        bb_middle = indicators.get("bb_middle", price)
        bb_width = ((bb_upper - bb_lower) / bb_middle * 100) if bb_middle > 0 else 4.0

        # --- Breakout detection ---
        highest_20 = indicators.get("highest_20", float("inf"))
        lowest_20 = indicators.get("lowest_20", 0)
        volume = candles[-1].get("volume", 0)
        volume_sma = indicators.get("volume_sma", volume)
        high_volume = volume > volume_sma * 1.5 if volume_sma > 0 else False

        # Check for breakout: new 20-period extreme + high volume
        is_breakout_up = price >= highest_20 and high_volume
        is_breakout_down = price <= lowest_20 and high_volume

        if is_breakout_up or is_breakout_down:
            return MarketRegime.BREAKOUT

        # Check for high volatility: ATR > 3% of price or wide BB
        if atr_pct > 3.0 or bb_width > 8.0:
            return MarketRegime.HIGH_VOLATILITY

        # Check for low volatility / BB squeeze
        if bb_width < 2.0 or atr_pct < 0.5:
            return MarketRegime.LOW_VOLATILITY

        # Trending regimes
        if strong_trend:
            if trending_up:
                return MarketRegime.TRENDING_UP
            elif trending_down:
                return MarketRegime.TRENDING_DOWN

        return MarketRegime.RANGING

    def detect_from_df(self, df: pd.DataFrame) -> MarketRegime:
        """Convenience: detect regime directly from OHLCV DataFrame.

        Computes indicators internally. Requires columns: open, high, low,
        close, volume with at least 30 rows.
        """
        if len(df) < 30:
            return MarketRegime.RANGING

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        # EMA
        ema_8 = close.ewm(span=8, adjust=False).mean()
        ema_21 = close.ewm(span=21, adjust=False).mean()

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.ewm(alpha=1 / 14, min_periods=14).mean()
        avg_loss = loss.ewm(alpha=1 / 14, min_periods=14).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        # BB
        sma_20 = close.rolling(20).mean()
        std_20 = close.rolling(20).std()
        bb_upper = sma_20 + 2 * std_20
        bb_lower = sma_20 - 2 * std_20

        # ATR
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1 / 14, min_periods=14).mean()

        # ADX
        adx = self._calc_adx(high, low, close)

        # Highest / lowest 20
        highest_20 = high.rolling(20).max()
        lowest_20 = low.rolling(20).min()

        # Volume SMA
        volume_sma = volume.rolling(20).mean()

        candles = df.reset_index().to_dict("records")
        indicators = {
            "adx": float(adx.iloc[-1]) if not np.isnan(adx.iloc[-1]) else 0,
            "atr": float(atr.iloc[-1]) if not np.isnan(atr.iloc[-1]) else 0,
            "bb_upper": float(bb_upper.iloc[-1]) if not np.isnan(bb_upper.iloc[-1]) else 0,
            "bb_lower": float(bb_lower.iloc[-1]) if not np.isnan(bb_lower.iloc[-1]) else 0,
            "bb_middle": float(sma_20.iloc[-1]) if not np.isnan(sma_20.iloc[-1]) else 0,
            "ema_8": float(ema_8.iloc[-1]),
            "ema_21": float(ema_21.iloc[-1]),
            "rsi_14": float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 50,
            "highest_20": float(highest_20.iloc[-1]) if not np.isnan(highest_20.iloc[-1]) else 0,
            "lowest_20": float(lowest_20.iloc[-1]) if not np.isnan(lowest_20.iloc[-1]) else 0,
            "volume_sma": float(volume_sma.iloc[-1]) if not np.isnan(volume_sma.iloc[-1]) else 0,
        }
        return self.detect(candles, indicators)

    @staticmethod
    def _calc_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        """Calculate ADX series."""
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr = tr.ewm(alpha=1 / period, min_periods=period).mean()
        plus_di = 100 * (plus_dm.ewm(alpha=1 / period, min_periods=period).mean() / atr)
        minus_di = 100 * (minus_dm.ewm(alpha=1 / period, min_periods=period).mean() / atr)

        dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
        adx = dx.ewm(alpha=1 / period, min_periods=period).mean()
        return adx
