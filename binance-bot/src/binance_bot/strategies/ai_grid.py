"""AI-Enhanced Grid Trading Strategy.

Combines Grid Trading with AI-powered:
- Market analysis
- Grid parameter optimization
- Signal confirmation
- Risk assessment
"""

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
from shared.factors import factor_calculator, factor_strategy


@dataclass
class AIGridConfig(GridConfig):
    """AI Grid configuration with additional AI settings."""
    
    # AI settings
    ai_enabled: bool = True
    # Note: require_ai_approval removed - bot now uses state machine (WAITING/TRADING/PAUSED)
    ai_confirm_signals: bool = False     # Don't confirm every signal (too slow)
    ai_auto_optimize: bool = True        # Auto-optimize grid parameters on setup
    ai_periodic_review: bool = True      # Periodic AI review of position/market
    review_interval_minutes: int = 15    # How often to run AI review
    min_confidence: int = 60             # Minimum AI confidence to trade (0-100)
    risk_tolerance: str = "medium"       # low/medium/high


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
        self.last_factor_score = None  # FactorScore from factor analysis
        self.ai_enabled = config.ai_enabled and trading_agent.is_available
        
        if self.ai_enabled:
            logger.info("AI Grid Strategy initialized with AI enabled")
        else:
            logger.warning("AI Grid Strategy running without AI (fallback to basic grid)")
    
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

        Args:
            ohlcv_df: Optional OHLCV DataFrame for factor analysis.
            news_sentiment_context: Optional news sentiment context string.

        Returns:
            Tuple of (should_trade, reason)
        """
        if not self.ai_enabled:
            # Fallback to basic grid setup
            self.setup_grid(current_price)
            return True, "AI disabled, using default grid"

        # Factor analysis (if OHLCV data available)
        factor_context = ""
        if ohlcv_df is not None and len(ohlcv_df) >= 20:
            try:
                factors = factor_calculator.calculate(ohlcv_df, self.symbol)
                score = factor_strategy.score(factors)
                factor_context = factor_strategy.to_ai_context(factors, score)
                self.last_factor_score = score

                # If factors say pause, respect that
                if score.grid_suitability < 0.3:
                    logger.warning(
                        f"Factor analysis: low grid suitability ({score.grid_suitability:.0%})"
                    )
            except Exception as e:
                logger.warning(f"Factor analysis failed: {e}")

        # Get AI market analysis
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
        
        # Check if AI recommends grid trading
        if not self.last_analysis.grid_recommended:
            return False, f"AI does not recommend: {self.last_analysis.reasoning[:100]}"
        
        # Get AI-optimized grid parameters (only if AI approved)
        if self.ai_config.ai_auto_optimize:
            logger.info("🔧 Running AI grid optimization...")
            
            # Use AI-suggested range or calculate from indicators
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
            
            # Check confidence threshold
            if self.last_optimization.confidence < self.ai_config.min_confidence:
                return False, f"AI confidence too low: {self.last_optimization.confidence}% < {self.ai_config.min_confidence}%"
            
            # Apply optimized parameters
            self._apply_optimization(current_price)
        else:
            # Use default grid setup
            self.setup_grid(current_price)
        
        return True, f"Grid ready. AI confidence: {self.last_optimization.confidence if self.last_optimization else 'N/A'}%"
    
    def _apply_optimization(self, current_price: float):
        """Apply AI-optimized parameters to grid."""
        if not self.last_optimization:
            self.setup_grid(current_price)
            return
        
        opt = self.last_optimization
        
        # Calculate spacing from optimized range and levels
        price_range = opt.upper_price - opt.lower_price
        spacing_pct = (price_range / opt.num_levels) / current_price * 100
        
        # Update config
        self.config.grid_levels = opt.num_levels // 2  # Levels per side
        self.config.grid_spacing_pct = spacing_pct
        
        # Setup grid with center between optimized bounds
        center = (opt.lower_price + opt.upper_price) / 2
        self.setup_grid(center)
        
        logger.info(f"📐 AI-optimized grid applied:")
        logger.info(f"   Range: ${opt.lower_price:,.2f} - ${opt.upper_price:,.2f}")
        logger.info(f"   Levels: {opt.num_levels}")
        logger.info(f"   Spacing: {spacing_pct:.2f}%")
        logger.info(f"   Confidence: {opt.confidence}%")
    
    async def calculate_signals_with_ai(
        self,
        df: pd.DataFrame,
        current_price: float,
        market_context: str = "",
    ) -> list[Signal]:
        """Calculate signals with optional AI confirmation.
        
        Args:
            df: OHLCV DataFrame
            current_price: Current market price
            market_context: Additional context for AI
            
        Returns:
            List of confirmed signals
        """
        # Get raw signals from grid logic
        raw_signals = self.calculate_signals(df, current_price)
        
        if not raw_signals:
            return []
        
        if not self.ai_enabled or not self.ai_config.ai_confirm_signals:
            return raw_signals
        
        # AI confirmation for each signal
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
            else:  # WAIT
                logger.info(f"⏳ AI suggests waiting on {signal.type.value.upper()} @ ${signal.price:,.2f}: {reason}")
        
        return confirmed_signals
    
    def _get_level_number(self, price: float) -> int:
        """Get grid level number for a price."""
        for i, level in enumerate(self.levels):
            if abs(level.price - price) < 0.01:
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
        
        recent = self.paper_trades[-3:]  # Last 3 trades
        summaries = []
        for trade in recent:
            sig = trade["signal"]
            summaries.append(f"{sig.type.value.upper()} @ ${sig.price:,.2f}")
        
        return "; ".join(summaries)
    
    async def periodic_review(
        self,
        current_price: float,
        indicators: dict,
        position_value: float = 0,
        unrealized_pnl: float = 0,
    ) -> dict:
        """Periodic AI review of market and position.
        
        Call this every N minutes to let AI assess if grid should continue,
        be adjusted, or stopped.
        
        Returns:
            Dict with action and reasoning
        """
        if not self.ai_enabled:
            return {"action": "CONTINUE", "reason": "AI disabled"}
        
        logger.info("🔄 Running periodic AI review...")
        
        # Build context
        status = self.get_status()
        paper = status["paper_trading"]
        
        # Pre-calculate optional values to avoid f-string issues
        trend_str = self.last_analysis.trend.value if self.last_analysis else 'N/A'
        risk_str = self.last_analysis.risk_level.value if self.last_analysis else 'N/A'
        grid_range_str = (
            f"${self.last_optimization.lower_price:,.2f} - ${self.last_optimization.upper_price:,.2f}"
            if self.last_optimization else 'N/A'
        )
        
        context = f"""
