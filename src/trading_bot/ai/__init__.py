"""AI module for trading decisions."""

from trading_bot.ai.agent import (
    TradingAgent,
    MarketAnalysis,
    GridOptimization,
    RiskAssessment,
    Trend,
    RiskLevel,
    SignalDecision,
    trading_agent,
)
from trading_bot.ai.prompts import (
    SYSTEM_PROMPT,
    MARKET_ANALYSIS_PROMPT,
    GRID_OPTIMIZATION_PROMPT,
    RISK_ASSESSMENT_PROMPT,
    SIGNAL_CONFIRMATION_PROMPT,
)

__all__ = [
    # Agent
    "TradingAgent",
    "trading_agent",
    # Data classes
    "MarketAnalysis",
    "GridOptimization",
    "RiskAssessment",
    # Enums
    "Trend",
    "RiskLevel",
    "SignalDecision",
    # Prompts
    "SYSTEM_PROMPT",
    "MARKET_ANALYSIS_PROMPT",
    "GRID_OPTIMIZATION_PROMPT",
    "RISK_ASSESSMENT_PROMPT",
    "SIGNAL_CONFIRMATION_PROMPT",
]
