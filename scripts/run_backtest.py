#!/usr/bin/env python3
"""Run backtesting on historical data."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from loguru import logger

from trading_bot.core.exchange import exchange_client
from trading_bot.core.indicators import Indicators
from trading_bot.strategies import GridStrategy, GridConfig
from trading_bot.backtest import Backtester


def setup_logging():
    """Configure logging."""
    logger.remove()
    logger.add(
        sys.stdout,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | <cyan>{message}</cyan>",
    )


def main():
    """Run backtest."""
    setup_logging()
    
    logger.info("=" * 50)
    logger.info("📈 GRID STRATEGY BACKTEST")
    logger.info("=" * 50)
    
    # Connect to exchange
    logger.info("Connecting to exchange...")
    exchange_client.connect()
    
    symbol = "BTC/USDT"
    
    # Fetch historical data
    logger.info(f"Fetching historical data for {symbol}...")
    
    # Get 1000 1-hour candles (~41 days)
    ohlcv = exchange_client.get_ohlcv(symbol, timeframe="1h", limit=1000)
    df = Indicators.to_dataframe(ohlcv)
    df = Indicators.add_all_indicators(df)
    
    logger.info(f"Loaded {len(df)} candles")
    logger.info(f"Date range: {df.index[0]} to {df.index[-1]}")
    logger.info(f"Price range: ${df['low'].min():,.2f} - ${df['high'].max():,.2f}")
    
    # Initialize strategy
    strategy = GridStrategy(
        symbol=symbol,
        config=GridConfig(
            grid_levels=5,
            grid_spacing_pct=2.0,  # 2% spacing
            amount_per_level=0.001,
        ),
    )
    
    # Set up initial grid based on first price
    initial_price = df["close"].iloc[0]
    strategy.setup_grid(initial_price)
    
    logger.info(f"Grid initialized at ${initial_price:,.2f}")
    
    # Run backtest
    backtester = Backtester(
        initial_balance=10000.0,
        commission=0.001,  # 0.1%
    )
    
    result = backtester.run(
        strategy=strategy,
        data=df,
        price_column="close",
    )
    
    # Additional stats
    logger.info("")
    logger.info("📊 Trade Summary:")
    
    buys = [t for t in result.trades if t["type"] == "BUY"]
    sells = [t for t in result.trades if t["type"] == "SELL"]
    
    logger.info(f"   Buys: {len(buys)}")
    logger.info(f"   Sells: {len(sells)}")
    
    if buys:
        avg_buy = sum(t["price"] for t in buys) / len(buys)
        logger.info(f"   Avg Buy Price: ${avg_buy:,.2f}")
    
    if sells:
        avg_sell = sum(t["price"] for t in sells) / len(sells)
        logger.info(f"   Avg Sell Price: ${avg_sell:,.2f}")
    
    # Annualized return
    if result.duration_days > 0:
        annual_return = result.total_return * (365 / result.duration_days)
        logger.info(f"\n📈 Annualized Return: {annual_return:+.2f}%")


if __name__ == "__main__":
    main()
