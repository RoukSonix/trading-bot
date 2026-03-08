"""
Jesse routes configuration.

Defines which strategy runs on which symbol/timeframe.
"""

routes = [
    {
        'exchange': 'Binance Perpetual Futures',
        'symbol': 'BTC-USDT',
        'timeframe': '1h',
        'strategy': 'AIGridStrategy',
    },
]

# Additional data routes for multi-timeframe strategies
data_routes = [
    # Example: use 4h for trend detection
    # {
    #     'exchange': 'Binance Perpetual Futures',
    #     'symbol': 'BTC-USDT',
    #     'timeframe': '4h',
    # },
]
