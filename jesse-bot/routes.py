"""
Jesse routes configuration.

Defines which strategy runs on which symbol/timeframe.
"""

routes = [
    {
        'exchange': 'Binance Perpetual Futures',
        'symbol': 'ETH-USDT',
        'timeframe': '1h',
        'strategy': 'AIGridStrategy',
    },
]

# Additional data routes for multi-timeframe strategies
data_routes = [
    {
        'exchange': 'Binance Perpetual Futures',
        'symbol': 'ETH-USDT',
        'timeframe': '4h',
    },
]
