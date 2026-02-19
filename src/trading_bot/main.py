"""Trading Bot main entry point."""

import sys
from loguru import logger

from trading_bot.config import settings
from trading_bot.core.exchange import exchange_client
from trading_bot.core.data_collector import data_collector
from trading_bot.core.indicators import indicators
from trading_bot.strategies.grid import GridStrategy, GridConfig


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
    
    # Get current price
    ticker = exchange_client.get_ticker(symbol)
    current_price = ticker["last"]
    logger.info(f"\n💰 Current {symbol} price: ${current_price:,.2f}")
    
    # === Sprint 3: Grid Strategy Test ===
    logger.info("\n" + "=" * 50)
    logger.info("📊 GRID STRATEGY TEST")
    logger.info("=" * 50)
    
    # Configure grid
    config = GridConfig(
        grid_levels=5,           # 5 levels on each side
        grid_spacing_pct=0.5,    # 0.5% spacing
        amount_per_level=0.001,  # 0.001 BTC per level
    )
    
    # Initialize strategy
    strategy = GridStrategy(symbol=symbol, config=config)
    strategy.start()
    
    # Setup grid around current price
    strategy.setup_grid(current_price)
    
    # Print grid visualization
    strategy.print_grid()
    
    # Simulate price movements
    logger.info("\n" + "=" * 50)
    logger.info("🎮 PAPER TRADING SIMULATION")
    logger.info("=" * 50)
    
    # Simulate prices (going down then up)
    simulated_prices = [
        current_price * 0.995,  # -0.5%
        current_price * 0.990,  # -1.0%
        current_price * 0.985,  # -1.5%
        current_price * 0.990,  # -1.0% (bounce)
        current_price * 0.995,  # -0.5%
        current_price * 1.000,  # back to start
        current_price * 1.005,  # +0.5%
        current_price * 1.010,  # +1.0%
    ]
    
    # Get some candle data for the strategy (not really used in grid but good practice)
    candles = data_collector.get_ohlcv(symbol, "1h", limit=50)
    df = indicators.to_dataframe(candles)
    df = indicators.add_all_indicators(df)
    
    for i, price in enumerate(simulated_prices):
        logger.info(f"\n--- Step {i+1}: Price = ${price:,.2f} ---")
        
        # Calculate signals
        signals = strategy.calculate_signals(df, price)
        
        # Execute paper trades
        for signal in signals:
            trade = strategy.execute_paper_trade(signal)
            if trade["status"] == "filled":
                logger.info(f"  Balance: ${trade['balance']:,.2f} USDT | Holdings: {trade['holdings']:.6f} BTC")
    
    # Final status
    logger.info("\n" + "=" * 50)
    logger.info("📈 FINAL STATUS")
    logger.info("=" * 50)
    
    status = strategy.get_status()
    logger.info(f"Total trades: {status['paper_trading']['trades_count']}")
    logger.info(f"USDT Balance: ${status['paper_trading']['balance_usdt']:,.2f}")
    logger.info(f"BTC Holdings: {status['paper_trading']['holdings_btc']:.6f}")
    
    # Calculate final portfolio value at current price
    portfolio_value = status['paper_trading']['balance_usdt'] + (status['paper_trading']['holdings_btc'] * current_price)
    pnl = portfolio_value - 10000  # Started with 10000
    pnl_pct = (pnl / 10000) * 100
    
    logger.info(f"Portfolio Value: ${portfolio_value:,.2f}")
    logger.info(f"PnL: ${pnl:+,.2f} ({pnl_pct:+.2f}%)")
    
    # Print final grid
    strategy.print_grid()
    
    logger.info("\n✅ Sprint 3 complete! Grid strategy working.")


if __name__ == "__main__":
    main()
