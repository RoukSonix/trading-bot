"""
Factors Mixin for AIGridStrategy — wraps shared/factors/.

Provides factor analysis (momentum, volatility, RSI, volume) and
market regime detection for grid trading decisions.
Falls back gracefully when shared/factors/ is unavailable.
"""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Try importing shared factor modules; may not be available in all envs
try:
    from shared.factors.factor_calculator import FactorCalculator, FactorResult
    from shared.factors.factor_strategy import FactorStrategy, FactorScore, MarketRegime, GridAction
    _HAS_FACTORS = True
except ImportError:
    _HAS_FACTORS = False
    logger.info("shared.factors not available — using built-in factor analysis")


class FactorsMixin:
    """Mixin providing factor analysis capabilities to the Jesse strategy.

    Wraps shared/factors/ with error handling and built-in fallback.
    All methods return plain dicts/floats so the strategy doesn't depend
    on shared module dataclasses.
    """

    def __init__(self):
        self._calculator = None
        self._strategy = None

        if _HAS_FACTORS:
            try:
                self._calculator = FactorCalculator()
                self._strategy = FactorStrategy()
            except Exception as e:
                logger.warning(f"Failed to initialize factor modules: {e}")

    @property
    def factors_available(self) -> bool:
        """Check if shared factor modules are available."""
        return self._calculator is not None and self._strategy is not None

    def calculate_factors(self, candles: np.ndarray) -> dict:
        """Calculate trading factors from candle data.

        Args:
            candles: Numpy array of OHLCV candles
                     [[timestamp, open, high, low, close, volume], ...].

        Returns:
            Dict with momentum, volatility, rsi_signal, volume factors
            and composite_score.
        """
        try:
            df = self._candles_to_dataframe(candles)
            if df is None or len(df) < 20:
                return self._default_factors()

            if self.factors_available:
                result = self._calculator.calculate(df)
                return {
                    'momentum_score': result.momentum_score,
                    'momentum_5d': result.momentum_5d,
                    'momentum_20d': result.momentum_20d,
                    'momentum_60d': result.momentum_60d,
                    'volatility_score': result.volatility_score,
                    'atr_pct': result.atr_pct,
                    'rsi_14': result.rsi_14,
                    'rsi_signal': result.rsi_signal,
                    'rsi_divergence': result.rsi_divergence,
                    'volume_score': result.volume_score,
                    'volume_sma_ratio': result.volume_sma_ratio,
                    'composite_score': result.composite_score,
                }
            else:
                return self._calculate_factors_builtin(df)

        except Exception as e:
            logger.warning(f"Factor calculation failed: {e}")
            return self._default_factors()

    def detect_regime(self, factors: dict) -> str:
        """Detect current market regime from factors.

        Args:
            factors: Dict from calculate_factors().

        Returns:
            One of: 'trending_up', 'trending_down', 'ranging',
            'high_volatility', 'low_volatility'.
        """
        try:
            if self.factors_available:
                # Reconstruct FactorResult for the strategy module
                fr = FactorResult(
                    symbol='BTC/USDT',
                    momentum_score=factors.get('momentum_score', 0.0),
                    volatility_score=factors.get('volatility_score', 0.0),
                    rsi_14=factors.get('rsi_14', 50.0),
                )
                score = self._strategy.score(fr)
                return score.regime.value
            else:
                return self._detect_regime_builtin(factors)
        except Exception as e:
            logger.warning(f"Regime detection failed: {e}")
            return 'ranging'

    def grid_suitability_score(self, factors: dict) -> float:
        """Calculate how suitable current market is for grid trading.

        Args:
            factors: Dict from calculate_factors().

        Returns:
            Float 0.0-1.0 (higher = more suitable for grid trading).
        """
        try:
            if self.factors_available:
                fr = FactorResult(
                    symbol='BTC/USDT',
                    momentum_score=factors.get('momentum_score', 0.0),
                    momentum_20d=factors.get('momentum_20d', 0.0),
                    momentum_60d=factors.get('momentum_60d', 0.0),
                    volatility_score=factors.get('volatility_score', 0.0),
                    atr_pct=factors.get('atr_pct', 0.0),
                    rsi_14=factors.get('rsi_14', 50.0),
                    rsi_signal=factors.get('rsi_signal', 0.0),
                    volume_sma_ratio=factors.get('volume_sma_ratio', 1.0),
                    composite_score=factors.get('composite_score', 0.0),
                )
                score = self._strategy.score(fr)
                return score.grid_suitability
            else:
                return self._grid_suitability_builtin(factors)
        except Exception as e:
            logger.warning(f"Grid suitability calculation failed: {e}")
            return 0.5

    def factors_to_ai_context(self, factors: dict) -> str:
        """Format factors for AI prompt context.

        Args:
            factors: Dict from calculate_factors().

        Returns:
            Formatted string for AI prompt.
        """
        regime = self.detect_regime(factors)
        suitability = self.grid_suitability_score(factors)

        return (
            f"## Factor Analysis\n"
            f"- Regime: {regime}\n"
            f"- Grid Suitability: {suitability:.0%}\n"
            f"- Composite Score: {factors.get('composite_score', 0):+.3f}\n"
            f"- Momentum: {factors.get('momentum_score', 0):+.3f}\n"
            f"- Volatility: {factors.get('volatility_score', 0):.3f} (ATR {factors.get('atr_pct', 0):.2f}%)\n"
            f"- RSI: {factors.get('rsi_14', 50):.1f} (signal: {factors.get('rsi_signal', 0):+.2f})\n"
            f"- Volume: {factors.get('volume_score', 0):+.3f} ({factors.get('volume_sma_ratio', 1):.2f}x avg)\n"
        )

    # ==================== Built-in fallback ====================

    def _calculate_factors_builtin(self, df: pd.DataFrame) -> dict:
        """Calculate factors without shared module dependency."""
        close = df['close']
        result = self._default_factors()

        # Momentum
        if len(df) >= 5:
            result['momentum_5d'] = float(close.iloc[-1] / close.iloc[-5] - 1.0)
        if len(df) >= 20:
            result['momentum_20d'] = float(close.iloc[-1] / close.iloc[-20] - 1.0)
        if len(df) >= 60:
            result['momentum_60d'] = float(close.iloc[-1] / close.iloc[-60] - 1.0)

        raw_momentum = (
            0.5 * result['momentum_60d']
            + 0.35 * result['momentum_20d']
            + 0.15 * result['momentum_5d']
        )
        result['momentum_score'] = float(np.clip(raw_momentum / 0.20, -1.0, 1.0))

        # Volatility (ATR approximation)
        high, low = df['high'], df['low']
        tr = high - low
        atr = tr.rolling(14).mean().iloc[-1] if len(df) >= 14 else 0.0
        current_price = float(close.iloc[-1])
        result['atr_pct'] = float(atr / current_price * 100) if current_price > 0 else 0.0
        result['volatility_score'] = float(np.clip(result['atr_pct'] / 5.0, 0.0, 1.0))

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).ewm(alpha=1/14, min_periods=14).mean()
        loss = (-delta.where(delta < 0, 0.0)).ewm(alpha=1/14, min_periods=14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi_val = float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 50.0
        result['rsi_14'] = rsi_val
        if rsi_val < 30:
            result['rsi_signal'] = -1.0
        elif rsi_val > 70:
            result['rsi_signal'] = 1.0
        else:
            result['rsi_signal'] = (rsi_val - 50) / 20.0

        # Volume
        if 'volume' in df.columns:
            volume = df['volume']
            vol_sma = volume.rolling(20).mean()
            if not np.isnan(vol_sma.iloc[-1]) and vol_sma.iloc[-1] > 0:
                ratio = float(volume.iloc[-1] / vol_sma.iloc[-1])
                result['volume_sma_ratio'] = ratio
                result['volume_score'] = float(np.clip((ratio - 1.0) / 2.0, -1.0, 1.0))

        # Composite
        result['composite_score'] = float(np.clip(
            0.35 * result['momentum_score']
            + 0.20 * (1.0 - result['volatility_score'])
            + 0.25 * (-result['rsi_signal'])
            + 0.20 * result.get('volume_score', 0.0),
            -1.0, 1.0,
        ))

        return result

    def _detect_regime_builtin(self, factors: dict) -> str:
        """Built-in regime detection without shared module."""
        vol = factors.get('volatility_score', 0.0)
        mom = factors.get('momentum_score', 0.0)
        rsi = factors.get('rsi_14', 50.0)

        if vol > 0.7:
            return 'high_volatility'
        if vol < 0.15:
            return 'low_volatility'
        if mom > 0.3 and rsi > 55:
            return 'trending_up'
        if mom < -0.3 and rsi < 45:
            return 'trending_down'
        return 'ranging'

    def _grid_suitability_builtin(self, factors: dict) -> float:
        """Built-in grid suitability without shared module."""
        regime = self._detect_regime_builtin(factors)
        score = 0.5

        if regime == 'ranging':
            score += 0.3
        elif regime in ('trending_up', 'trending_down'):
            score -= 0.15
        elif regime == 'high_volatility':
            score -= 0.25
        elif regime == 'low_volatility':
            score -= 0.1

        vol = factors.get('volatility_score', 0.0)
        if 0.2 <= vol <= 0.6:
            score += 0.15

        rsi = factors.get('rsi_14', 50.0)
        rsi_dist = abs(rsi - 50)
        if rsi_dist < 10:
            score += 0.1
        elif rsi_dist > 20:
            score -= 0.1

        vol_ratio = factors.get('volume_sma_ratio', 1.0)
        if 0.8 <= vol_ratio <= 1.5:
            score += 0.05

        return float(np.clip(score, 0.0, 1.0))

    # ==================== Helpers ====================

    @staticmethod
    def _candles_to_dataframe(candles: np.ndarray) -> pd.DataFrame | None:
        """Convert Jesse-style candle array to DataFrame.

        Args:
            candles: Numpy array with columns [timestamp, open, high, low, close, volume].

        Returns:
            DataFrame with columns: open, high, low, close, volume.
        """
        if candles is None or len(candles) == 0:
            return None

        df = pd.DataFrame(
            candles[:, 1:6] if candles.shape[1] >= 6 else candles,
            columns=['open', 'high', 'low', 'close', 'volume'][:candles.shape[1] - 1] if candles.shape[1] >= 6 else ['open', 'high', 'low', 'close', 'volume'][:candles.shape[1]],
        )

        # Ensure we have at least OHLC
        if 'close' not in df.columns:
            return None

        return df

    @staticmethod
    def _default_factors() -> dict:
        """Return default (neutral) factor values."""
        return {
            'momentum_score': 0.0,
            'momentum_5d': 0.0,
            'momentum_20d': 0.0,
            'momentum_60d': 0.0,
            'volatility_score': 0.0,
            'atr_pct': 0.0,
            'rsi_14': 50.0,
            'rsi_signal': 0.0,
            'rsi_divergence': 0.0,
            'volume_score': 0.0,
            'volume_sma_ratio': 1.0,
            'composite_score': 0.0,
        }
