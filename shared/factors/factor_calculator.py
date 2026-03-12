"""Trading factor calculations for multi-factor analysis.

Calculates momentum, volatility, RSI-based, and volume factors
from OHLCV data for use in grid optimization and trading decisions.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from loguru import logger


@dataclass
class FactorResult:
    """Result of factor calculation for a symbol."""

    symbol: str
    timestamp: pd.Timestamp | None = None

    # Momentum factors
    momentum_60d: float = 0.0  # 60-day price return
    momentum_20d: float = 0.0  # 20-day price return
    momentum_5d: float = 0.0   # 5-day price return (short-term)
    momentum_score: float = 0.0  # Normalized composite [-1, 1]

    # Volatility factors
    atr_14: float = 0.0          # Average True Range (14-period)
    atr_pct: float = 0.0         # ATR as percentage of price
    std_dev_20: float = 0.0      # 20-day return std deviation
    volatility_score: float = 0.0  # Normalized [0, 1] (higher = more volatile)

    # RSI-based factors
    rsi_14: float = 50.0         # Standard RSI
    rsi_signal: float = 0.0      # -1 (oversold), 0 (neutral), 1 (overbought)
    rsi_divergence: float = 0.0  # Price vs RSI divergence

    # Volume factors
    volume_sma_ratio: float = 1.0  # Current vol / 20-day avg vol
    obv_trend: float = 0.0        # OBV direction [-1, 1]
    volume_score: float = 0.0     # Normalized volume factor

    # Composite
    composite_score: float = 0.0   # Weighted composite of all factors [-1, 1]
    factor_data: dict = field(default_factory=dict)  # Raw data for debugging


class FactorCalculator:
    """Calculate trading factors from OHLCV data."""

    def __init__(
        self,
        momentum_weights: tuple[float, float, float] = (0.5, 0.35, 0.15),
        composite_weights: dict[str, float] | None = None,
    ):
        """Initialize factor calculator.

        Args:
            momentum_weights: Weights for (60d, 20d, 5d) momentum.
            composite_weights: Weights for composite score.
                Keys: momentum, volatility, rsi, volume.
        """
        self.momentum_weights = momentum_weights
        self.composite_weights = composite_weights or {
            "momentum": 0.35,
            "volatility": 0.20,
            "rsi": 0.25,
            "volume": 0.20,
        }

    def calculate(self, df: pd.DataFrame, symbol: str = "BTC/USDT") -> FactorResult:
        """Calculate all factors from OHLCV DataFrame.

        Args:
            df: DataFrame with columns: open, high, low, close, volume.
                Must have at least 60 rows for full factor calculation.
            symbol: Trading symbol.

        Returns:
            FactorResult with all calculated factors.
        """
        if len(df) < 20:
            logger.warning(f"Insufficient data ({len(df)} rows), need at least 20")
            return FactorResult(symbol=symbol)

        result = FactorResult(symbol=symbol)
        result.timestamp = df.index[-1] if isinstance(df.index, pd.DatetimeIndex) else None

        # Calculate individual factor groups
        self._calc_momentum(df, result)
        self._calc_volatility(df, result)
        self._calc_rsi_factors(df, result)
        self._calc_volume_factors(df, result)

        # Composite score
        w = self.composite_weights
        result.composite_score = np.clip(
            w["momentum"] * result.momentum_score
            + w["volatility"] * (1.0 - result.volatility_score)  # Low vol = positive
            + w["rsi"] * (-result.rsi_signal)  # Contrarian: oversold = positive
            + w["volume"] * result.volume_score,
            -1.0,
            1.0,
        )

        logger.debug(
            f"Factors for {symbol}: momentum={result.momentum_score:.3f}, "
            f"volatility={result.volatility_score:.3f}, rsi_signal={result.rsi_signal:.3f}, "
            f"volume={result.volume_score:.3f}, composite={result.composite_score:.3f}"
        )

        return result

    def _calc_momentum(self, df: pd.DataFrame, result: FactorResult) -> None:
        """Calculate momentum factors (price returns)."""
        close = df["close"]

        # Price returns over different lookbacks
        if len(df) >= 60:
            result.momentum_60d = (close.iloc[-1] / close.iloc[-60] - 1.0)
        if len(df) >= 20:
            result.momentum_20d = (close.iloc[-1] / close.iloc[-20] - 1.0)
        if len(df) >= 5:
            result.momentum_5d = (close.iloc[-1] / close.iloc[-5] - 1.0)

        # Weighted composite momentum score, clamped to [-1, 1]
        w = self.momentum_weights
        raw = (
            w[0] * result.momentum_60d
            + w[1] * result.momentum_20d
            + w[2] * result.momentum_5d
        )
        # Normalize: ±20% return maps to ±1
        result.momentum_score = float(np.clip(raw / 0.20, -1.0, 1.0))

    def _calc_volatility(self, df: pd.DataFrame, result: FactorResult) -> None:
        """Calculate volatility factors (ATR, std dev)."""
        high = df["high"]
        low = df["low"]
        close = df["close"]

        # ATR (14-period)
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1 / 14, min_periods=14).mean()

        result.atr_14 = float(atr.iloc[-1]) if not np.isnan(atr.iloc[-1]) else 0.0
        current_price = float(close.iloc[-1])
        result.atr_pct = (result.atr_14 / current_price * 100) if current_price > 0 else 0.0

        # 20-day return standard deviation
        returns = close.pct_change().dropna()
        if len(returns) >= 20:
            result.std_dev_20 = float(returns.iloc[-20:].std())
        elif len(returns) > 0:
            result.std_dev_20 = float(returns.std())

        # Volatility score: normalize ATR% to [0, 1]
        # Typical crypto ATR% ranges: 1-5% is normal, >5% is high
        result.volatility_score = float(np.clip(result.atr_pct / 5.0, 0.0, 1.0))

    def _calc_rsi_factors(self, df: pd.DataFrame, result: FactorResult) -> None:
        """Calculate RSI-based factors."""
        close = df["close"]
        delta = close.diff()

        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.ewm(alpha=1 / 14, min_periods=14).mean()
        avg_loss = loss.ewm(alpha=1 / 14, min_periods=14).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi = rsi.fillna(100.0)

        result.rsi_14 = float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 50.0

        # RSI signal: -1 (oversold <30), 0 (neutral), 1 (overbought >70)
        if result.rsi_14 < 30:
            result.rsi_signal = -1.0
        elif result.rsi_14 > 70:
            result.rsi_signal = 1.0
        else:
            # Linear interpolation between 30-70
            result.rsi_signal = (result.rsi_14 - 50) / 20.0

        # Price-RSI divergence (simplified)
        # Bullish divergence: price making lower lows but RSI making higher lows
        if len(df) >= 20 and len(rsi.dropna()) >= 20:
            price_trend = close.iloc[-1] - close.iloc[-20]
            rsi_trend = rsi.iloc[-1] - rsi.dropna().iloc[-20]
            # Divergence: opposite signs = divergence
            if price_trend != 0:
                result.rsi_divergence = float(np.clip(
                    -np.sign(price_trend) * np.sign(rsi_trend) * 0.5,
                    -1.0, 1.0,
                ))

    def _calc_volume_factors(self, df: pd.DataFrame, result: FactorResult) -> None:
        """Calculate volume-based factors."""
        if "volume" not in df.columns:
            return

        volume = df["volume"]
        close = df["close"]

        # Volume SMA ratio (current vs 20-day average)
        vol_sma = volume.rolling(window=20).mean()
        if not np.isnan(vol_sma.iloc[-1]) and vol_sma.iloc[-1] > 0:
            result.volume_sma_ratio = float(volume.iloc[-1] / vol_sma.iloc[-1])

        # On-Balance Volume (OBV) trend
        obv = (np.sign(close.diff()) * volume).cumsum()
        if len(obv) >= 20:
            obv_sma = obv.rolling(window=20).mean()
            if not np.isnan(obv_sma.iloc[-1]) and obv_sma.iloc[-1] != 0:
                obv_deviation = (obv.iloc[-1] - obv_sma.iloc[-1]) / abs(obv_sma.iloc[-1])
                result.obv_trend = float(np.clip(obv_deviation, -1.0, 1.0))

        # Volume score: above-average volume with positive price action is bullish
        vol_ratio_norm = float(np.clip((result.volume_sma_ratio - 1.0) / 2.0, -0.5, 0.5))
        price_direction = 1.0 if close.iloc[-1] > close.iloc[-2] else -1.0
        result.volume_score = float(np.clip(
            vol_ratio_norm * price_direction * 0.5 + result.obv_trend * 0.5,
            -1.0, 1.0,
        ))

    def calculate_from_candles(
        self,
        candles: list[dict],
        symbol: str = "BTC/USDT",
    ) -> FactorResult:
        """Calculate factors from a list of OHLCV candle dicts.

        Args:
            candles: List of dicts with keys: timestamp, open, high, low, close, volume.
            symbol: Trading symbol.

        Returns:
            FactorResult with all calculated factors.
        """
        from shared.core.indicators import Indicators

        df = Indicators.to_dataframe(candles)
        return self.calculate(df, symbol)

    def to_dict(self, result: FactorResult) -> dict:
        """Convert FactorResult to a dict suitable for AI prompts."""
        return {
            "Momentum (60d)": f"{result.momentum_60d:+.2%}",
            "Momentum (20d)": f"{result.momentum_20d:+.2%}",
            "Momentum (5d)": f"{result.momentum_5d:+.2%}",
            "Momentum Score": f"{result.momentum_score:+.3f}",
            "ATR (14)": f"{result.atr_14:.4f}",
            "ATR %": f"{result.atr_pct:.2f}%",
            "Volatility (20d StdDev)": f"{result.std_dev_20:.4f}",
            "Volatility Score": f"{result.volatility_score:.3f}",
            "RSI (14)": f"{result.rsi_14:.1f}",
            "RSI Signal": f"{result.rsi_signal:+.2f}",
            "RSI Divergence": f"{result.rsi_divergence:+.2f}",
            "Volume Ratio": f"{result.volume_sma_ratio:.2f}x",
            "OBV Trend": f"{result.obv_trend:+.3f}",
            "Volume Score": f"{result.volume_score:+.3f}",
            "Composite Score": f"{result.composite_score:+.3f}",
        }


# Global instance
factor_calculator = FactorCalculator()
