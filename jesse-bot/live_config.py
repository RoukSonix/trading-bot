"""
Jesse live mode configuration.

Loads exchange credentials and risk limits from environment variables.
Used by jesse-live Docker service for paper/live trading on Binance Testnet.
"""

import os


def get_exchange_config() -> dict:
    """Build exchange config from environment variables.

    Returns:
        Dict compatible with Jesse's exchange configuration.
    """
    api_key = os.environ.get('BINANCE_API_KEY', '')
    api_secret = os.environ.get('BINANCE_API_SECRET', '')
    exchange_type = os.environ.get('JESSE_EXCHANGE_TYPE', 'futures')
    leverage = int(os.environ.get('JESSE_LEVERAGE', '1'))
    leverage_mode = os.environ.get('JESSE_LEVERAGE_MODE', 'cross')
    starting_balance = float(os.environ.get('JESSE_STARTING_BALANCE', '10000'))

    config = {
        'Binance Perpetual Futures': {
            'fee': 0.0004,
            'type': 'futures',
            'futures_leverage_mode': leverage_mode,
            'futures_leverage': leverage,
            'balance': starting_balance,
            'api_key': api_key,
            'api_secret': api_secret,
        },
    }

    if exchange_type == 'spot':
        config['Binance Spot'] = {
            'fee': 0.001,
            'type': 'spot',
            'balance': starting_balance,
            'api_key': api_key,
            'api_secret': api_secret,
        }

    return config


def get_risk_config() -> dict:
    """Load risk management limits from environment variables.

    Returns:
        Dict with risk limit settings.
    """
    return {
        'max_position_pct': float(os.environ.get('RISK_MAX_POSITION_PCT', '10')),
        'daily_loss_limit_pct': float(os.environ.get('RISK_DAILY_LOSS_LIMIT_PCT', '5')),
        'max_drawdown_pct': float(os.environ.get('RISK_MAX_DRAWDOWN_PCT', '10')),
        'emergency_stop_file': os.environ.get('EMERGENCY_STOP_FILE', 'EMERGENCY_STOP'),
    }


def get_notification_config() -> dict:
    """Load notification settings from environment variables.

    Returns:
        Dict with notification channel settings.
    """
    return {
        'discord_webhook_url': os.environ.get('DISCORD_WEBHOOK_URL', ''),
        'telegram_bot_token': os.environ.get('TELEGRAM_BOT_TOKEN', ''),
        'telegram_chat_id': os.environ.get('TELEGRAM_CHAT_ID', ''),
        'alerts_enabled': os.environ.get('ALERTS_ENABLED', 'true').lower() == 'true',
    }


def get_trading_mode() -> str:
    """Get current trading mode.

    Returns:
        'paper' or 'live'. Defaults to 'paper' for safety.
    """
    return os.environ.get('TRADING_MODE', 'paper')


def is_testnet() -> bool:
    """Check if running on testnet.

    Returns:
        True if BINANCE_TESTNET is set to 'true' or '1'.
    """
    val = os.environ.get('BINANCE_TESTNET', 'true').lower()
    return val in ('true', '1', 'yes')


def validate_config() -> list[str]:
    """Validate that all required environment variables are set.

    Returns:
        List of error messages. Empty list means all OK.
    """
    errors = []

    api_key = os.environ.get('BINANCE_API_KEY', '')
    api_secret = os.environ.get('BINANCE_API_SECRET', '')

    if not api_key or api_key == 'your_api_key_here':
        errors.append('BINANCE_API_KEY is not set or still has placeholder value')

    if not api_secret or api_secret == 'your_api_secret_here':
        errors.append('BINANCE_API_SECRET is not set or still has placeholder value')

    trading_mode = get_trading_mode()
    if trading_mode not in ('paper', 'live'):
        errors.append(f'TRADING_MODE must be "paper" or "live", got "{trading_mode}"')

    # Warn if live mode but not testnet
    if trading_mode == 'live' and not is_testnet():
        errors.append(
            'DANGER: TRADING_MODE=live with BINANCE_TESTNET!=true. '
            'This would use REAL money. Set BINANCE_TESTNET=true for safety.'
        )

    # Validate risk limits are reasonable
    risk = get_risk_config()
    if risk['max_position_pct'] > 50:
        errors.append(f'RISK_MAX_POSITION_PCT={risk["max_position_pct"]} is dangerously high (>50%)')
    if risk['daily_loss_limit_pct'] > 20:
        errors.append(f'RISK_DAILY_LOSS_LIMIT_PCT={risk["daily_loss_limit_pct"]} is dangerously high (>20%)')
    if risk['max_drawdown_pct'] > 30:
        errors.append(f'RISK_MAX_DRAWDOWN_PCT={risk["max_drawdown_pct"]} is dangerously high (>30%)')

    return errors
