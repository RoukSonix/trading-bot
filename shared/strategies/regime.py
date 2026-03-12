"""Market regime detector with hysteresis and confidence scoring (Sprint 22+)."""

from collections import deque
from enum import Enum

import numpy as np
import pandas as pd
from loguru import logger


class MarketRegime(Enum):
    """Market regime classification."""
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    BREAKOUT = "breakout"


class MarketRegimeDetector:
    """Detect current market regime with hysteresis and confidence.

    Uses ADX for trend strength, ATR/price for volatility, Bollinger Band
    width for squeeze detection, and volume analysis for breakout confirmation.

    Stability features:
    - Hysteresis: new regime must be confirmed N consecutive times
    - Confidence: only switch when confidence > threshold
    - History smoothing: considers recent regime history
    """

    def __init__(
        self,
        adx_threshold: float = 25.0,
        vol_lookback: int = 20,
        confirmation_count: int = 1,
        confidence_threshold: float = 0.65,
        history_size: int = 20,
    ):
        self.adx_threshold = adx_threshold
        self.vol_lookback = vol_lookback
        self.confirmation_count = confirmation_count
        self.confidence_threshold = confidence_threshold

        # State for hysteresis
        self._current_regime = MarketRegime.RANGING
        self._candidate_regime: MarketRegime | None = None
        self._candidate_count = 0
        self._regime_history: deque[MarketRegime] = deque(maxlen=history_size)
        self._last_confidence = 0.0
        self._initialized = False  # First detection skips hysteresis

    @property
    def current_regime(self) -> MarketRegime:
        return self._current_regime

    @property
    def confidence(self) -> float:
        return self._last_confidence

    def detect(self, candles: list[dict], indicators: dict) -> MarketRegime:
        """Analyze market and return stable regime with hysteresis.

        The raw regime is computed every call, but the returned regime
        only changes when the new regime has been confirmed
        `confirmation_count` times consecutively AND confidence exceeds
        the threshold.
        """
        if not candles or len(candles) < 2:
            return self._current_regime

        raw_regime, confidence = self._detect_raw(candles, indicators)
        self._last_confidence = confidence
        self._regime_history.append(raw_regime)

        # First detection: set regime immediately without hysteresis
        if not self._initialized:
            self._initialized = True
            self._current_regime = raw_regime
            logger.info(
                f"Initial regime set: {raw_regime.value} "
                f"(confidence={confidence:.0%})"
            )
            return self._current_regime

        # --- Hysteresis logic ---
        if raw_regime != self._current_regime:
            if raw_regime == self._candidate_regime:
                self._candidate_count += 1
            else:
                # New candidate
                self._candidate_regime = raw_regime
                self._candidate_count = 1

            # Check if confirmed enough times with sufficient confidence
            if (
                self._candidate_count >= self.confirmation_count
                and confidence >= self.confidence_threshold
            ):
                old = self._current_regime
                self._current_regime = raw_regime
                self._candidate_regime = None
                self._candidate_count = 0
                logger.info(
                    f"Regime confirmed: {old.value} -> {raw_regime.value} "
                    f"(confidence={confidence:.0%}, after {self.confirmation_count} confirmations)"
                )
        else:
            # Current regime still holds, reset candidate
            self._candidate_regime = None
            self._candidate_count = 0

        return self._current_regime

    def _detect_raw(self, candles: list[dict], indicators: dict) -> tuple[MarketRegime, float]:
        """Detect raw regime with confidence score.

        Returns:
            Tuple of (regime, confidence 0.0-1.0)
        """
        price = candles[-1]["close"]

        # --- Indicators ---
        adx = indicators.get("adx", 0)
        atr = indicators.get("atr", 0)
        atr_pct = (atr / price * 100) if price > 0 else 0

        ema_fast = indicators.get("ema_8", price)
        ema_slow = indicators.get("ema_21", price)

        bb_upper = indicators.get("bb_upper", price * 1.02)
        bb_lower = indicators.get("bb_lower", price * 0.98)
        bb_middle = indicators.get("bb_middle", price)
        bb_width = ((bb_upper - bb_lower) / bb_middle * 100) if bb_middle > 0 else 4.0

        highest_20 = indicators.get("highest_20", float("inf"))
        lowest_20 = indicators.get("lowest_20", 0)
        volume = candles[-1].get("volume", 0)
        volume_sma = indicators.get("volume_sma", volume)
        high_volume = volume > volume_sma * 1.5 if volume_sma > 0 else False

        # --- Scoring each regime ---
        scores: dict[MarketRegime, float] = {}

        # Breakout: new extreme + volume
        breakout_score = 0.0
        if price >= highest_20 and high_volume:
            breakout_score = 0.7 + min(0.3, (volume / volume_sma - 1.5) * 0.2) if volume_sma > 0 else 0.7
        elif price <= lowest_20 and high_volume:
            breakout_score = 0.7 + min(0.3, (volume / volume_sma - 1.5) * 0.2) if volume_sma > 0 else 0.7
        scores[MarketRegime.BREAKOUT] = breakout_score

        # High volatility: ATR > 3% or wide BB
        hv_score = 0.0
        if atr_pct > 3.0:
            hv_score = min(1.0, 0.5 + (atr_pct - 3.0) * 0.15)
        if bb_width > 8.0:
            hv_score = max(hv_score, min(1.0, 0.5 + (bb_width - 8.0) * 0.1))
        scores[MarketRegime.HIGH_VOLATILITY] = hv_score

        # Low volatility: tight BB or low ATR
        lv_score = 0.0
        if bb_width < 2.0:
            lv_score = min(1.0, 0.5 + (2.0 - bb_width) * 0.4)
        if atr_pct < 0.5:
            lv_score = max(lv_score, min(1.0, 0.5 + (0.5 - atr_pct) * 0.8))
        scores[MarketRegime.LOW_VOLATILITY] = lv_score

        # Trending up: ADX strong + EMA bullish
        tu_score = 0.0
        if adx > self.adx_threshold and ema_fast > ema_slow:
            adx_strength = min(1.0, (adx - self.adx_threshold) / 25.0)
            ema_spread = abs(ema_fast - ema_slow) / price * 100
            spread_score = min(0.3, ema_spread * 0.1)
            tu_score = 0.4 + adx_strength * 0.4 + spread_score
        scores[MarketRegime.TRENDING_UP] = tu_score

        # Trending down: ADX strong + EMA bearish
        td_score = 0.0
        if adx > self.adx_threshold and ema_fast < ema_slow:
            adx_strength = min(1.0, (adx - self.adx_threshold) / 25.0)
            ema_spread = abs(ema_fast - ema_slow) / price * 100
            spread_score = min(0.3, ema_spread * 0.1)
            td_score = 0.4 + adx_strength * 0.4 + spread_score
        scores[MarketRegime.TRENDING_DOWN] = td_score

        # Ranging: default when nothing else strong
        ranging_score = 0.3  # Base score
        if adx < self.adx_threshold:
            ranging_score += min(0.4, (self.adx_threshold - adx) / self.adx_threshold * 0.4)
        if 2.0 <= bb_width <= 6.0:
            ranging_score += 0.2
        scores[MarketRegime.RANGING] = ranging_score

        # --- Pick winner ---
        best_regime = max(scores, key=scores.get)
        best_score = scores[best_regime]

        # Confidence = how much the winner stands out
        sorted_scores = sorted(scores.values(), reverse=True)
        if len(sorted_scores) > 1 and sorted_scores[0] > 0:
            margin = sorted_scores[0] - sorted_scores[1]
            confidence = min(1.0, best_score * 0.7 + margin * 0.3)
        else:
            confidence = best_score

        return best_regime, confidence

    def get_status(self) -> dict:
        """Get detector status for dashboard/logging."""
        history_counts = {}
        for r in self._regime_history:
            history_counts[r.value] = history_counts.get(r.value, 0) + 1

        return {
            "current_regime": self._current_regime.value,
            "confidence": round(self._last_confidence, 3),
            "candidate": self._candidate_regime.value if self._candidate_regime else None,
            "candidate_confirmations": self._candidate_count,
            "required_confirmations": self.confirmation_count,
            "recent_history": history_counts,
        }

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

        ema_8 = close.ewm(span=8, adjust=False).mean()
        ema_21 = close.ewm(span=21, adjust=False).mean()

        delta = close.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.ewm(alpha=1 / 14, min_periods=14).mean()
        avg_loss = loss.ewm(alpha=1 / 14, min_periods=14).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        sma_20 = close.rolling(20).mean()
        std_20 = close.rolling(20).std()
        bb_upper = sma_20 + 2 * std_20
        bb_lower = sma_20 - 2 * std_20

        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1 / 14, min_periods=14).mean()

        adx = self._calc_adx(high, low, close)

        highest_20 = high.rolling(20).max()
        lowest_20 = low.rolling(20).min()
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
