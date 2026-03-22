"""
AI Mixin for AIGridStrategy — wraps shared/ai/agent.py.

Provides AI-powered market analysis, position review, and grid optimization.
Falls back to ai_fallback if shared/ai is unavailable or AI calls fail.
"""

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Try importing the shared AI agent; may fail without OpenRouter/deps
try:
    from shared.ai.agent import TradingAgent, MarketAnalysis, GridOptimization
    _HAS_SHARED_AI = True
except ImportError:
    _HAS_SHARED_AI = False

try:
    from .ai_fallback import AIFallback
except ImportError:
    from ai_fallback import AIFallback

# AI call timeout in seconds
AI_TIMEOUT = 60


class AIMixin:
    """Mixin providing AI capabilities to the Jesse strategy.

    Wraps shared/ai/agent.py with error handling and fallback.
    All methods return plain dicts so the strategy doesn't depend on
    shared.ai dataclasses.
    """

    def __init__(self):
        self._ai_agent: Optional[Any] = None
        self._fallback = AIFallback()

        if _HAS_SHARED_AI:
            try:
                self._ai_agent = TradingAgent()
                if not self._ai_agent.is_available:
                    logger.warning("TradingAgent created but LLM not available (no API key)")
                    self._ai_agent = None
            except Exception as e:
                logger.warning(f"Failed to initialize TradingAgent: {e}")
                self._ai_agent = None

    @property
    def ai_available(self) -> bool:
        """Check if AI agent is available."""
        return self._ai_agent is not None and self._ai_agent.is_available

    def ai_analyze_market(
        self,
        candles: list[list[float]],
        indicators: dict[str, float],
        symbol: str = "BTCUSDT",
    ) -> dict:
        """Analyze market conditions using AI or fallback.

        Args:
            candles: List of OHLCV candles [[ts, open, high, low, close, vol], ...].
            indicators: Dict of indicator values (rsi, atr, sma_fast, sma_slow, etc.).

        Returns:
            Dict with keys: recommendation (str), confidence (float 0-1),
            grid_params (dict), trend (str), reasoning (str).
        """
        if not self.ai_available:
            return self._fallback.analyze_market(candles, indicators)

        coro = self._ai_analyze_market_async(candles, indicators, symbol=symbol)
        try:
            return self._run_ai_with_timeout(coro)
        except Exception as e:
            coro.close()
            logger.warning(f"AI analyze_market failed: {e}. Using fallback.")
            return self._fallback.analyze_market(candles, indicators)

    def ai_review_position(
        self,
        position_info: dict,
        market_data: dict,
        symbol: str = "BTCUSDT",
        total_balance: float = 10000.0,
    ) -> str:
        """Review open position using AI or fallback.

        Args:
            position_info: Dict with entry_price, current_price, side, qty, pnl_pct.
            market_data: Dict with rsi, atr, trend, volatility.

        Returns:
            One of: 'CONTINUE', 'PAUSE', 'ADJUST', 'STOP'.
        """
        if not self.ai_available:
            return self._fallback.review_position(position_info, market_data)

        coro = self._ai_review_position_async(
            position_info, market_data, symbol=symbol, total_balance=total_balance,
        )
        try:
            return self._run_ai_with_timeout(coro)
        except Exception as e:
            coro.close()
            logger.warning(f"AI review_position failed: {e}. Using fallback.")
            return self._fallback.review_position(position_info, market_data)

    def ai_optimize_grid(
        self,
        current_grid: dict,
        market_analysis: dict,
        symbol: str = "BTCUSDT",
    ) -> dict:
        """Optimize grid parameters using AI or fallback.

        Args:
            current_grid: Dict with center, spacing_pct, levels_count, direction.
            market_analysis: Dict from ai_analyze_market().

        Returns:
            Dict with spacing_pct, levels_count, direction.
        """
        if not self.ai_available:
            return self._fallback.optimize_grid(current_grid, market_analysis)

        coro = self._ai_optimize_grid_async(current_grid, market_analysis, symbol=symbol)
        try:
            return self._run_ai_with_timeout(coro)
        except Exception as e:
            coro.close()
            logger.warning(f"AI optimize_grid failed: {e}. Using fallback.")
            return self._fallback.optimize_grid(current_grid, market_analysis)

    # ==================== Async AI calls ====================

    async def _ai_analyze_market_async(
        self,
        candles: list[list[float]],
        indicators: dict[str, float],
        symbol: str = "BTCUSDT",
    ) -> dict:
        """Call TradingAgent.analyze_market() and normalize response."""
        closes = [c[4] for c in candles] if candles else []
        current_price = closes[-1] if closes else 0.0
        high_24h = max(c[2] for c in candles[-24:]) if len(candles) >= 24 else (max(c[2] for c in candles) if candles else 0.0)
        low_24h = min(c[3] for c in candles[-24:]) if len(candles) >= 24 else (min(c[3] for c in candles) if candles else 0.0)
        change_24h = ((current_price - closes[-24]) / closes[-24] * 100) if len(closes) >= 24 else 0.0

        analysis: MarketAnalysis = await self._ai_agent.analyze_market(
            symbol=symbol,
            current_price=current_price,
            high_24h=high_24h,
            low_24h=low_24h,
            change_24h=change_24h,
            indicators=indicators,
            best_bid=current_price * 0.9999,
            best_ask=current_price * 1.0001,
            price_action=f"Last close: {current_price:.2f}",
        )

        trend_map = {'bullish': 'uptrend', 'bearish': 'downtrend', 'sideways': 'neutral'}
        trend = trend_map.get(analysis.trend.value, 'neutral')

        grid_params = {}
        if analysis.suggested_lower and analysis.suggested_upper:
            grid_params = {
                'lower': analysis.suggested_lower,
                'upper': analysis.suggested_upper,
            }

        confidence = 0.7 if analysis.grid_recommended else 0.3
        if analysis.risk_level.value == 'high':
            confidence *= 0.5
        elif analysis.risk_level.value == 'low':
            confidence = min(1.0, confidence * 1.2)

        recommendation = 'TRADE' if analysis.grid_recommended else 'WAIT'

        return {
            'recommendation': recommendation,
            'confidence': confidence,
            'grid_params': grid_params,
            'trend': trend,
            'reasoning': analysis.reasoning,
        }

    async def _ai_review_position_async(
        self,
        position_info: dict,
        market_data: dict,
        symbol: str = "BTCUSDT",
        total_balance: float = 10000.0,
    ) -> str:
        """Call TradingAgent.assess_risk() and map to review action."""
        current_price = position_info.get('current_price', 0.0)
        entry_price = position_info.get('entry_price', current_price)
        side = position_info.get('side', 'long')
        pnl_pct = position_info.get('pnl_pct', 0.0)
        qty = position_info.get('qty', 0.0)
        position_value = current_price * qty
        position_pct = (position_value / total_balance * 100) if total_balance > 0 else 0.0
        base_currency = symbol.replace("USDT", "") if symbol.endswith("USDT") else symbol[:3]

        assessment = await self._ai_agent.assess_risk(
            symbol=symbol,
            side=side.upper(),
            entry_price=entry_price,
            current_price=current_price,
            position_size=qty,
            base_currency=base_currency,
            position_value=position_value,
            unrealized_pnl=pnl_pct,
            pnl_percent=pnl_pct,
            volatility=market_data.get('volatility', 0.0),
            rsi=market_data.get('rsi', 50.0),
            trend=market_data.get('trend', 'sideways'),
            total_balance=total_balance,
            position_pct=position_pct,
        )

        action_map = {
            'HOLD': 'CONTINUE',
            'ADD': 'CONTINUE',
            'REDUCE': 'ADJUST',
            'CLOSE': 'STOP',
        }
        return action_map.get(assessment.action, 'CONTINUE')

    async def _ai_optimize_grid_async(
        self,
        current_grid: dict,
        market_analysis: dict,
        symbol: str = "BTCUSDT",
    ) -> dict:
        """Call TradingAgent.optimize_grid() and normalize response."""
        center = current_grid.get('center', 100000.0)
        spacing = current_grid.get('spacing_pct', 1.5)
        levels = current_grid.get('levels_count', 10)

        lower = center * (1 - spacing / 100 * levels)
        upper = center * (1 + spacing / 100 * levels)

        optimization: GridOptimization = await self._ai_agent.optimize_grid(
            symbol=symbol,
            current_price=center,
            atr=center * 0.01,
            bb_lower=lower,
            bb_upper=upper,
            rsi=50.0,
            grid_lower=lower,
            grid_upper=upper,
            num_levels=levels,
            investment_per_level=100.0,
            max_investment=1000.0,
        )

        return {
            'spacing_pct': spacing,
            'levels_count': optimization.num_levels,
            'direction': current_grid.get('direction', 'both'),
        }

    # ==================== Helpers ====================

    def _run_ai_with_timeout(self, coro, timeout: float = AI_TIMEOUT):
        """Run async AI coroutine synchronously with timeout."""
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop is not None and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, asyncio.wait_for(coro, timeout))
                    return future.result(timeout=timeout)
            else:
                return asyncio.run(asyncio.wait_for(coro, timeout))
        except asyncio.TimeoutError:
            raise TimeoutError(f"AI call timed out after {timeout}s")
