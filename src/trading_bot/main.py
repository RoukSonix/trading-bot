"""Trading Bot main entry point."""

import sys
from loguru import logger

from trading_bot.config import settings
from trading_bot.core.exchange import exchange_client
from trading_bot.core.data_collector import data_collector
from trading_bot.core.indicators import indicators


def setup_logging():
    """Configure logging."""
    logger.remove()
    
    # Console output
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
    )
    
    # File output
    logger.add(
        "logs/trading_{time:YYYY-MM-DD}.log",
        rotation="1 day",
        level=settings.log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    )


def main():
    """Main application entry point."""
    setup_logging()
    
    logger.info("=" * 50)
    logger.info("Trading Bot starting...")
    logger.info(f"Environment: {settings.binance_env.value}")
    logger.info("=" * 50)
    
    # Connect to exchange
    exchange_client.connect()
    
    # === Sprint 2: Data Layer Test ===
    symbol = "BTC/USDT"
    timeframe = "1h"
    
    # Fetch and store OHLCV data
    logger.info("")
    logger.info(f"📊 Fetching {symbol} {timeframe} data...")
    new_candles = data_collector.fetch_and_store_ohlcv(symbol, timeframe, limit=100)
    total_candles = data_collector.count_candles(symbol, timeframe)
    logger.info(f"Database: {total_candles} candles stored")
    
    # Get data from DB and calculate indicators
    logger.info("")
    logger.info("📈 Calculating indicators...")
    candles = data_collector.get_ohlcv(symbol, timeframe, limit=50)
    df = indicators.to_dataframe(candles)
    df = indicators.add_all_indicators(df)
    
    # Show latest values
    latest = df.iloc[-1]
    logger.info(f"Latest {symbol} data:")
    logger.info(f"  Close:      ${latest['close']:,.2f}")
    logger.info(f"  SMA(20):    ${latest['sma_20']:,.2f}")
    logger.info(f"  SMA(50):    ${latest['sma_50']:,.2f}")
    logger.info(f"  RSI(14):    {latest['rsi']:.1f}")
    logger.info(f"  BB Upper:   ${latest['bb_upper']:,.2f}")
    logger.info(f"  BB Lower:   ${latest['bb_lower']:,.2f}")
    logger.info(f"  MACD:       {latest['macd']:.2f}")
    logger.info(f"  ATR:        ${latest['atr']:,.2f}")
    
    # Market analysis
    logger.info("")
    logger.info("🔍 Market Analysis:")
    
    # RSI analysis
    rsi = latest["rsi"]
    if rsi > 70:
        logger.info(f"  RSI: OVERBOUGHT ({rsi:.1f})")
    elif rsi < 30:
        logger.info(f"  RSI: OVERSOLD ({rsi:.1f})")
    else:
        logger.info(f"  RSI: Neutral ({rsi:.1f})")
    
    # Price vs SMA
    close = latest["close"]
    sma20 = latest["sma_20"]
    if close > sma20:
        logger.info(f"  Trend: BULLISH (price above SMA20)")
    else:
        logger.info(f"  Trend: BEARISH (price below SMA20)")
    
    # Bollinger position
    bb_upper = latest["bb_upper"]
    bb_lower = latest["bb_lower"]
    bb_position = (close - bb_lower) / (bb_upper - bb_lower) * 100
    logger.info(f"  BB Position: {bb_position:.0f}% (0=lower, 100=upper)")
    
    logger.info("")
    logger.info("✅ Sprint 2 complete! Data layer working.")


if __name__ == "__main__":
    main()
