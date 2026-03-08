"""
SafetyManager — Live trading safety mechanisms.

Pure Python, no Jesse dependency. Checks position sizes, daily loss limits,
drawdown thresholds, and emergency stop files before allowing trades.
"""

import json
import os
from datetime import datetime, timezone


class SafetyManager:
    """Safety checks for live trading.

    All methods are pure functions (except log_trade and emergency_stop_check
    which do file I/O). No exchange or framework dependency.
    """

    def check_max_position_size(
        self,
        qty: float,
        price: float,
        balance: float,
        max_pct: float = 10.0,
    ) -> bool:
        """Check if position size is within allowed percentage of balance.

        Args:
            qty: Order quantity (units of base asset).
            price: Current price per unit.
            balance: Account balance in quote currency.
            max_pct: Maximum position size as % of balance.

        Returns:
            True if position is within limit, False if it exceeds.
        """
        if balance <= 0 or price <= 0 or qty <= 0:
            return False

        position_value = abs(qty) * price
        max_value = balance * (max_pct / 100.0)
        return position_value <= max_value

    def check_daily_loss_limit(
        self,
        current_pnl: float,
        limit_pct: float = 5.0,
        starting_balance: float = 0.0,
    ) -> bool:
        """Check if daily PnL is within the loss limit.

        Args:
            current_pnl: Current daily PnL (negative = loss).
            limit_pct: Maximum allowed daily loss as % of starting balance.
            starting_balance: Balance at start of day. If 0, uses absolute pnl.

        Returns:
            True if within limit (OK to trade), False if limit breached.
        """
        if limit_pct <= 0:
            return False

        if starting_balance > 0:
            loss_pct = abs(min(current_pnl, 0)) / starting_balance * 100
            return loss_pct < limit_pct
        else:
            # Absolute mode: just check if pnl is not excessively negative
            return current_pnl > -(limit_pct)

    def check_max_drawdown(
        self,
        peak_equity: float,
        current_equity: float,
        max_dd_pct: float = 10.0,
    ) -> bool:
        """Check if drawdown from peak is within limit.

        Args:
            peak_equity: Highest account equity observed.
            current_equity: Current account equity.
            max_dd_pct: Maximum allowed drawdown as % of peak.

        Returns:
            True if within limit, False if max drawdown breached.
        """
        if peak_equity <= 0:
            return False

        if current_equity >= peak_equity:
            return True

        drawdown_pct = (peak_equity - current_equity) / peak_equity * 100
        return drawdown_pct < max_dd_pct

    def emergency_stop_check(self, stop_file: str = 'EMERGENCY_STOP') -> bool:
        """Check if emergency stop file exists.

        Create this file to immediately halt all trading.

        Args:
            stop_file: Path to the emergency stop file.

        Returns:
            True if emergency stop is triggered (file exists), False otherwise.
        """
        return os.path.exists(stop_file)

    def log_trade(self, trade_info: dict, log_file: str = 'trades.log') -> None:
        """Append trade information to a log file.

        Args:
            trade_info: Dict with trade details (symbol, side, qty, price, etc.).
            log_file: Path to the trade log file.
        """
        entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            **trade_info,
        }

        with open(log_file, 'a') as f:
            f.write(json.dumps(entry) + '\n')

    def run_all_checks(
        self,
        qty: float,
        price: float,
        balance: float,
        current_pnl: float,
        peak_equity: float,
        current_equity: float,
        starting_balance: float = 0.0,
        max_position_pct: float = 10.0,
        daily_loss_limit_pct: float = 5.0,
        max_drawdown_pct: float = 10.0,
        stop_file: str = 'EMERGENCY_STOP',
    ) -> dict:
        """Run all safety checks and return results.

        Args:
            qty: Order quantity.
            price: Current price.
            balance: Current balance.
            current_pnl: Daily PnL.
            peak_equity: Peak equity.
            current_equity: Current equity.
            starting_balance: Balance at start of day.
            max_position_pct: Max position size %.
            daily_loss_limit_pct: Max daily loss %.
            max_drawdown_pct: Max drawdown %.
            stop_file: Emergency stop file path.

        Returns:
            Dict with check results and overall pass/fail.
        """
        results = {
            'position_size_ok': self.check_max_position_size(
                qty, price, balance, max_position_pct
            ),
            'daily_loss_ok': self.check_daily_loss_limit(
                current_pnl, daily_loss_limit_pct, starting_balance
            ),
            'drawdown_ok': self.check_max_drawdown(
                peak_equity, current_equity, max_drawdown_pct
            ),
            'emergency_stop': self.emergency_stop_check(stop_file),
        }
        results['all_ok'] = (
            results['position_size_ok']
            and results['daily_loss_ok']
            and results['drawdown_ok']
            and not results['emergency_stop']
        )
        return results
