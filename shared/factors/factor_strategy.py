"""Multi-factor scoring strategy for grid optimization.

Uses factor analysis results to score trading conditions and
provide recommendations for grid parameter adjustment.
"""

from dataclasses import dataclass
from enum import Enum

import numpy as np
from loguru import logger

from shared.factors.factor_calculator import FactorCalculator, FactorResult


class MarketRegime(str, Enum):
    """Detected market regime based on factor analysis."""

    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"


class GridAction(str, Enum):
    """Recommended grid action based on factors."""

    WIDEN = "widen"      # Widen grid range
    NARROW = "narrow"    # Narrow grid range
    SHIFT_UP = "shift_up"    # Shift grid higher
    SHIFT_DOWN = "shift_down"  # Shift grid lower
    HOLD = "hold"        # Keep current grid
    PAUSE = "pause"      # Pause grid trading


@dataclass
class FactorScore:
    """Scored factor analysis with grid recommendations."""

    # Overall scores
    trade_score: float  # [-1, 1]: -1 = strong sell, 1 = strong buy
    grid_suitability: float  # [0, 1]: how suitable conditions are for grid trading
    regime: MarketRegime

    # Grid adjustment recommendations
    action: GridAction
    range_adjustment_pct: float  # How much to adjust range (%)
    level_adjustment: int  # How many levels to add/remove
    spacing_adjustment_pct: float  # How much to adjust spacing (%)

    # Risk
    risk_score: float  # [0, 1]: 0 = low risk, 1 = high risk

    reasoning: str