Current Market:
- Price: ${current_price:,.2f}
- RSI: {indicators.get('RSI (14)', 'N/A')}
- ATR: ${indicators.get('ATR (14)', 0):,.2f}

Grid Status:
- Active buy levels: {status['active_buy_levels']}
- Active sell levels: {status['active_sell_levels']}
- Filled levels: {status['filled_levels']}
- Total trades: {paper['trades_count']}

Position:
- Holdings: {paper['holdings_btc']:.6f} BTC
- USDT Balance: ${paper['balance_usdt']:,.2f}
- Total Value: ${paper['total_value']:,.2f}
- Unrealized PnL: ${unrealized_pnl:,.2f}

Last AI Analysis:
- Trend: {trend_str}
- Risk: {risk_str}
- Grid range: {grid_range_str}
"""
        
        prompt = f"""Review this grid trading position and market state:

{context}

Provide a brief assessment:
1. Should we CONTINUE, PAUSE, or STOP the grid?
2. Should we ADJUST the grid range? If yes, suggest new bounds.
3. Any risk concerns?

Format your response as:
ACTION: CONTINUE/PAUSE/STOP/ADJUST
NEW_LOWER: <price or N/A>
NEW_UPPER: <price or N/A>
RISK: LOW/MEDIUM/HIGH
REASON: <one line explanation>
"""
        
        try:
            from shared.ai import trading_agent
            response = await trading_agent._call_llm(prompt)
            
            # Parse response
            result = {
                "action": "CONTINUE",
                "new_lower": None,
                "new_upper": None,
                "risk": "MEDIUM",
                "reason": response[:200],
                "raw_response": response,
            }
            
            for line in response.split('\n'):
                line = line.strip()
                if line.startswith('ACTION:'):
                    action = line.split(':')[1].strip().upper()
                    if action in ['CONTINUE', 'PAUSE', 'STOP', 'ADJUST']:
                        result["action"] = action
                elif line.startswith('NEW_LOWER:'):
                    val = line.split(':')[1].strip().replace('$', '').replace(',', '')
                    if val != 'N/A':
                        try:
                            result["new_lower"] = float(val)
                        except ValueError:
                            pass
                elif line.startswith('NEW_UPPER:'):
                    val = line.split(':')[1].strip().replace('$', '').replace(',', '')
                    if val != 'N/A':
                        try:
                            result["new_upper"] = float(val)
                        except ValueError:
                            pass
                elif line.startswith('RISK:'):
                    risk = line.split(':')[1].strip().upper()
                    if risk in ['LOW', 'MEDIUM', 'HIGH']:
                        result["risk"] = risk
                elif line.startswith('REASON:'):
                    result["reason"] = line.split(':', 1)[1].strip()
            
            logger.info(f"📋 AI Review: {result['action']} (Risk: {result['risk']})")
            logger.info(f"   Reason: {result['reason']}")
            
            # Apply adjustments if needed
            if result["action"] == "ADJUST" and result["new_lower"] and result["new_upper"]:
                logger.info(f"🔧 Adjusting grid to ${result['new_lower']:,.2f} - ${result['new_upper']:,.2f}")
                
                # Create optimization object if it doesn't exist
                if self.last_optimization is None:
                    from shared.ai.agent import GridOptimization
                    self.last_optimization = GridOptimization(
                        lower_price=result["new_lower"],
                        upper_price=result["new_upper"],
                        num_levels=self.config.grid_levels * 2,
                        confidence=70,
                        reasoning="AI periodic review adjustment",
                    )
                else:
                    self.last_optimization.lower_price = result["new_lower"]
                    self.last_optimization.upper_price = result["new_upper"]
                
                self._apply_optimization(current_price)
            
            return result
            
        except Exception as e:
            logger.error(f"AI review failed: {e}")
            return {"action": "CONTINUE", "reason": f"AI error: {e}"}
    
    def get_status(self) -> dict:
        """Get current strategy status including AI state."""
        status = super().get_status()
        
        status["ai"] = {
            "enabled": self.ai_enabled,
            "confirm_signals": self.ai_config.ai_confirm_signals,
            "auto_optimize": self.ai_config.ai_auto_optimize,
            "min_confidence": self.ai_config.min_confidence,
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
