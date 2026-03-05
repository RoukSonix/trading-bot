#!/usr/bin/env python3
"""Run AI Grid Trading Strategy - End-to-End Pipeline.

Architecture:
1. AI analyzes market and optimizes grid parameters (on startup)
2. Grid strategy runs autonomously (fast, no AI delay)
3. AI periodic review every N minutes (adjust or stop if needed)
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # monorepo root (for shared.*)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from loguru import logger

from shared.config import settings
from binance_bot.core.exchange import exchange_client
from shared.core.indicators import Indicators
from binance_bot.strategies import AIGridStrategy, AIGridConfig


def setup_logging():
    """Configure logging."""
    logger.remove()
    logger.add(
        sys.stdout,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
    )


async def run_ai_grid():
    """Run AI Grid Strategy pipeline."""
    
    setup_logging()
    
    logger.info("=" * 60)
    logger.info("🤖 AI GRID TRADING BOT")
    logger.info("=" * 60)
    logger.info(f"Mode: AI Setup + Autonomous Grid + Periodic Review")
    logger.info(f"Environment: {settings.binance_env.value}")
    logger.info(f"AI Model: {settings.openrouter_model}")
    logger.info("")
    
    # === Step 1: Connect to Exchange ===
    logger.info("📡 Connecting to exchange...")
    exchange_client.connect()
    
    symbol = "BTC/USDT"
    
    # === Step 2: Fetch Market Data ===
    logger.info(f"📊 Fetching market data for {symbol}...")
    
    ticker = exchange_client.get_ticker(symbol)
    current_price = ticker["last"]
    high_24h = ticker["high"]
    low_24h = ticker["low"]
    change_24h = ticker.get("percentage", 0) or 0
    
    logger.info(f"   Price: ${current_price:,.2f}")
    logger.info(f"   24h: ${low_24h:,.2f} - ${high_24h:,.2f} ({change_24h:+.2f}%)")
    
    # Order book
    order_book = exchange_client.get_order_book(symbol)
    best_bid = order_book["bids"][0][0] if order_book["bids"] else current_price * 0.999
    best_ask = order_book["asks"][0][0] if order_book["asks"] else current_price * 1.001
    
    # Indicators
    ohlcv = exchange_client.get_ohlcv(symbol, timeframe="1h", limit=100)
    ohlcv_df = Indicators.to_dataframe(ohlcv)
    indicators_df = Indicators.add_all_indicators(ohlcv_df)
    
    latest = indicators_df.iloc[-1]
    indicator_dict = {
        "RSI (14)": latest.get("rsi", 50),
        "SMA (20)": latest.get("sma_20", current_price),
        "EMA (20)": latest.get("ema_20", current_price),
        "MACD": latest.get("macd", 0),
        "BB Upper": latest.get("bb_upper", current_price * 1.02),
        "BB Lower": latest.get("bb_lower", current_price * 0.98),
        "ATR (14)": latest.get("atr", current_price * 0.01),
    }
    
    logger.info(f"   RSI: {indicator_dict['RSI (14)']:.1f}, ATR: ${indicator_dict['ATR (14)']:,.2f}")
    
    # === Step 3: Initialize AI Grid Strategy ===
    logger.info("")
    logger.info("🎯 Initializing AI Grid Strategy...")
    
    config = AIGridConfig(
        grid_levels=5,
        grid_spacing_pct=1.0,
        amount_per_level=0.0001,
        # AI settings
        ai_enabled=True,
        ai_confirm_signals=False,      # NO per-signal confirmation (fast!)
        ai_auto_optimize=True,         # AI optimizes grid on setup
        ai_periodic_review=True,       # AI reviews periodically
        review_interval_minutes=15,
        min_confidence=50,
        risk_tolerance="medium",
    )
    
    strategy = AIGridStrategy(symbol=symbol, config=config)
    
    # === Step 4: AI Analysis & Grid Setup ===
    logger.info("")
    logger.info("🧠 AI Market Analysis & Grid Setup...")
    
    should_trade, reason = await strategy.analyze_and_setup(
        current_price=current_price,
        high_24h=high_24h,
        low_24h=low_24h,
        change_24h=change_24h,
        indicators=indicator_dict,
        best_bid=best_bid,
        best_ask=best_ask,
        price_action=f"Price at ${current_price:,.2f}",
    )
    
    if not should_trade:
        logger.warning(f"❌ AI: {reason}")
        return
    
    logger.info(f"✅ {reason}")
    strategy.print_grid()
    
    # === Step 5: Simulate Trading (Grid runs autonomously) ===
    logger.info("")
    logger.info("⚡ Simulating autonomous grid trading (no AI delay)...")
    
    # Simulate price movements
    price_changes = [-1, -2, -1.5, +1, +2, +1.5, -0.5, +0.5]
    
    for i, pct in enumerate(price_changes):
        sim_price = current_price * (1 + pct/100)
        
        # Grid calculates signals WITHOUT AI (fast!)
        signals = strategy.calculate_signals(indicators_df, sim_price)
        
        if signals:
            for signal in signals:
                trade = strategy.execute_paper_trade(signal)
                if trade["status"] == "filled":
                    logger.info(f"   ⚡ {signal.type.value.upper()} {signal.amount:.6f} @ ${signal.price:,.2f} (Price: ${sim_price:,.2f})")
        
        # Small delay to simulate real-time
        await asyncio.sleep(0.1)
    
    # === Step 6: Periodic AI Review ===
    logger.info("")
    logger.info("🔄 Running periodic AI review...")
    
    review = await strategy.periodic_review(
        current_price=current_price,
        indicators=indicator_dict,
        position_value=strategy.paper_holdings * current_price,
        unrealized_pnl=0,
    )
    
    # === Final Status ===
    logger.info("")
    logger.info("=" * 60)
    logger.info("📈 FINAL STATUS")
    logger.info("=" * 60)
    
    status = strategy.get_status()
    paper = status['paper_trading']
    
    logger.info(f"Grid: {status['active_buy_levels']} buys, {status['active_sell_levels']} sells active")
    logger.info(f"Trades executed: {paper['trades_count']}")
    logger.info(f"Holdings: {paper['holdings_btc']:.6f} BTC + ${paper['balance_usdt']:,.2f} USDT")
    logger.info(f"Total value: ${paper['total_value']:,.2f}")
    
    if status['ai']['last_optimization']:
        opt = status['ai']['last_optimization']
        logger.info(f"AI Confidence: {opt['confidence']}%")
    
    logger.info("")
    logger.info("✅ Pipeline complete!")


if __name__ == "__main__":
    asyncio.run(run_ai_grid())