class FactorStrategy:
    """Multi-factor scoring strategy for grid trading optimization."""

    def __init__(
        self,
        calculator: FactorCalculator | None = None,
        grid_suitability_threshold: float = 0.4,
        volatility_ideal_range: tuple[float, float] = (0.2, 0.6),
    ):
        """Initialize factor strategy.

        Args:
            calculator: FactorCalculator instance (creates default if None).
            grid_suitability_threshold: Minimum suitability to recommend grid trading.
            volatility_ideal_range: Ideal volatility score range for grid trading.
        """
        self.calculator = calculator or FactorCalculator()
        self.grid_suitability_threshold = grid_suitability_threshold
        self.volatility_ideal_range = volatility_ideal_range

    def score(self, factors: FactorResult) -> FactorScore:
        """Score factor results and provide grid recommendations.

        Args:
            factors: Calculated factor results.

        Returns:
            FactorScore with recommendations.
        """
        regime = self._detect_regime(factors)
        grid_suitability = self._calc_grid_suitability(factors, regime)
        trade_score = factors.composite_score
        risk_score = self._calc_risk_score(factors)
        action, range_adj, level_adj, spacing_adj = self._recommend_grid_adjustments(
            factors, regime, grid_suitability
        )

        reasoning = self._build_reasoning(factors, regime, action, grid_suitability)

        result = FactorScore(
            trade_score=trade_score,
            grid_suitability=grid_suitability,
            regime=regime,
            action=action,
            range_adjustment_pct=range_adj,
            level_adjustment=level_adj,
            spacing_adjustment_pct=spacing_adj,
            risk_score=risk_score,
            reasoning=reasoning,
        )

        logger.info(
            f"Factor score: trade={trade_score:+.3f}, "
            f"suitability={grid_suitability:.3f}, regime={regime.value}, "
            f"action={action.value}, risk={risk_score:.3f}"
        )

        return result

    def analyze_and_score(
        self,
        df: "pd.DataFrame",
        symbol: str = "BTC/USDT",
    ) -> tuple[FactorResult, FactorScore]:
        """Calculate factors and score in one call.

        Args:
            df: OHLCV DataFrame.
            symbol: Trading symbol.

        Returns:
            Tuple of (FactorResult, FactorScore).
        """
        factors = self.calculator.calculate(df, symbol)
        score = self.score(factors)
        return factors, score

    def _detect_regime(self, factors: FactorResult) -> MarketRegime:
        """Detect current market regime from factors."""
        # High volatility takes precedence
        if factors.volatility_score > 0.7:
            return MarketRegime.HIGH_VOLATILITY
        if factors.volatility_score < 0.15:
            return MarketRegime.LOW_VOLATILITY

        # Trend detection
        if factors.momentum_score > 0.3 and factors.rsi_14 > 55:
            return MarketRegime.TRENDING_UP
        if factors.momentum_score < -0.3 and factors.rsi_14 < 45:
            return MarketRegime.TRENDING_DOWN

        return MarketRegime.RANGING

    def _calc_grid_suitability(
        self, factors: FactorResult, regime: MarketRegime
    ) -> float:
        """Calculate how suitable conditions are for grid trading.

        Grid trading works best in ranging, moderate-volatility markets.
        """
        score = 0.5  # Neutral baseline

        # Ranging markets are ideal for grid trading
        if regime == MarketRegime.RANGING:
            score += 0.3
        elif regime in (MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN):
            score -= 0.15  # Trends are less ideal but manageable
        elif regime == MarketRegime.HIGH_VOLATILITY:
            score -= 0.25  # Too risky
        elif regime == MarketRegime.LOW_VOLATILITY:
            score -= 0.1  # Too little profit opportunity

        # Volatility in ideal range boosts suitability
        v_low, v_high = self.volatility_ideal_range
        if v_low <= factors.volatility_score <= v_high:
            score += 0.15
        elif factors.volatility_score > v_high:
            score -= 0.1 * (factors.volatility_score - v_high) / (1.0 - v_high)

        # RSI near middle (40-60) is good for grid
        rsi_distance = abs(factors.rsi_14 - 50)
        if rsi_distance < 10:
            score += 0.1
        elif rsi_distance > 20:
            score -= 0.1

        # Volume confirmation
        if 0.8 <= factors.volume_sma_ratio <= 1.5:
            score += 0.05  # Normal volume is fine

        return float(np.clip(score, 0.0, 1.0))

    def _calc_risk_score(self, factors: FactorResult) -> float:
        """Calculate overall risk score [0, 1]."""
        risk = 0.3  # Baseline

        # High volatility = higher risk
        risk += factors.volatility_score * 0.3

        # Extreme RSI = higher risk
        rsi_extreme = max(0, (abs(factors.rsi_14 - 50) - 20) / 30)
        risk += rsi_extreme * 0.2

        # Strong momentum in one direction = risk for grid trading
        risk += abs(factors.momentum_score) * 0.15

        # Abnormal volume = caution
        if factors.volume_sma_ratio > 2.0:
            risk += 0.1

        return float(np.clip(risk, 0.0, 1.0))

    def _recommend_grid_adjustments(
        self,
        factors: FactorResult,
        regime: MarketRegime,
        suitability: float,
    ) -> tuple[GridAction, float, int, float]:
        """Recommend grid adjustments based on factors.

        Returns:
            Tuple of (action, range_adjustment_%, level_adjustment, spacing_adjustment_%)
        """
        if suitability < self.grid_suitability_threshold:
            return GridAction.PAUSE, 0.0, 0, 0.0

        # Default: no adjustment
        action = GridAction.HOLD
        range_adj = 0.0
        level_adj = 0
        spacing_adj = 0.0

        if regime == MarketRegime.HIGH_VOLATILITY:
            # Widen grid in high vol
            action = GridAction.WIDEN
            range_adj = min(factors.volatility_score * 30, 20.0)
            spacing_adj = range_adj * 0.5  # Wider spacing too
        elif regime == MarketRegime.LOW_VOLATILITY:
            # Narrow grid in low vol for tighter spreads
            action = GridAction.NARROW
            range_adj = -10.0
            level_adj = 2  # Add more levels for smaller moves
            spacing_adj = -5.0
        elif regime == MarketRegime.TRENDING_UP:
            action = GridAction.SHIFT_UP
            range_adj = factors.momentum_score * 10
        elif regime == MarketRegime.TRENDING_DOWN:
            action = GridAction.SHIFT_DOWN
            range_adj = factors.momentum_score * 10  # Negative momentum → negative shift
        elif regime == MarketRegime.RANGING:
            # Optimize for ranging: maybe tighten slightly
            if factors.volatility_score < 0.3:
                action = GridAction.NARROW
                range_adj = -5.0
                level_adj = 1

        return action, range_adj, level_adj, spacing_adj

    def _build_reasoning(
        self,
        factors: FactorResult,
        regime: MarketRegime,
        action: GridAction,
        suitability: float,
    ) -> str:
        """Build human-readable reasoning string."""
        parts = [f"Market regime: {regime.value}."]

        if factors.momentum_score > 0.2:
            parts.append(f"Positive momentum ({factors.momentum_20d:+.1%} 20d).")
        elif factors.momentum_score < -0.2:
            parts.append(f"Negative momentum ({factors.momentum_20d:+.1%} 20d).")
        else:
            parts.append("Neutral momentum.")

        parts.append(f"Volatility: {factors.atr_pct:.1f}% ATR.")

        if factors.rsi_14 < 30:
            parts.append(f"RSI oversold ({factors.rsi_14:.0f}).")
        elif factors.rsi_14 > 70:
            parts.append(f"RSI overbought ({factors.rsi_14:.0f}).")

        if factors.volume_sma_ratio > 1.5:
            parts.append(f"Above-average volume ({factors.volume_sma_ratio:.1f}x).")

        parts.append(f"Grid suitability: {suitability:.0%}. Action: {action.value}.")

        return " ".join(parts)

    def to_ai_context(self, factors: FactorResult, score: FactorScore) -> str:
        """Format factor analysis for AI agent consumption.

        Returns a string suitable for including in AI prompts.
        """
        return f"""## Factor Analysis
- Market Regime: {score.regime.value}
- Composite Score: {factors.composite_score:+.3f}
- Trade Score: {score.trade_score:+.3f}
- Grid Suitability: {score.grid_suitability:.0%}
- Risk Score: {score.risk_score:.0%}

### Momentum
- 60d Return: {factors.momentum_60d:+.2%}
- 20d Return: {factors.momentum_20d:+.2%}
- 5d Return: {factors.momentum_5d:+.2%}
- Score: {factors.momentum_score:+.3f}

### Volatility
- ATR%: {factors.atr_pct:.2f}%
- 20d StdDev: {factors.std_dev_20:.4f}
- Score: {factors.volatility_score:.3f}

### RSI
- RSI(14): {factors.rsi_14:.1f}
- Signal: {factors.rsi_signal:+.2f}
- Divergence: {factors.rsi_divergence:+.2f}

### Volume
- Vol Ratio: {factors.volume_sma_ratio:.2f}x avg
- OBV Trend: {factors.obv_trend:+.3f}
- Score: {factors.volume_score:+.3f}

### Grid Recommendation
- Action: {score.action.value}
- Range Adjustment: {score.range_adjustment_pct:+.1f}%
- Level Adjustment: {score.level_adjustment:+d}
- Spacing Adjustment: {score.spacing_adjustment_pct:+.1f}%
- Reasoning: {score.reasoning}
"""


# Global instance
factor_strategy = FactorStrategy()
