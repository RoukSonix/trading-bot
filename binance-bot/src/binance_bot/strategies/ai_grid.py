"""AI-Enhanced Grid Trading Strategy.

Combines Grid Trading with AI-powered:
- Market analysis
- Grid parameter optimization
- Signal confirmation
- Risk assessment
"""

import re
from dataclasses import dataclass
from typing import Optional
import pandas as pd
from loguru import logger

from binance_bot.strategies.grid import GridStrategy, GridConfig
from binance_bot.strategies.base import Signal, SignalType
from shared.ai import (
    trading_agent,
    MarketAnalysis,
    GridOptimization,
    SignalDecision,
)
from shared.ai.parsing import parse_llm_json
from shared.factors import factor_calculator, factor_strategy
from shared.constants import (
    MIN_GRID_SUITABILITY,
    DEFAULT_ADJUSTMENT_CONFIDENCE,
    PRICE_MATCH_TOLERANCE,
)


@dataclass
class AIGridConfig(GridConfig):
    """AI Grid configuration with additional AI settings."""

    # AI settings
    ai_enabled: bool = True
    ai_confirm_signals: bool = False
    ai_auto_optimize: bool = True
    ai_periodic_review: bool = True
    review_interval_minutes: int = 15
    min_confidence: int = 60
    risk_tolerance: str = "medium"
    ai_short_enabled: bool = True


