"""AI Trading Agent using LangChain + OpenRouter."""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from shared.config import settings
from shared.ai.prompts import (
    SYSTEM_PROMPT,
    MARKET_ANALYSIS_PROMPT,
    GRID_OPTIMIZATION_PROMPT,
    RISK_ASSESSMENT_PROMPT,
    SIGNAL_CONFIRMATION_PROMPT,
)


class Trend(str, Enum):
    """Market trend."""
    BULLISH = "bullish"
    BEARISH = "bearish"
    SIDEWAYS = "sideways"


class RiskLevel(str, Enum):
    """Risk level assessment."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SignalDecision(str, Enum):
    """AI decision on a signal."""
    CONFIRM = "confirm"
    REJECT = "reject"
    WAIT = "wait"


@dataclass
class MarketAnalysis:
    """Result of market analysis."""
    trend: Trend
    volatility_suitable: bool
    support_level: float
    resistance_level: float
    grid_recommended: bool
    suggested_lower: float | None
    suggested_upper: float | None
    risk_level: RiskLevel
    reasoning: str
    raw_response: str


@dataclass
class GridOptimization:
    """Optimized grid parameters."""
    lower_price: float
    upper_price: float
    num_levels: int
    confidence: int  # 0-100
    reasoning: str


@dataclass
class RiskAssessment:
    """Risk assessment result."""
    risk_score: int  # 1-10
    action: str  # HOLD/REDUCE/CLOSE/ADD
    stop_loss: float
    take_profit: float
    warning: str | None


class TradingAgent:
    """AI agent for trading decisions."""
    
    def __init__(self):
        """Initialize the trading agent with OpenRouter."""
        if not settings.openrouter_api_key:
            logger.warning("OpenRouter API key not set. AI features disabled.")
            self.llm = None
            return
        
        self.llm = ChatOpenAI(
            model=settings.openrouter_model,
            openai_api_key=settings.openrouter_api_key,
            openai_api_base=settings.openrouter_base_url,
            temperature=settings.ai_temperature,
            max_tokens=settings.ai_max_tokens,
            default_headers={
                "HTTP-Referer": "https://github.com/trading-bot",
                "X-Title": "Trading Bot",
                # Disable OpenRouter fallbacks via header
                # See: https://openrouter.ai/docs#provider-routing
                "X-Provider-Preferences": '{"allow_fallbacks":false}',
            },
        )
        logger.info(f"AI Agent initialized with model: {settings.openrouter_model}")
    
    @property
    def is_available(self) -> bool:
        """Check if AI is available."""
        return self.llm is not None
    
    async def _call_llm(self, prompt: str, system: str = SYSTEM_PROMPT) -> str:
        """Make an LLM call."""
        if not self.is_available:
            raise RuntimeError("AI not available. Set OPENROUTER_API_KEY in .env")
        
        messages = [
            SystemMessage(content=system),
            HumanMessage(content=prompt),
        ]
        
        try:
            response = await self.llm.ainvoke(messages)
            return response.content
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise
    
    async def analyze_market(
        self,
        symbol: str,
        current_price: float,
        high_24h: float,
        low_24h: float,
        change_24h: float,
        indicators: dict[str, Any],
        best_bid: float,
        best_ask: float,
        price_action: str,
        factor_context: str = "",
        news_context: str = "",
    ) -> MarketAnalysis:
        """Analyze market conditions for a symbol.

        Args:
            factor_context: Optional factor analysis context string.
            news_context: Optional news sentiment context string.
        """

        # Format indicators
        ind_str = "\n".join([f"- {k}: {v}" for k, v in indicators.items()])

        # Calculate spread
        spread = ((best_ask - best_bid) / best_bid) * 100

        prompt = MARKET_ANALYSIS_PROMPT.format(
            symbol=symbol,
            current_price=current_price,
            high_24h=high_24h,
            low_24h=low_24h,
            change_24h=change_24h,
            indicators=ind_str,
            best_bid=best_bid,
            best_ask=best_ask,
            spread=spread,
            price_action=price_action,
            factor_context=factor_context,
            news_context=news_context,
        )
        
        response = await self._call_llm(prompt)
        logger.debug(f"Market analysis response: {response}")
        
        # Parse response (simple heuristic parsing)
        analysis = self._parse_market_analysis(response, current_price, high_24h, low_24h)
        analysis.raw_response = response
        
        return analysis
    
    def _parse_market_analysis(
        self,
        response: str,
        current_price: float,
        high_24h: float,
        low_24h: float,
    ) -> MarketAnalysis:
        """Parse market analysis from LLM response."""
        response_lower = response.lower()
        
        # Detect trend
        if "bullish" in response_lower:
            trend = Trend.BULLISH
        elif "bearish" in response_lower:
            trend = Trend.BEARISH
        else:
            trend = Trend.SIDEWAYS
        
        # Detect risk level
        if "high risk" in response_lower or "risk: high" in response_lower:
            risk_level = RiskLevel.HIGH
        elif "low risk" in response_lower or "risk: low" in response_lower:
            risk_level = RiskLevel.LOW
        else:
            risk_level = RiskLevel.MEDIUM
        
        # Check if grid is recommended
        grid_recommended = (
            "activate grid" in response_lower or
            "grid trading: yes" in response_lower or
            "should we activate grid trading? yes" in response_lower or
            ("suitable" in response_lower and "grid" in response_lower)
        )
        
        # Volatility suitable for grid trading
        volatility_suitable = (
            "volatility" in response_lower and
            ("suitable" in response_lower or "good" in response_lower or "ideal" in response_lower)
        )
        
        # Extract price range if mentioned
        # Look for patterns like "$85,000 - $95,000" or "85000-95000"
        suggested_lower = None
        suggested_upper = None
        
        price_range_match = re.search(
            r'\$?([\d,]+(?:\.\d+)?)\s*[-–—to]\s*\$?([\d,]+(?:\.\d+)?)',
            response
        )
        if price_range_match:
            try:
                suggested_lower = float(price_range_match.group(1).replace(',', ''))
                suggested_upper = float(price_range_match.group(2).replace(',', ''))
            except ValueError:
                pass
        
        # Default support/resistance based on 24h range
        support_level = low_24h * 0.99
        resistance_level = high_24h * 1.01
        
        return MarketAnalysis(
            trend=trend,
            volatility_suitable=volatility_suitable,
            support_level=support_level,
            resistance_level=resistance_level,
            grid_recommended=grid_recommended,
            suggested_lower=suggested_lower,
            suggested_upper=suggested_upper,
            risk_level=risk_level,
            reasoning=response[:500],  # First 500 chars as reasoning
            raw_response="",
        )
    
    async def optimize_grid(
        self,
        symbol: str,
        current_price: float,
        atr: float,
        bb_lower: float,
        bb_upper: float,
        rsi: float,
        grid_lower: float,
        grid_upper: float,
        num_levels: int,
        investment_per_level: float,
        max_investment: float,
        risk_tolerance: str = "medium",
    ) -> GridOptimization:
        """Get AI-optimized grid parameters."""
        
        prompt = GRID_OPTIMIZATION_PROMPT.format(
            symbol=symbol,
            current_price=current_price,
            atr=atr,
            bb_lower=bb_lower,
            bb_upper=bb_upper,
            rsi=rsi,
            grid_lower=grid_lower,
            grid_upper=grid_upper,
            num_levels=num_levels,
            investment_per_level=investment_per_level,
            max_investment=max_investment,
            risk_tolerance=risk_tolerance,
        )
        
        response = await self._call_llm(prompt)
        logger.debug(f"Grid optimization response: {response}")
        
        return self._parse_grid_optimization(response, grid_lower, grid_upper, num_levels)
    
    def _parse_grid_optimization(
        self,
        response: str,
        default_lower: float,
        default_upper: float,
        default_levels: int,
    ) -> GridOptimization:
        """Parse grid optimization from LLM response."""
        
        lower = default_lower
        upper = default_upper
        levels = default_levels
        confidence = 50
        reasoning = ""
        
        for line in response.split('\n'):
            line = line.strip()
            if line.startswith('GRID_LOWER:'):
                try:
                    lower = float(line.split(':')[1].strip().replace('$', '').replace(',', ''))
                except ValueError:
                    pass
            elif line.startswith('GRID_UPPER:'):
                try:
                    upper = float(line.split(':')[1].strip().replace('$', '').replace(',', ''))
                except ValueError:
                    pass
            elif line.startswith('NUM_LEVELS:'):
                try:
                    levels = int(line.split(':')[1].strip())
                except ValueError:
                    pass
            elif line.startswith('CONFIDENCE:'):
                try:
                    confidence = int(line.split(':')[1].strip().replace('%', ''))
                except ValueError:
                    pass
            elif line.startswith('REASONING:'):
                reasoning = line.split(':', 1)[1].strip()
        
        return GridOptimization(
            lower_price=lower,
            upper_price=upper,
            num_levels=levels,
            confidence=confidence,
            reasoning=reasoning or response[:200],
        )
    
    async def assess_risk(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        current_price: float,
        position_size: float,
        base_currency: str,
        position_value: float,
        unrealized_pnl: float,
        pnl_percent: float,
        volatility: float,
        rsi: float,
        trend: str,
        total_balance: float,
        position_pct: float,
    ) -> RiskAssessment:
        """Assess risk for a position."""
        
        prompt = RISK_ASSESSMENT_PROMPT.format(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            current_price=current_price,
            position_size=position_size,
            base_currency=base_currency,
            position_value=position_value,
            unrealized_pnl=unrealized_pnl,
            pnl_percent=pnl_percent,
            volatility=volatility,
            rsi=rsi,
            trend=trend,
            total_balance=total_balance,
            position_pct=position_pct,
        )
        
        response = await self._call_llm(prompt)
        logger.debug(f"Risk assessment response: {response}")
        
        return self._parse_risk_assessment(response, current_price)
    
    def _parse_risk_assessment(
        self,
        response: str,
        current_price: float,
    ) -> RiskAssessment:
        """Parse risk assessment from LLM response."""
        
        risk_score = 5
        action = "HOLD"
        stop_loss = current_price * 0.95
        take_profit = current_price * 1.10
        warning = None
        
        for line in response.split('\n'):
            line = line.strip()
            if 'risk score' in line.lower():
                match = re.search(r'(\d+)', line)
                if match:
                    risk_score = min(10, max(1, int(match.group(1))))
            elif 'action' in line.lower():
                for act in ['CLOSE', 'REDUCE', 'ADD', 'HOLD']:
                    if act in line.upper():
                        action = act
                        break
            elif 'stop loss' in line.lower():
                match = re.search(r'\$?([\d,]+(?:\.\d+)?)', line)
                if match:
                    try:
                        stop_loss = float(match.group(1).replace(',', ''))
                    except ValueError:
                        pass
            elif 'take profit' in line.lower():
                match = re.search(r'\$?([\d,]+(?:\.\d+)?)', line)
                if match:
                    try:
                        take_profit = float(match.group(1).replace(',', ''))
                    except ValueError:
                        pass
            elif 'warning' in line.lower():
                warning = line.split(':', 1)[-1].strip()
        
        return RiskAssessment(
            risk_score=risk_score,
            action=action,
            stop_loss=stop_loss,
            take_profit=take_profit,
            warning=warning,
        )
    
    async def confirm_signal(
        self,
        signal_type: str,
        symbol: str,
        price: float,
        grid_level: int,
        reason: str,
        market_context: str,
        recent_trades: str,
    ) -> tuple[SignalDecision, str]:
        """Get AI confirmation for a trading signal."""
        
        prompt = SIGNAL_CONFIRMATION_PROMPT.format(
            signal_type=signal_type,
            symbol=symbol,
            price=price,
            grid_level=grid_level,
            reason=reason,
            market_context=market_context,
            recent_trades=recent_trades,
        )
        
        response = await self._call_llm(prompt)
        logger.debug(f"Signal confirmation response: {response}")
        
        response_upper = response.upper()
        reason_text = response.split(':', 1)[-1].strip() if ':' in response else response
        
        if 'CONFIRM' in response_upper:
            return SignalDecision.CONFIRM, reason_text
        elif 'REJECT' in response_upper:
            return SignalDecision.REJECT, reason_text
        else:
            return SignalDecision.WAIT, reason_text


# Global agent instance
trading_agent = TradingAgent()
