"""
Rule-based AI fallback — no LLM dependency.

Provides the same interface as AIMixin's AI methods using simple
indicator-based heuristics (RSI, ATR, SMA). Used when shared/ai is
unavailable or when AI calls fail.
"""

import logging

logger = logging.getLogger(__name__)


class AIFallback:
    """Rule-based fallback for AI analysis.

    Uses RSI, ATR, and SMA indicators to make trading decisions
    without any LLM dependency.
    """

    def analyze_market(
        self,
        candles: list[list[float]],
        indicators: dict[str, float],
    ) -> dict:
        """Analyze market using indicator heuristics.

        Args:
            candles: OHLCV candle data.
            indicators: Dict with rsi, atr, sma_fast, sma_slow, close.

        Returns:
            Dict matching AIMixin.ai_analyze_market() return format.
        """
        rsi = indicators.get('rsi', 50.0)
        atr = indicators.get('atr', 0.0)
        sma_fast = indicators.get('sma_fast', 0.0)
        sma_slow = indicators.get('sma_slow', 0.0)
        close = indicators.get('close', 0.0)

        # Trend from SMA crossover
        if sma_fast > 0 and sma_slow > 0:
            if sma_fast > sma_slow:
                trend = 'uptrend'
            elif sma_fast < sma_slow:
                trend = 'downtrend'
            else:
                trend = 'neutral'
        else:
            trend = 'neutral'

        # Confidence based on RSI position and trend strength
        confidence = 0.5
        if 30 <= rsi <= 70:
            confidence += 0.1  # RSI in normal range is good for grid
        if sma_fast > 0 and sma_slow > 0:
            trend_strength = abs(sma_fast - sma_slow) / sma_slow if sma_slow else 0
            if trend_strength < 0.02:
                confidence += 0.1  # Low trend strength = good for grid (range-bound)

        # Volatility check: ATR as % of price
        volatility_pct = (atr / close * 100) if close > 0 else 0.0
        if 0.5 <= volatility_pct <= 5.0:
            confidence += 0.1  # Moderate volatility is ideal for grid
            recommendation = 'TRADE'
        elif volatility_pct > 8.0:
            confidence = max(0.1, confidence - 0.3)
            recommendation = 'WAIT'
        else:
            recommendation = 'TRADE'

        # RSI extremes suggest caution
        if rsi > 80 or rsi < 20:
            recommendation = 'WAIT'
            confidence = max(0.1, confidence - 0.2)

        # Grid direction suggestion
        grid_params = {}
        if trend == 'uptrend':
            grid_params['direction'] = 'long_only'
        elif trend == 'downtrend':
            grid_params['direction'] = 'short_only'
        else:
            grid_params['direction'] = 'both'

        reasoning = (
            f"Fallback analysis: RSI={rsi:.1f}, trend={trend}, "
            f"volatility={volatility_pct:.2f}%"
        )

        return {
            'recommendation': recommendation,
            'confidence': min(1.0, confidence),
            'grid_params': grid_params,
            'trend': trend,
            'reasoning': reasoning,
        }

    def review_position(
        self,
        position_info: dict,
        market_data: dict,
    ) -> str:
        """Review open position using rule-based logic.

        Args:
            position_info: Dict with entry_price, current_price, side, qty, pnl_pct.
            market_data: Dict with rsi, atr, trend, volatility.

        Returns:
            One of: 'CONTINUE', 'PAUSE', 'ADJUST', 'STOP'.
        """
        pnl_pct = position_info.get('pnl_pct', 0.0)
        side = position_info.get('side', 'long')
        rsi = market_data.get('rsi', 50.0)
        trend = market_data.get('trend', 'neutral')

        # Large loss → STOP
        if pnl_pct < -5.0:
            return 'STOP'

        # Moderate loss + adverse trend → ADJUST
        if pnl_pct < -2.0:
            if (side == 'long' and trend == 'downtrend') or \
               (side == 'short' and trend == 'uptrend'):
                return 'ADJUST'

        # RSI extreme against position
        if side == 'long' and rsi > 85:
            return 'ADJUST'
        if side == 'short' and rsi < 15:
            return 'ADJUST'

        # Trend reversal warning
        if (side == 'long' and trend == 'downtrend' and pnl_pct < 0) or \
           (side == 'short' and trend == 'uptrend' and pnl_pct < 0):
            return 'PAUSE'

        return 'CONTINUE'

    def optimize_grid(
        self,
        current_grid: dict,
        market_analysis: dict,
    ) -> dict:
        """Optimize grid parameters using rule-based logic.

        Args:
            current_grid: Dict with center, spacing_pct, levels_count, direction.
            market_analysis: Dict from analyze_market().

        Returns:
            Dict with spacing_pct, levels_count, direction.
        """
        spacing = current_grid.get('spacing_pct', 1.5)
        levels = current_grid.get('levels_count', 10)
        direction = current_grid.get('direction', 'both')

        trend = market_analysis.get('trend', 'neutral')
        confidence = market_analysis.get('confidence', 0.5)

        # Adjust direction based on trend
        if trend == 'uptrend':
            direction = 'long_only'
        elif trend == 'downtrend':
            direction = 'short_only'
        else:
            direction = 'both'

        # Low confidence → widen spacing, fewer levels
        if confidence < 0.3:
            spacing = min(5.0, spacing * 1.5)
            levels = max(3, levels - 2)
        # High confidence → tighter spacing, more levels
        elif confidence > 0.7:
            spacing = max(0.3, spacing * 0.8)
            levels = min(30, levels + 2)

        return {
            'spacing_pct': round(spacing, 2),
            'levels_count': levels,
            'direction': direction,
        }