class AIGridStrategy(GridStrategy):
    """AI-Enhanced Grid Trading Strategy."""

    name = "AIGridStrategy"

    def __init__(
        self,
        symbol: str = "BTC/USDT",
        config: Optional[AIGridConfig] = None,
    ):
        """Initialize AI Grid strategy."""
        config = config or AIGridConfig()
        super().__init__(symbol, config)
        self.ai_config = config

        # AI state
        self.last_analysis: Optional[MarketAnalysis] = None
        self.last_optimization: Optional[GridOptimization] = None
        self.last_factor_score = None
        self.ai_enabled = config.ai_enabled and trading_agent.is_available

        if self.ai_enabled:
            logger.info("AI Grid Strategy initialized with AI enabled")
        else:
            logger.warning("AI Grid Strategy running without AI (fallback to basic grid)")

    # ── analyze_and_setup ───────────────────────────────────────────────────

    async def analyze_and_setup(
        self,
        current_price: float,
        high_24h: float,
        low_24h: float,
        change_24h: float,
        indicators: dict,
        best_bid: float,
        best_ask: float,
        price_action: str = "",
        ohlcv_df: Optional[pd.DataFrame] = None,
        news_sentiment_context: str = "",
    ) -> tuple[bool, str]:
        """Analyze market and setup grid with AI assistance.

        Returns:
            Tuple of (should_trade, reason)
        """
        if not self.ai_enabled:
            self.setup_grid(current_price)
            return True, "AI disabled, using default grid"

        factor_context = self._run_factor_analysis(ohlcv_df)

        should_trade, reason = await self._fetch_ai_analysis(
            current_price, high_24h, low_24h, change_24h,
            indicators, best_bid, best_ask, price_action,
            factor_context, news_sentiment_context,
        )
        if not should_trade:
            return False, reason

        return await self._apply_ai_config(current_price, indicators)

    def _run_factor_analysis(self, ohlcv_df: Optional[pd.DataFrame]) -> str:
        """Run factor analysis and return context string."""
        if ohlcv_df is None or len(ohlcv_df) < 20:
            return ""

        try:
            factors = factor_calculator.calculate(ohlcv_df, self.symbol)
            score = factor_strategy.score(factors)
            self.last_factor_score = score

            if score.grid_suitability < MIN_GRID_SUITABILITY:
                logger.warning(
                    f"Factor analysis: low grid suitability ({score.grid_suitability:.0%})"
                )

            return factor_strategy.to_ai_context(factors, score)
        except Exception as e:
            logger.warning(f"Factor analysis failed: {e}")
            return ""

    async def _fetch_ai_analysis(
        self, current_price: float, high_24h: float, low_24h: float,
        change_24h: float, indicators: dict, best_bid: float,
        best_ask: float, price_action: str,
        factor_context: str, news_sentiment_context: str,
    ) -> tuple[bool, str]:
        """Run AI market analysis. Returns (should_trade, reason)."""
        logger.info("🤖 Running AI market analysis...")

        self.last_analysis = await trading_agent.analyze_market(
            symbol=self.symbol,
            current_price=current_price,
            high_24h=high_24h,
            low_24h=low_24h,
            change_24h=change_24h,
            indicators=indicators,
            best_bid=best_bid,
            best_ask=best_ask,
            price_action=price_action,
            factor_context=factor_context,
            news_context=news_sentiment_context,
        )

        if not self.last_analysis.grid_recommended:
            return False, f"AI does not recommend: {self.last_analysis.reasoning[:100]}"
        return True, ""

    async def _apply_ai_config(
        self, current_price: float, indicators: dict,
    ) -> tuple[bool, str]:
        """Apply AI optimization or default grid. Returns (should_trade, reason)."""
        if not self.ai_config.ai_auto_optimize:
            self.setup_grid(current_price)
            return True, "Grid ready. AI confidence: N/A"

        logger.info("🔧 Running AI grid optimization...")

        grid_lower = self.last_analysis.suggested_lower or (current_price * 0.95)
        grid_upper = self.last_analysis.suggested_upper or (current_price * 1.05)

        self.last_optimization = await trading_agent.optimize_grid(
            symbol=self.symbol,
            current_price=current_price,
            atr=indicators.get("ATR (14)", current_price * 0.01),
            bb_lower=indicators.get("BB Lower", current_price * 0.97),
            bb_upper=indicators.get("BB Upper", current_price * 1.03),
            rsi=indicators.get("RSI (14)", 50),
            grid_lower=grid_lower,
            grid_upper=grid_upper,
            num_levels=self.config.grid_levels,
            investment_per_level=self.config.amount_per_level * current_price,
            max_investment=self.config.max_position * current_price,
            risk_tolerance=self.ai_config.risk_tolerance,
        )

        if self.last_optimization.confidence < self.ai_config.min_confidence:
            return False, f"AI confidence too low: {self.last_optimization.confidence}% < {self.ai_config.min_confidence}%"

        self._apply_optimization(current_price)
        return True, f"Grid ready. AI confidence: {self.last_optimization.confidence}%"

    def _apply_optimization(self, current_price: float):
        """Apply AI-optimized parameters to grid."""
        if not self.last_optimization:
            self.setup_grid(current_price)
            return

        opt = self.last_optimization

        price_range = opt.upper_price - opt.lower_price
        if opt.num_levels < 2 or current_price <= 0:
            logger.warning(f"AI returned num_levels={opt.num_levels}, current_price={current_price}, using default grid")
            self.setup_grid(current_price)
            return
        spacing_pct = (price_range / opt.num_levels) / current_price * 100

        self.config.grid_levels = max(1, opt.num_levels // 2)
        self.config.grid_spacing_pct = spacing_pct

        center = (opt.lower_price + opt.upper_price) / 2
        self.setup_grid(center)

        logger.info(f"📐 AI-optimized grid applied:")
        logger.info(f"   Range: ${opt.lower_price:,.2f} - ${opt.upper_price:,.2f}")
        logger.info(f"   Levels: {opt.num_levels}")
        logger.info(f"   Spacing: {spacing_pct:.2f}%")
        logger.info(f"   Confidence: {opt.confidence}%")

    # ── Signal confirmation ─────────────────────────────────────────────────

    async def calculate_signals_with_ai(
        self, df: pd.DataFrame, current_price: float, market_context: str = "",
    ) -> list[Signal]:
        """Calculate signals with optional AI confirmation."""
        raw_signals = self.calculate_signals(df, current_price)

        if not raw_signals:
            return []

        if not self.ai_enabled or not self.ai_config.ai_confirm_signals:
            return raw_signals

        confirmed_signals = []

        for signal in raw_signals:
            decision, reason = await trading_agent.confirm_signal(
                signal_type=signal.type.value.upper(),
                symbol=self.symbol,
                price=signal.price,
                grid_level=self._get_level_number(signal.price),
                reason=signal.reason,
                market_context=market_context or self._get_market_context(),
                recent_trades=self._get_recent_trades_summary(),
            )

            if decision == SignalDecision.CONFIRM:
                logger.info(f"✅ AI confirmed {signal.type.value.upper()} @ ${signal.price:,.2f}: {reason}")
                confirmed_signals.append(signal)
            elif decision == SignalDecision.REJECT:
                logger.warning(f"❌ AI rejected {signal.type.value.upper()} @ ${signal.price:,.2f}: {reason}")
            else:
                logger.info(f"⏳ AI suggests waiting on {signal.type.value.upper()} @ ${signal.price:,.2f}: {reason}")

        return confirmed_signals

    def _get_level_number(self, price: float) -> int:
        """Get grid level number for a price."""
        for i, level in enumerate(self.levels):
            tolerance = max(level.price * PRICE_MATCH_TOLERANCE, 0.001)
            if abs(level.price - price) < tolerance:
                return i + 1
        return 0

    def _get_market_context(self) -> str:
        """Get current market context for AI."""
        if self.last_analysis:
            return (
                f"Trend: {self.last_analysis.trend.value}, "
                f"Risk: {self.last_analysis.risk_level.value}, "
                f"Volatility suitable: {self.last_analysis.volatility_suitable}"
            )
        return "No recent analysis"

    def _get_recent_trades_summary(self) -> str:
        """Get summary of recent paper trades."""
        if not self.paper_trades:
            return "No recent trades"
        recent = self.paper_trades[-3:]
        summaries = [f"{t['signal'].type.value.upper()} @ ${t['signal'].price:,.2f}" for t in recent]
        return "; ".join(summaries)

    # ── Periodic review ─────────────────────────────────────────────────────

    async def periodic_review(
        self,
        current_price: float,
        indicators: dict,
        position_value: float = 0,
        unrealized_pnl: float = 0,
    ) -> dict:
        """Periodic AI review of market and position."""
        if not self.ai_enabled:
            return {"action": "CONTINUE", "reason": "AI disabled"}

        logger.info("🔄 Running periodic AI review...")

        prompt = self._build_review_prompt(current_price, indicators, position_value, unrealized_pnl)

        try:
            result = await self._execute_review(prompt)
            logger.info(f"📋 AI Review: {result['action']} (Risk: {result['risk']})")
            logger.info(f"   Reason: {result['reason']}")

            self._apply_review(result, current_price)
            return result
        except Exception as e:
            logger.error(f"AI review failed: {e}")
            return {"action": "CONTINUE", "reason": f"AI error: {e}"}

    def _build_review_prompt(
        self, current_price: float, indicators: dict,
        position_value: float, unrealized_pnl: float,
    ) -> str:
        """Build context and prompt for periodic review."""
        status = self.get_status()
        paper = status["paper_trading"]

        trend_str = self.last_analysis.trend.value if self.last_analysis else 'N/A'
        risk_str = self.last_analysis.risk_level.value if self.last_analysis else 'N/A'
        grid_range_str = (
            f"${self.last_optimization.lower_price:,.2f} - ${self.last_optimization.upper_price:,.2f}"
            if self.last_optimization else 'N/A'
        )

        long_hold = paper.get('long_holdings', paper.get('holdings_btc', 0))
        short_hold = paper.get('short_holdings', 0)
        net_exposure = paper.get('net_exposure', long_hold - short_hold)

        context = f"""
Current Market:
- Price: ${current_price:,.2f}
- RSI: {indicators.get('RSI (14)', 'N/A')}
- ATR: ${indicators.get('ATR (14)', 0):,.2f}

Grid Status:
- Active buy levels: {status['active_buy_levels']}
- Active sell levels: {status['active_sell_levels']}
- Filled levels: {status['filled_levels']}
- Long levels: {status.get('long_levels', 'N/A')}
- Short levels: {status.get('short_levels', 'N/A')}
- Total trades: {paper['trades_count']}

Position:
- Long Holdings: {long_hold:.6f} BTC
- Short Holdings: {short_hold:.6f} BTC
- Net Exposure: {net_exposure:.6f} BTC
- USDT Balance: ${paper['balance_usdt']:,.2f}
- Total Value: ${paper['total_value']:,.2f}
- Unrealized PnL: ${unrealized_pnl:,.2f}

Last AI Analysis:
- Trend: {trend_str}
- Risk: {risk_str}
- Grid range: {grid_range_str}
"""

        return f"""Review this grid trading position and market state:

{context}

Provide a brief assessment:
1. Should we CONTINUE, PAUSE, or STOP the grid?
2. Should we ADJUST the grid range? If yes, suggest new bounds.
3. Should we GO_SHORT (increase short exposure) or REDUCE_LONG?
4. Any risk concerns?

Respond with ONLY a JSON object (no markdown, no extra text):
{{"action": "CONTINUE|PAUSE|STOP|ADJUST|GO_SHORT|REDUCE_LONG", "new_lower": null, "new_upper": null, "risk": "LOW|MEDIUM|HIGH", "reason": "one line explanation"}}
"""

    async def _execute_review(self, prompt: str) -> dict:
        """Execute LLM review call and parse response."""
        from shared.ai import trading_agent
        response = await trading_agent._call_llm(prompt)
        return self._parse_review_response(response)

    def _apply_review(self, result: dict, current_price: float):
        """Apply grid adjustments from review result."""
        if result["action"] != "ADJUST" or not result["new_lower"] or not result["new_upper"]:
            return

        logger.info(f"🔧 Adjusting grid to ${result['new_lower']:,.2f} - ${result['new_upper']:,.2f}")

        if self.last_optimization is None:
            from shared.ai.agent import GridOptimization
            self.last_optimization = GridOptimization(
                lower_price=result["new_lower"],
                upper_price=result["new_upper"],
                num_levels=self.config.grid_levels * 2,
                confidence=DEFAULT_ADJUSTMENT_CONFIDENCE,
                reasoning="AI periodic review adjustment",
            )
        else:
            self.last_optimization.lower_price = result["new_lower"]
            self.last_optimization.upper_price = result["new_upper"]

        self._apply_optimization(current_price)

    @staticmethod
    def _parse_review_response(response: str) -> dict:
        """Parse AI review response. Try JSON first, fall back to line parsing."""
        result = {
            "action": "CONTINUE",
            "new_lower": None,
            "new_upper": None,
            "risk": "MEDIUM",
            "reason": response[:200],
            "raw_response": response,
        }

        valid_actions = {"CONTINUE", "PAUSE", "STOP", "ADJUST", "GO_SHORT", "REDUCE_LONG"}
        valid_risks = {"LOW", "MEDIUM", "HIGH"}

        # Try JSON parsing first
        cleaned = re.sub(r'```(?:json)?\s*', '', response)
        cleaned = re.sub(r'```', '', cleaned)
        parsed = parse_llm_json(cleaned)
        if parsed:
            action = str(parsed.get("action", "")).upper()
            if action in valid_actions:
                result["action"] = action
            risk = str(parsed.get("risk", "")).upper()
            if risk in valid_risks:
                result["risk"] = risk
            if parsed.get("reason"):
                result["reason"] = str(parsed["reason"])
            for key in ("new_lower", "new_upper"):
                val = parsed.get(key)
                if val is not None and val != "N/A":
                    try:
                        result[key] = float(str(val).replace("$", "").replace(",", ""))
                    except (ValueError, TypeError):
                        pass
            return result

        # Fallback: line-by-line parsing
        for line in response.split("\n"):
            line = line.strip()
            if line.startswith("ACTION:"):
                action = line.split(":", 1)[1].strip().upper()
                if action in valid_actions:
                    result["action"] = action
            elif line.startswith("NEW_LOWER:"):
                val = line.split(":", 1)[1].strip().replace("$", "").replace(",", "")
                if val != "N/A":
                    try:
                        result["new_lower"] = float(val)
                    except ValueError:
                        pass
            elif line.startswith("NEW_UPPER:"):
                val = line.split(":", 1)[1].strip().replace("$", "").replace(",", "")
                if val != "N/A":
                    try:
                        result["new_upper"] = float(val)
                    except ValueError:
                        pass
            elif line.startswith("RISK:"):
                risk = line.split(":", 1)[1].strip().upper()
                if risk in valid_risks:
                    result["risk"] = risk
            elif line.startswith("REASON:"):
                result["reason"] = line.split(":", 1)[1].strip()

        return result

    # ── Status ──────────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        """Get current strategy status including AI state."""
        status = super().get_status()

        status["ai"] = {
            "enabled": self.ai_enabled,
            "confirm_signals": self.ai_config.ai_confirm_signals,
            "auto_optimize": self.ai_config.ai_auto_optimize,
            "min_confidence": self.ai_config.min_confidence,
            "short_enabled": self.ai_config.ai_short_enabled,
            "last_analysis": {
                "trend": self.last_analysis.trend.value if self.last_analysis else None,
                "risk_level": self.last_analysis.risk_level.value if self.last_analysis else None,
                "grid_recommended": self.last_analysis.grid_recommended if self.last_analysis else None,
            } if self.last_analysis else None,
            "last_optimization": {
                "confidence": self.last_optimization.confidence if self.last_optimization else None,
                "lower": self.last_optimization.lower_price if self.last_optimization else None,
                "upper": self.last_optimization.upper_price if self.last_optimization else None,
                "levels": self.last_optimization.num_levels if self.last_optimization else None,
            } if self.last_optimization else None,
            "last_factor_score": {
                "regime": self.last_factor_score.regime.value,
                "trade_score": self.last_factor_score.trade_score,
                "grid_suitability": self.last_factor_score.grid_suitability,
                "risk_score": self.last_factor_score.risk_score,
                "action": self.last_factor_score.action.value,
            } if self.last_factor_score else None,
        }

        return status
