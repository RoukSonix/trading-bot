#!/usr/bin/env python3
"""Simple Grid Bot without AI - for testing."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # monorepo root (for shared.*)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from loguru import logger
from binance_bot.core.exchange import exchange_client
from binance_bot.strategies import GridStrategy, GridConfig


async def run():
    # Setup logging
    logger.remove()
    logger.add(
        sys.stdout,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <cyan>{message}</cyan>",
    )
    logger.add(
        "logs/grid_simple.log",
        rotation="1 day",
        level="DEBUG",
    )
    
    logger.info("🤖 SIMPLE GRID BOT starting...")
    logger.info("Mode: No AI, paper trading")
    
    # Connect
    exchange_client.connect()
    
    symbol = "BTC/USDT"
    ticker = exchange_client.get_ticker(symbol)
    price = ticker["last"]
    
    logger.info(f"Current price: ${price:,.2f}")
    
    # Setup grid
    strategy = GridStrategy(
        symbol=symbol,
        config=GridConfig(
            grid_levels=5,
            grid_spacing_pct=1.5,
            amount_per_level=0.0001,
        ),
    )
    strategy.setup_grid(price)
    strategy.print_grid()
    
    logger.info("🚀 Running... (Ctrl+C to stop)")
    
    tick = 0
    try:
        while True:
            tick += 1
            
            # Get current price
            ticker = exchange_client.get_ticker(symbol)
            current = ticker["last"]
            
            # Check signals
            signals = strategy.calculate_signals(None, current)
            
            for sig in signals:
                trade = strategy.execute_paper_trade(sig)
                if trade["status"] == "filled":
                    logger.info(
                        f"⚡ {sig.type.value.upper()} "
                        f"{sig.amount:.6f} @ ${sig.price:,.2f}"
                    )
            
            # Status every 5 minutes (60 ticks * 5 sec)
            if tick % 60 == 0:
                status = strategy.get_status()
                paper = status["paper_trading"]
                logger.info(
                    f"📊 Price: ${current:,.2f} | "
                    f"Trades: {paper['trades_count']} | "
                    f"Value: ${paper['total_value']:,.2f}"
                )
            
            await asyncio.sleep(5)
            
    except KeyboardInterrupt:
        logger.info("🛑 Stopping...")
        
        # Final status
        status = strategy.get_status()
        paper = status["paper_trading"]
        
        logger.info("")
        logger.info("=" * 50)
        logger.info("📈 FINAL STATUS")
        logger.info("=" * 50)
        logger.info(f"Trades: {paper['trades_count']}")
        logger.info(f"Holdings: {paper['holdings_btc']:.6f} BTC")
        logger.info(f"Balance: ${paper['balance_usdt']:,.2f}")
        logger.info(f"Total Value: ${paper['total_value']:,.2f}")
        
        profit = paper["total_value"] - 10000
        logger.info(f"Profit: ${profit:+,.2f}")


if __name__ == "__main__":
    asyncio.run(run())
