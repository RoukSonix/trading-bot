"""AI Trading Agent using LangChain + OpenRouter."""

import asyncio
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

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
from shared.ai.parsing import parse_llm_json, parse_price_value, extract_field
from shared.constants import LLM_TIMEOUT_SEC


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
            timeout=LLM_TIMEOUT_SEC,
            default_headers={
                "HTTP-Referer": "https://github.com/trading-bot",
                "X-Title": "Trading Bot",
                "X-Provider-Preferences": '{"allow_fallbacks":false}',
            },
        )
        logger.info(f"AI Agent initialized with model: {settings.openrouter_model}")

    @property
    def is_available(self) -> bool:
        """Check if AI is available."""
        return self.llm is not None

    async def _call_llm(self, prompt: str, system: str = SYSTEM_PROMPT) -> str:
        """Make an LLM call with timeout protection."""
        if not self.is_available:
            raise RuntimeError("AI not available. Set OPENROUTER_API_KEY in .env")

        messages = [
            SystemMessage(content=system),
            HumanMessage(content=prompt),
        ]

        try:
            response = await asyncio.wait_for(
                self.llm.ainvoke(messages),
                timeout=LLM_TIMEOUT_SEC,
            )
            return response.content
        except asyncio.TimeoutError:
            logger.error(f"LLM call timed out after {LLM_TIMEOUT_SEC}s")
            raise
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise

    # ── Market Analysis ─────────────────────────────────────────────────────

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
        """Analyze market conditions for a symbol."""
        ind_str = "\n".join([f"- {k}: {v}" for k, v in indicators.items()])
        spread = ((best_ask - best_bid) / best_bid) * 100 if best_bid > 0 else 0.0

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

        analysis = self._parse_market_analysis(response, current_price, high_24h, low_24h)
        analysis.raw_response = response
        return analysis

    _NEGATION_RE = re.compile(
        r"(?:not|no|don't|doesn't|isn't|aren't|neither|without|hardly|barely)"
        r"(?:\s+\S+){0,4}\s+",
        re.IGNORECASE,
    )

    def _keyword_negated(self, keyword: str, text: str) -> bool:
        """Check if a keyword is preceded by a negation word (within 5 words)."""
        return bool(re.search(
            self._NEGATION_RE.pattern + re.escape(keyword),
            text,
            re.IGNORECASE,
        ))

    def _parse_market_analysis(
        self, response: str, current_price: float,
        high_24h: float, low_24h: float,
    ) -> MarketAnalysis:
        """Parse market analysis — JSON or keyword fallback."""
        support_level = low_24h * 0.99
        resistance_level = high_24h * 1.01

        parsed = parse_llm_json(response)
        if parsed:
            return self._parse_market_analysis_json(parsed, support_level, resistance_level, response)
        return self._parse_market_analysis_keywords(response, support_level, resistance_level)

    def _parse_market_analysis_json(
        self, parsed: dict, support_level: float,
        resistance_level: float, raw_response: str,
    ) -> MarketAnalysis:
        """Build MarketAnalysis from parsed JSON dict."""
        trend_str = str(parsed.get("trend", "")).lower()
        trend = {"bullish": Trend.BULLISH, "bearish": Trend.BEARISH}.get(trend_str, Trend.SIDEWAYS)

        risk_str = str(parsed.get("risk", parsed.get("risk_level", ""))).lower()
        risk_level = {"high": RiskLevel.HIGH, "low": RiskLevel.LOW}.get(risk_str, RiskLevel.MEDIUM)

        return MarketAnalysis(
            trend=trend,
            volatility_suitable=bool(parsed.get("volatility_suitable", False)),
            support_level=support_level,
            resistance_level=resistance_level,
            grid_recommended=bool(parsed.get("grid_recommended", parsed.get("grid_trading", False))),
            suggested_lower=extract_field(parsed, ("suggested_lower", "lower", "grid_lower"), converter=parse_price_value),
            suggested_upper=extract_field(parsed, ("suggested_upper", "upper", "grid_upper"), converter=parse_price_value),
            risk_level=risk_level,
            reasoning=str(parsed.get("reasoning", parsed.get("reason", raw_response[:500]))),
            raw_response="",
        )

    def _parse_market_analysis_keywords(
        self, response: str, support_level: float, resistance_level: float,
    ) -> MarketAnalysis:
        """Build MarketAnalysis via negation-aware keyword matching (fallback)."""
        response_lower = response.lower()

        trend = self._detect_trend_keywords(response_lower)
        risk_level = self._detect_risk_keywords(response_lower)
        grid_recommended = self._detect_grid_recommended(response_lower)

        vol_suitable = (
            "volatility" in response_lower
            and ("suitable" in response_lower or "good" in response_lower or "ideal" in response_lower)
        )
        volatility_suitable = vol_suitable and not self._keyword_negated("suitable", response_lower)

        suggested_lower, suggested_upper = self._extract_price_range(response)

        return MarketAnalysis(
            trend=trend,
            volatility_suitable=volatility_suitable,
            support_level=support_level,
            resistance_level=resistance_level,
            grid_recommended=grid_recommended,
            suggested_lower=suggested_lower,
            suggested_upper=suggested_upper,
            risk_level=risk_level,
            reasoning=response[:500],
            raw_response="",
        )

    def _detect_trend_keywords(self, response_lower: str) -> Trend:
        bullish = bool(re.search(r'\bbullish\b', response_lower))
        bearish = bool(re.search(r'\bbearish\b', response_lower))
        if bullish and not self._keyword_negated("bullish", response_lower):
            return Trend.BULLISH
        if bearish and not self._keyword_negated("bearish", response_lower):
            return Trend.BEARISH
        return Trend.SIDEWAYS

    def _detect_risk_keywords(self, response_lower: str) -> RiskLevel:
        high = bool(re.search(r'\bhigh risk\b', response_lower) or re.search(r'\brisk:\s*high\b', response_lower))
        low = bool(re.search(r'\blow risk\b', response_lower) or re.search(r'\brisk:\s*low\b', response_lower))
        if high and not self._keyword_negated("high", response_lower):
            return RiskLevel.HIGH
        if low and not self._keyword_negated("low", response_lower):
            return RiskLevel.LOW
        return RiskLevel.MEDIUM

    def _detect_grid_recommended(self, response_lower: str) -> bool:
        grid_phrases = ["activate grid", "grid trading: yes", "should we activate grid trading? yes"]
        if any(phrase in response_lower for phrase in grid_phrases):
            return True
        suitable_grid = "suitable" in response_lower and "grid" in response_lower
        return suitable_grid and not self._keyword_negated("suitable", response_lower)

    @staticmethod
    def _extract_price_range(response: str) -> tuple[float | None, float | None]:
        match = re.search(r'\$?([\d,]+(?:\.\d+)?)\s*[-\u2013\u2014to]\s*\$?([\d,]+(?:\.\d+)?)', response)
        if not match:
            return None, None
        try:
            return float(match.group(1).replace(',', '')), float(match.group(2).replace(',', ''))
        except ValueError:
            return None, None

    # ── Grid Optimization ───────────────────────────────────────────────────

    async def optimize_grid(
        self, symbol: str, current_price: float, atr: float,
        bb_lower: float, bb_upper: float, rsi: float,
        grid_lower: float, grid_upper: float, num_levels: int,
        investment_per_level: float, max_investment: float,
        risk_tolerance: str = "medium",
    ) -> GridOptimization:
        """Get AI-optimized grid parameters."""
        prompt = GRID_OPTIMIZATION_PROMPT.format(
            symbol=symbol, current_price=current_price, atr=atr,
            bb_lower=bb_lower, bb_upper=bb_upper, rsi=rsi,
            grid_lower=grid_lower, grid_upper=grid_upper,
            num_levels=num_levels, investment_per_level=investment_per_level,
            max_investment=max_investment, risk_tolerance=risk_tolerance,
        )
        response = await self._call_llm(prompt)
        logger.debug(f"Grid optimization response: {response}")
        return self._parse_grid_optimization(response, grid_lower, grid_upper, num_levels)

    def _parse_grid_optimization(
        self, response: str, default_lower: float,
        default_upper: float, default_levels: int,
    ) -> GridOptimization:
        """Parse grid optimization — JSON or line fallback."""
        parsed = parse_llm_json(response)
        if parsed:
            return self._parse_grid_opt_json(parsed, default_lower, default_upper, default_levels, response)
        return self._parse_grid_opt_lines(response, default_lower, default_upper, default_levels)

    def _parse_grid_opt_json(
        self, parsed: dict, default_lower: float,
        default_upper: float, default_levels: int, raw: str,
    ) -> GridOptimization:
        lower = extract_field(parsed, ("grid_lower", "lower_price", "lower"), converter=parse_price_value, default=default_lower)
        upper = extract_field(parsed, ("grid_upper", "upper_price", "upper"), converter=parse_price_value, default=default_upper)
        levels = extract_field(parsed, ("num_levels", "levels"), converter=lambda v: int(v), default=default_levels)
        confidence = 50
        if "confidence" in parsed:
            try:
                confidence = int(str(parsed["confidence"]).replace("%", ""))
            except (ValueError, TypeError):
                pass
        reasoning = str(parsed.get("reasoning", parsed.get("reason", "")))
        return GridOptimization(lower_price=lower, upper_price=upper, num_levels=levels,
                                confidence=confidence, reasoning=reasoning or raw[:200])

    @staticmethod
    def _parse_grid_opt_lines(
        response: str, default_lower: float,
        default_upper: float, default_levels: int,
    ) -> GridOptimization:
        lower, upper, levels, confidence, reasoning = default_lower, default_upper, default_levels, 50, ""
        for line in response.split('\n'):
            line = line.strip()
            if line.startswith('GRID_LOWER:'):
                try: lower = float(line.split(':')[1].strip().replace('$', '').replace(',', ''))
                except ValueError: pass
            elif line.startswith('GRID_UPPER:'):
                try: upper = float(line.split(':')[1].strip().replace('$', '').replace(',', ''))
                except ValueError: pass
            elif line.startswith('NUM_LEVELS:'):
                try: levels = int(line.split(':')[1].strip())
                except ValueError: pass
            elif line.startswith('CONFIDENCE:'):
                try: confidence = int(line.split(':')[1].strip().replace('%', ''))
                except ValueError: pass
            elif line.startswith('REASONING:'):
                reasoning = line.split(':', 1)[1].strip()
        return GridOptimization(lower_price=lower, upper_price=upper, num_levels=levels,
                                confidence=confidence, reasoning=reasoning or response[:200])

    # ── Risk Assessment ─────────────────────────────────────────────────────

    async def assess_risk(
        self, symbol: str, side: str, entry_price: float,
        current_price: float, position_size: float, base_currency: str,
        position_value: float, unrealized_pnl: float, pnl_percent: float,
        volatility: float, rsi: float, trend: str,
        total_balance: float, position_pct: float,
    ) -> RiskAssessment:
        """Assess risk for a position. Called by jesse-bot."""
        prompt = RISK_ASSESSMENT_PROMPT.format(
            symbol=symbol, side=side, entry_price=entry_price,
            current_price=current_price, position_size=position_size,
            base_currency=base_currency, position_value=position_value,
            unrealized_pnl=unrealized_pnl, pnl_percent=pnl_percent,
            volatility=volatility, rsi=rsi, trend=trend,
            total_balance=total_balance, position_pct=position_pct,
        )
        response = await self._call_llm(prompt)
        logger.debug(f"Risk assessment response: {response}")
        return self._parse_risk_assessment(response, current_price)

    def _parse_risk_assessment(self, response: str, current_price: float) -> RiskAssessment:
        """Parse risk assessment — JSON or line fallback."""
        parsed = parse_llm_json(response)
        if parsed:
            return self._parse_risk_json(parsed, current_price)
        return self._parse_risk_lines(response, current_price)

    @staticmethod
    def _parse_risk_json(parsed: dict, current_price: float) -> RiskAssessment:
        risk_score = 5
        if "risk_score" in parsed:
            try: risk_score = min(10, max(1, int(parsed["risk_score"])))
            except (ValueError, TypeError): pass
        act = str(parsed.get("action", "")).upper()
        action = act if act in ("CLOSE", "REDUCE", "ADD", "HOLD") else "HOLD"
        stop_loss = extract_field(parsed, ("stop_loss", "sl"), converter=parse_price_value, default=current_price * 0.95)
        take_profit = extract_field(parsed, ("take_profit", "tp"), converter=parse_price_value, default=current_price * 1.10)
        return RiskAssessment(risk_score=risk_score, action=action, stop_loss=stop_loss,
                              take_profit=take_profit, warning=parsed.get("warning"))

    @staticmethod
    def _parse_risk_lines(response: str, current_price: float) -> RiskAssessment:
        risk_score, action = 5, "HOLD"
        stop_loss, take_profit, warning = current_price * 0.95, current_price * 1.10, None
        for line in response.split('\n'):
            line = line.strip()
            if 'risk score' in line.lower():
                match = re.search(r'(\d+)', line)
                if match: risk_score = min(10, max(1, int(match.group(1))))
            elif 'action' in line.lower():
                for act in ['CLOSE', 'REDUCE', 'ADD', 'HOLD']:
                    if act in line.upper():
                        action = act
                        break
            elif 'stop loss' in line.lower():
                match = re.search(r'\$?([\d,]+(?:\.\d+)?)', line)
                if match:
                    try: stop_loss = float(match.group(1).replace(',', ''))
                    except ValueError: pass
            elif 'take profit' in line.lower():
                match = re.search(r'\$?([\d,]+(?:\.\d+)?)', line)
                if match:
                    try: take_profit = float(match.group(1).replace(',', ''))
                    except ValueError: pass
            elif 'warning' in line.lower():
                warning = line.split(':', 1)[-1].strip()
        return RiskAssessment(risk_score=risk_score, action=action, stop_loss=stop_loss,
                              take_profit=take_profit, warning=warning)

    # ── Signal Confirmation ─────────────────────────────────────────────────

    async def confirm_signal(
        self, signal_type: str, symbol: str, price: float,
        grid_level: int, reason: str, market_context: str, recent_trades: str,
    ) -> tuple[SignalDecision, str]:
        """Get AI confirmation for a trading signal."""
        prompt = SIGNAL_CONFIRMATION_PROMPT.format(
            signal_type=signal_type, symbol=symbol, price=price,
            grid_level=grid_level, reason=reason,
            market_context=market_context, recent_trades=recent_trades,
        )
        response = await self._call_llm(prompt)
        logger.debug(f"Signal confirmation response: {response}")

        parsed = parse_llm_json(response)
        if parsed:
            decision_str = str(parsed.get("decision", parsed.get("action", ""))).upper()
            reason_text = str(parsed.get("reason", response[:200]))
            if "CONFIRM" in decision_str:
                return SignalDecision.CONFIRM, reason_text
            elif "REJECT" in decision_str:
                return SignalDecision.REJECT, reason_text
            return SignalDecision.WAIT, reason_text

        response_upper = response.upper()
        reason_text = response.split(':', 1)[-1].strip() if ':' in response else response
        if 'CONFIRM' in response_upper:
            return SignalDecision.CONFIRM, reason_text
        elif 'REJECT' in response_upper:
            return SignalDecision.REJECT, reason_text
        return SignalDecision.WAIT, reason_text


# Global agent instance — lazy proxy to defer instantiation
_trading_agent = None


def get_trading_agent() -> TradingAgent:
    """Lazy factory for TradingAgent singleton."""
    global _trading_agent
    if _trading_agent is None:
        _trading_agent = TradingAgent()
    return _trading_agent


class _LazyAgent:
    """Proxy that defers TradingAgent() instantiation until first attribute access."""
    def __getattr__(self, name):
        return getattr(get_trading_agent(), name)


trading_agent = _LazyAgent()
