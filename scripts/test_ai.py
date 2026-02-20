#!/usr/bin/env python3
"""Test AI agent functionality."""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from trading_bot.ai import trading_agent, Trend


async def test_market_analysis():
    """Test market analysis with sample data."""
    
    if not trading_agent.is_available:
        print("❌ AI not available. Set OPENROUTER_API_KEY in .env")
        return False
    
    print("🤖 Testing AI Market Analysis...")
    print("-" * 50)
    
    # Sample market data (BTC-like)
    analysis = await trading_agent.analyze_market(
        symbol="BTC/USDT",
        current_price=96500.0,
        high_24h=97200.0,
        low_24h=95100.0,
        change_24h=1.2,
        indicators={
            "RSI (14)": 55.3,
            "SMA (20)": 95800.0,
            "EMA (20)": 96100.0,
            "MACD": 120.5,
            "BB Upper": 98000.0,
            "BB Lower": 94500.0,
            "ATR (14)": 850.0,
        },
        best_bid=96495.0,
        best_ask=96505.0,
        price_action="Price bounced from $95,100 support, now testing $96,500 resistance. Volume increasing.",
    )
    
    print(f"📊 Analysis Results:")
    print(f"   Trend: {analysis.trend.value}")
    print(f"   Risk Level: {analysis.risk_level.value}")
    print(f"   Volatility Suitable: {analysis.volatility_suitable}")
    print(f"   Grid Recommended: {analysis.grid_recommended}")
    print(f"   Support: ${analysis.support_level:,.2f}")
    print(f"   Resistance: ${analysis.resistance_level:,.2f}")
    
    if analysis.suggested_lower and analysis.suggested_upper:
        print(f"   Suggested Range: ${analysis.suggested_lower:,.2f} - ${analysis.suggested_upper:,.2f}")
    
    print()
    print("💬 AI Reasoning:")
    print(analysis.reasoning[:300] + "..." if len(analysis.reasoning) > 300 else analysis.reasoning)
    
    return True


async def test_grid_optimization():
    """Test grid optimization."""
    
    if not trading_agent.is_available:
        return False
    
    print()
    print("🔧 Testing Grid Optimization...")
    print("-" * 50)
    
    optimization = await trading_agent.optimize_grid(
        symbol="BTC/USDT",
        current_price=96500.0,
        atr=850.0,
        bb_lower=94500.0,
        bb_upper=98000.0,
        rsi=55.3,
        grid_lower=94000.0,
        grid_upper=99000.0,
        num_levels=10,
        investment_per_level=100.0,
        max_investment=1000.0,
        risk_tolerance="medium",
    )
    
    print(f"📐 Optimized Grid:")
    print(f"   Lower: ${optimization.lower_price:,.2f}")
    print(f"   Upper: ${optimization.upper_price:,.2f}")
    print(f"   Levels: {optimization.num_levels}")
    print(f"   Confidence: {optimization.confidence}%")
    print(f"   Reasoning: {optimization.reasoning}")
    
    return True


async def test_signal_confirmation():
    """Test signal confirmation."""
    
    if not trading_agent.is_available:
        return False
    
    print()
    print("✅ Testing Signal Confirmation...")
    print("-" * 50)
    
    decision, reason = await trading_agent.confirm_signal(
        signal_type="BUY",
        symbol="BTC/USDT",
        price=95500.0,
        grid_level=3,
        reason="Price hit grid level 3 (buy zone)",
        market_context="RSI: 45, Trend: sideways, Volume: average",
        recent_trades="Last trade: SELL at $96,800 (profit $50)",
    )
    
    print(f"🎯 Signal Decision: {decision.value.upper()}")
    print(f"   Reason: {reason}")
    
    return True


async def main():
    """Run all tests."""
    print("=" * 50)
    print("🧪 Trading Bot AI Test Suite")
    print("=" * 50)
    print()
    
    try:
        success = await test_market_analysis()
        if success:
            await test_grid_optimization()
            await test_signal_confirmation()
        
        print()
        print("=" * 50)
        print("✅ All tests completed!" if success else "❌ Tests failed - check API key")
        print("=" * 50)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
