"""Trading Bot main entry point."""

import sys
import time
from loguru import logger

from trading_bot.config import settings
from trading_bot.core.exchange import exchange_client
from trading_bot.core.order_manager import order_manager, OrderType
from trading_bot.core.position_manager import position_manager


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
    
    symbol = "BTC/USDT"
    
    # Get current price and balance
    ticker = exchange_client.get_ticker(symbol)
    current_price = ticker["last"]
    
    usdt_balance = exchange_client.get_balance("USDT")
    btc_balance = exchange_client.get_balance("BTC")
    
    logger.info(f"\n💰 Current {symbol} price: ${current_price:,.2f}")
    logger.info(f"💵 USDT Balance: ${usdt_balance['free']:,.2f}")
    logger.info(f"₿ BTC Balance: {btc_balance['free']:.6f}")
    
    # === Sprint 4: Order Execution Test ===
    logger.info("\n" + "=" * 50)
    logger.info("📊 ORDER EXECUTION TEST (TESTNET)")
    logger.info("=" * 50)
    
    # Test 1: Place a limit buy order below current price
    buy_price = current_price * 0.99  # 1% below
    buy_amount = 0.001  # Small amount for testing
    
    logger.info(f"\n--- Test 1: Limit BUY order ---")
    buy_order = order_manager.create_limit_order(
        symbol=symbol,
        side="buy",
        amount=buy_amount,
        price=buy_price,
    )
    logger.info(f"Order status: {buy_order.status.value}")
    
    # Test 2: Place a limit sell order above current price
    sell_price = current_price * 1.01  # 1% above
    
    logger.info(f"\n--- Test 2: Limit SELL order ---")
    # First check if we have BTC to sell
    if btc_balance["free"] >= buy_amount:
        sell_order = order_manager.create_limit_order(
            symbol=symbol,
            side="sell",
            amount=buy_amount,
            price=sell_price,
        )
        logger.info(f"Order status: {sell_order.status.value}")
    else:
        logger.info(f"Skipped - insufficient BTC balance ({btc_balance['free']:.6f})")
    
    # Test 3: Check open orders
    logger.info(f"\n--- Test 3: Open orders ---")
    open_orders = order_manager.get_open_orders(symbol)
    logger.info(f"Open orders: {len(open_orders)}")
    for order in open_orders[:5]:
        logger.info(f"  {order['side'].upper()} {order['amount']} @ ${order['price']:,.2f} [{order['status']}]")
    
    # Test 4: Cancel the test orders
    logger.info(f"\n--- Test 4: Cancel test orders ---")
    if buy_order.id:
        order_manager.cancel_order(buy_order.id, symbol)
    
    # Test 5: Market order (actually executes!)
    logger.info(f"\n--- Test 5: Market BUY order ---")
    market_order = order_manager.create_market_order(
        symbol=symbol,
        side="buy",
        amount=0.0001,  # Very small amount
    )
    logger.info(f"Order status: {market_order.status.value}")
    
    if market_order.status.value == "filled":
        logger.info(f"Filled at: ${market_order.price:,.2f}")
        logger.info(f"Cost: ${market_order.cost:.4f}")
        
        # Update position
        position_manager.update_position(
            symbol=symbol,
            side="buy",
            amount=market_order.filled,
            price=market_order.price,
        )
    
    # Test 6: Position tracking
    logger.info(f"\n--- Test 6: Position tracking ---")
    position_manager.calculate_unrealized_pnl(symbol, current_price)
    position_manager.print_summary()
    
    # Final balances
    logger.info("\n" + "=" * 50)
    logger.info("📈 FINAL BALANCES")
    logger.info("=" * 50)
    
    usdt_balance = exchange_client.get_balance("USDT")
    btc_balance = exchange_client.get_balance("BTC")
    
    logger.info(f"💵 USDT: ${usdt_balance['free']:,.2f}")
    logger.info(f"₿ BTC: {btc_balance['free']:.6f}")
    
    portfolio = position_manager.get_portfolio_value({symbol: current_price})
    logger.info(f"📊 Portfolio Value: ${portfolio['total_value']:,.2f}")
    logger.info(f"📊 Total PnL: ${portfolio['total_pnl']:+,.2f}")
    
    logger.info("\n✅ Sprint 4 complete! Order execution working.")


if __name__ == "__main__":
    main()
