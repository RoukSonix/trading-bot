"""
Jesse configuration for jesse-bot.

This config is used by Jesse framework for backtesting and live trading.
"""

# Exchange configuration
exchanges = {
    'Binance Perpetual Futures': {
        'fee': 0.0004,  # 0.04% maker fee
        'type': 'futures',
        'futures_leverage_mode': 'cross',
        'futures_leverage': 1,  # 1x leverage
        'balance': 10_000,  # Initial balance in USDT
    },
    'Binance Spot': {
        'fee': 0.001,
        'type': 'spot',
        'balance': 10_000,
    },
}

# Data configuration
data = {
    'warmup_candles_num': 240,  # Warmup candles for indicators
}

# Optimization settings
optimization = {
    'objective_function': 'sharpe',  # sharpe, calmar, sortino, omega
    'trials': 200,
    'best_candidates_count': 20,
    'cpu_cores': 8,  # Use 8 of 16 available cores
}

# Logging settings
logging = {
    'strategy_execution': True,
    'order_submission': True,
    'order_execution': True,
    'position_opened': True,
    'position_closed': True,
}
