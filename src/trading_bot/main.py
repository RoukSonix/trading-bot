"""Trading Bot main entry point."""

import sys
from loguru import logger

from trading_bot.config import settings
from trading_bot.core.exchange import exchange_client


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
    
    # Test: Get balances
    logger.info("")
    logger.info("📊 Account Balances:")
    balances = exchange_client.get_all_balances(min_value=0.001)
    for b in balances[:10]:  # Top 10
        logger.info(f"  {b['currency']}: {b['total']:.8f} (free: {b['free']:.8f})")
    
    # Test: Get BTC price
    logger.info("")
    logger.info("💰 BTC/USDT Ticker:")
    ticker = exchange_client.get_ticker("BTC/USDT")
    logger.info(f"  Last: ${ticker['last']:,.2f}")
    logger.info(f"  Bid:  ${ticker['bid']:,.2f}")
    logger.info(f"  Ask:  ${ticker['ask']:,.2f}")
    logger.info(f"  24h Change: {ticker['change_percent']:.2f}%")
    
    # Test: Get order book
    logger.info("")
    logger.info("📖 Order Book (top 5):")
    book = exchange_client.get_order_book("BTC/USDT", limit=5)
    logger.info(f"  Spread: ${book['spread']:.2f}")
    logger.info("  Bids:")
    for price, amount in book["bids"]:
        logger.info(f"    ${price:,.2f} - {amount:.6f} BTC")
    logger.info("  Asks:")
    for price, amount in book["asks"]:
        logger.info(f"    ${price:,.2f} - {amount:.6f} BTC")
    
    logger.info("")
    logger.info("✅ Sprint 1 complete! Exchange connection working.")


if __name__ == "__main__":
    main()
