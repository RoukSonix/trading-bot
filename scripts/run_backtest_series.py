#!/usr/bin/env python3
"""Run backtest series with different grid configurations."""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from loguru import logger
from trading_bot.core.exchange import exchange_client
from trading_bot.core.indicators import Indicators
from trading_bot.backtest import Backtester


async def main():
    """Run backtest series."""
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
    )
    
    logger.info("=" * 60)
    logger.info("📊 BACKTEST SERIES")
    logger.info("=" * 60)
    
    # Connect to exchange for data
    logger.info("Connecting to exchange...")
    exchange_client.connect()
    
    # Fetch historical data (1h candles, 30 days)
    logger.info("Fetching historical data...")
    ohlcv = exchange_client.get_ohlcv("BTC/USDT", timeframe="1h", limit=720)  # 30 days
    df = Indicators.to_dataframe(ohlcv)
    df = Indicators.add_all_indicators(df)
    
    logger.info(f"Data: {len(df)} candles from {df.index[0]} to {df.index[-1]}")
    
    # Define test configurations
    configs = [
        # Varying grid levels
        {"name": "levels_8_sp1.5", "levels": 8, "spacing": 1.5, "amount": 0.001},
        {"name": "levels_10_sp1.5", "levels": 10, "spacing": 1.5, "amount": 0.001},
        {"name": "levels_12_sp1.5", "levels": 12, "spacing": 1.5, "amount": 0.001},
        
        # Varying spacing
        {"name": "levels_10_sp1.0", "levels": 10, "spacing": 1.0, "amount": 0.001},
        {"name": "levels_10_sp2.0", "levels": 10, "spacing": 2.0, "amount": 0.001},
        {"name": "levels_10_sp2.5", "levels": 10, "spacing": 2.5, "amount": 0.001},
        
        # Aggressive vs conservative
        {"name": "aggressive", "levels": 15, "spacing": 0.8, "amount": 0.002},
        {"name": "conservative", "levels": 6, "spacing": 3.0, "amount": 0.0005},
    ]
    
    # Run backtests
    backtester = Backtester(initial_balance=10000.0, commission=0.001)
    results = backtester.run_comparison(configs, df, price_column="close")
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = f"data/backtest_results_{timestamp}.json"
    backtester.save_results(results, filepath)
    
    logger.info("")
    logger.info("✅ Backtest series completed!")
    logger.info(f"Best config: {results[0].config_name} ({results[0].total_return:+.2f}%)")


if __name__ == "__main__":
    asyncio.run(main())
