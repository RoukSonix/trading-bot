#!/usr/bin/env python3
"""
Simple test script to run Jesse backtest with AIGridStrategy.

Usage:
    python scripts/run_backtest.py
"""

import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set working directory to jesse-bot
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Import Jesse modules
from jesse import routes
from jesse.modes import backtest_mode
from jesse.config import config


def run_backtest():
    """Run backtest with AIGridStrategy."""
    
    # Configure for backtest
    config['app']['trading_mode'] = 'backtest'
    
    # Define routes
    from jesse.routes import router
    
    # Test route definition
    test_routes = [
        {
            'exchange': 'Binance Perpetual Futures',
            'symbol': 'BTC-USDT',
            'timeframe': '1h',
            'strategy': 'AIGridStrategy',
        },
    ]
    
    test_data_routes = []
    
    # Initialize router
    router.initiate(test_routes, test_data_routes)
    
    # Run backtest
    print("Running backtest...")
    print(f"Strategy: AIGridStrategy")
    print(f"Symbol: BTC-USDT")
    print(f"Timeframe: 1h")
    print(f"Period: 2024-01-01 to 2024-03-01")
    print()
    
    try:
        backtest_mode.run(
            client_id='test-backtest',
            debug_mode=False,
            user_config={},
            exchange='Binance Perpetual Futures',
            routes=test_routes,
            data_routes=test_data_routes,
            start_date='2024-01-01',
            finish_date='2024-03-01',
            candles=None,
            chart=False,
            tradingview=False,
            csv=False,
            json=False,
            fast_mode=False,
            benchmark=False,
        )
    except Exception as e:
        print(f"Error during backtest: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    run_backtest()
