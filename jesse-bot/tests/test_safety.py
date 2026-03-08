"""
Tests for SafetyManager — live trading safety mechanisms.

Tests all safety check methods, edge cases, trade logging,
emergency stop file detection, and the combined run_all_checks.
"""

import json
import os
import tempfile

import pytest

from safety import SafetyManager


@pytest.fixture
def sm():
    """SafetyManager instance."""
    return SafetyManager()


# ── check_max_position_size ──────────────────────────────────────────


class TestCheckMaxPositionSize:
    """Tests for SafetyManager.check_max_position_size."""

    def test_within_limit(self, sm):
        """Position value 5% of balance should pass at 10% limit."""
        assert sm.check_max_position_size(qty=0.05, price=100000, balance=10000, max_pct=10) is True

    def test_at_exact_limit(self, sm):
        """Position value exactly at limit should pass."""
        # 10% of 10000 = 1000; qty * price = 0.01 * 100000 = 1000
        assert sm.check_max_position_size(qty=0.01, price=100000, balance=10000, max_pct=10) is True

    def test_exceeds_limit(self, sm):
        """Position value exceeding limit should fail."""
        # 20% of 10000 = 2000; qty * price = 0.02 * 100000 = 2000 > 1000 (10%)
        assert sm.check_max_position_size(qty=0.02, price=100000, balance=10000, max_pct=10) is False

    def test_zero_balance(self, sm):
        """Zero balance should always fail."""
        assert sm.check_max_position_size(qty=0.01, price=100000, balance=0, max_pct=10) is False

    def test_negative_balance(self, sm):
        """Negative balance should always fail."""
        assert sm.check_max_position_size(qty=0.01, price=100000, balance=-1000, max_pct=10) is False

    def test_zero_qty(self, sm):
        """Zero quantity should fail."""
        assert sm.check_max_position_size(qty=0, price=100000, balance=10000, max_pct=10) is False

    def test_negative_qty(self, sm):
        """Negative quantity should fail (uses abs internally but qty<=0 check)."""
        assert sm.check_max_position_size(qty=-0.01, price=100000, balance=10000, max_pct=10) is False

    def test_zero_price(self, sm):
        """Zero price should fail."""
        assert sm.check_max_position_size(qty=0.01, price=0, balance=10000, max_pct=10) is False

    def test_very_small_position(self, sm):
        """Tiny position should always pass."""
        assert sm.check_max_position_size(qty=0.00001, price=100000, balance=10000, max_pct=10) is True

    def test_100_percent_limit(self, sm):
        """100% limit allows full balance position."""
        assert sm.check_max_position_size(qty=0.1, price=100000, balance=10000, max_pct=100) is True

    def test_1_percent_limit(self, sm):
        """Very tight 1% limit."""
        # 1% of 10000 = 100; 0.001 * 100000 = 100
        assert sm.check_max_position_size(qty=0.001, price=100000, balance=10000, max_pct=1) is True
        assert sm.check_max_position_size(qty=0.002, price=100000, balance=10000, max_pct=1) is False


# ── check_daily_loss_limit ───────────────────────────────────────────


class TestCheckDailyLossLimit:
    """Tests for SafetyManager.check_daily_loss_limit."""

    def test_no_loss(self, sm):
        """Zero PnL should pass."""
        assert sm.check_daily_loss_limit(current_pnl=0, limit_pct=5, starting_balance=10000) is True

    def test_profit(self, sm):
        """Positive PnL should always pass."""
        assert sm.check_daily_loss_limit(current_pnl=500, limit_pct=5, starting_balance=10000) is True

    def test_small_loss_within_limit(self, sm):
        """Small loss within limit should pass."""
        # -200 / 10000 = 2% < 5%
        assert sm.check_daily_loss_limit(current_pnl=-200, limit_pct=5, starting_balance=10000) is True

    def test_loss_at_limit(self, sm):
        """Loss exactly at limit should fail (uses strict <)."""
        # -500 / 10000 = 5% = 5% — not strictly less than
        assert sm.check_daily_loss_limit(current_pnl=-500, limit_pct=5, starting_balance=10000) is False

    def test_loss_exceeds_limit(self, sm):
        """Loss exceeding limit should fail."""
        assert sm.check_daily_loss_limit(current_pnl=-600, limit_pct=5, starting_balance=10000) is False

    def test_zero_limit(self, sm):
        """Zero limit should always fail."""
        assert sm.check_daily_loss_limit(current_pnl=0, limit_pct=0, starting_balance=10000) is False

    def test_absolute_mode(self, sm):
        """When starting_balance=0, uses absolute pnl check."""
        assert sm.check_daily_loss_limit(current_pnl=-3, limit_pct=5, starting_balance=0) is True
        assert sm.check_daily_loss_limit(current_pnl=-6, limit_pct=5, starting_balance=0) is False

    def test_large_starting_balance(self, sm):
        """Large balance makes same absolute loss a smaller %."""
        # -500 / 100000 = 0.5% < 5%
        assert sm.check_daily_loss_limit(current_pnl=-500, limit_pct=5, starting_balance=100000) is True


# ── check_max_drawdown ───────────────────────────────────────────────


class TestCheckMaxDrawdown:
    """Tests for SafetyManager.check_max_drawdown."""

    def test_no_drawdown(self, sm):
        """Current = peak should pass."""
        assert sm.check_max_drawdown(peak_equity=10000, current_equity=10000, max_dd_pct=10) is True

    def test_above_peak(self, sm):
        """Current > peak (new high) should pass."""
        assert sm.check_max_drawdown(peak_equity=10000, current_equity=11000, max_dd_pct=10) is True

    def test_small_drawdown(self, sm):
        """5% drawdown within 10% limit should pass."""
        assert sm.check_max_drawdown(peak_equity=10000, current_equity=9500, max_dd_pct=10) is True

    def test_drawdown_at_limit(self, sm):
        """Drawdown exactly at limit should fail (uses strict <)."""
        assert sm.check_max_drawdown(peak_equity=10000, current_equity=9000, max_dd_pct=10) is False

    def test_drawdown_exceeds_limit(self, sm):
        """Drawdown exceeding limit should fail."""
        assert sm.check_max_drawdown(peak_equity=10000, current_equity=8000, max_dd_pct=10) is False

    def test_zero_peak(self, sm):
        """Zero peak equity should fail."""
        assert sm.check_max_drawdown(peak_equity=0, current_equity=1000, max_dd_pct=10) is False

    def test_negative_peak(self, sm):
        """Negative peak equity should fail."""
        assert sm.check_max_drawdown(peak_equity=-1000, current_equity=500, max_dd_pct=10) is False

    def test_very_tight_limit(self, sm):
        """1% max drawdown is very tight."""
        assert sm.check_max_drawdown(peak_equity=10000, current_equity=9950, max_dd_pct=1) is True
        assert sm.check_max_drawdown(peak_equity=10000, current_equity=9890, max_dd_pct=1) is False

    def test_large_drawdown_50pct(self, sm):
        """50% drawdown."""
        assert sm.check_max_drawdown(peak_equity=10000, current_equity=5000, max_dd_pct=50) is False
        assert sm.check_max_drawdown(peak_equity=10000, current_equity=5100, max_dd_pct=50) is True


# ── emergency_stop_check ─────────────────────────────────────────────


class TestEmergencyStopCheck:
    """Tests for SafetyManager.emergency_stop_check."""

    def test_no_stop_file(self, sm, tmp_path):
        """Should return False when stop file doesn't exist."""
        stop_file = str(tmp_path / 'EMERGENCY_STOP')
        assert sm.emergency_stop_check(stop_file) is False

    def test_stop_file_exists(self, sm, tmp_path):
        """Should return True when stop file exists."""
        stop_file = tmp_path / 'EMERGENCY_STOP'
        stop_file.touch()
        assert sm.emergency_stop_check(str(stop_file)) is True

    def test_stop_file_with_content(self, sm, tmp_path):
        """Should return True even when file has content."""
        stop_file = tmp_path / 'EMERGENCY_STOP'
        stop_file.write_text("Emergency: market crash detected")
        assert sm.emergency_stop_check(str(stop_file)) is True

    def test_custom_stop_file_name(self, sm, tmp_path):
        """Should work with custom stop file name."""
        stop_file = tmp_path / 'HALT_TRADING'
        stop_file.touch()
        assert sm.emergency_stop_check(str(stop_file)) is True
        assert sm.emergency_stop_check(str(tmp_path / 'NOPE')) is False


# ── log_trade ────────────────────────────────────────────────────────


class TestLogTrade:
    """Tests for SafetyManager.log_trade."""

    def test_log_creates_file(self, sm, tmp_path):
        """Should create log file if it doesn't exist."""
        log_file = str(tmp_path / 'trades.log')
        sm.log_trade({'symbol': 'BTC-USDT', 'side': 'long', 'qty': 0.01}, log_file)
        assert os.path.exists(log_file)

    def test_log_writes_json(self, sm, tmp_path):
        """Should write valid JSON line."""
        log_file = str(tmp_path / 'trades.log')
        sm.log_trade({'symbol': 'BTC-USDT', 'side': 'long', 'qty': 0.01}, log_file)

        with open(log_file) as f:
            line = f.readline().strip()
            data = json.loads(line)

        assert data['symbol'] == 'BTC-USDT'
        assert data['side'] == 'long'
        assert data['qty'] == 0.01
        assert 'timestamp' in data

    def test_log_appends(self, sm, tmp_path):
        """Should append multiple trades."""
        log_file = str(tmp_path / 'trades.log')
        sm.log_trade({'trade': 1}, log_file)
        sm.log_trade({'trade': 2}, log_file)
        sm.log_trade({'trade': 3}, log_file)

        with open(log_file) as f:
            lines = f.readlines()

        assert len(lines) == 3
        assert json.loads(lines[0])['trade'] == 1
        assert json.loads(lines[2])['trade'] == 3

    def test_log_includes_timestamp(self, sm, tmp_path):
        """Should include ISO format UTC timestamp."""
        log_file = str(tmp_path / 'trades.log')
        sm.log_trade({'test': True}, log_file)

        with open(log_file) as f:
            data = json.loads(f.readline())

        # Should be ISO format with timezone
        assert 'T' in data['timestamp']
        assert '+' in data['timestamp'] or 'Z' in data['timestamp']

    def test_log_preserves_all_fields(self, sm, tmp_path):
        """Should preserve all trade_info fields."""
        log_file = str(tmp_path / 'trades.log')
        trade = {
            'symbol': 'ETH-USDT',
            'side': 'short',
            'entry_price': 3500.0,
            'exit_price': 3400.0,
            'qty': 1.5,
            'pnl': 150.0,
            'pnl_pct': 4.29,
        }
        sm.log_trade(trade, log_file)

        with open(log_file) as f:
            data = json.loads(f.readline())

        for key, val in trade.items():
            assert data[key] == val


# ── run_all_checks ───────────────────────────────────────────────────


class TestRunAllChecks:
    """Tests for SafetyManager.run_all_checks."""

    def test_all_pass(self, sm, tmp_path):
        """All checks pass with safe parameters."""
        result = sm.run_all_checks(
            qty=0.01, price=100000, balance=10000,
            current_pnl=0, peak_equity=10000, current_equity=10000,
            starting_balance=10000,
            stop_file=str(tmp_path / 'NO_SUCH_FILE'),
        )
        assert result['all_ok'] is True
        assert result['position_size_ok'] is True
        assert result['daily_loss_ok'] is True
        assert result['drawdown_ok'] is True
        assert result['emergency_stop'] is False

    def test_position_too_large(self, sm, tmp_path):
        """Should fail when position size exceeds limit."""
        result = sm.run_all_checks(
            qty=0.05, price=100000, balance=10000,
            current_pnl=0, peak_equity=10000, current_equity=10000,
            starting_balance=10000, max_position_pct=10,
            stop_file=str(tmp_path / 'NO'),
        )
        assert result['all_ok'] is False
        assert result['position_size_ok'] is False

    def test_daily_loss_exceeded(self, sm, tmp_path):
        """Should fail when daily loss exceeds limit."""
        result = sm.run_all_checks(
            qty=0.01, price=100000, balance=10000,
            current_pnl=-600, peak_equity=10000, current_equity=10000,
            starting_balance=10000, daily_loss_limit_pct=5,
            stop_file=str(tmp_path / 'NO'),
        )
        assert result['all_ok'] is False
        assert result['daily_loss_ok'] is False

    def test_drawdown_exceeded(self, sm, tmp_path):
        """Should fail when drawdown exceeds limit."""
        result = sm.run_all_checks(
            qty=0.01, price=100000, balance=10000,
            current_pnl=0, peak_equity=12000, current_equity=10000,
            starting_balance=10000, max_drawdown_pct=10,
            stop_file=str(tmp_path / 'NO'),
        )
        assert result['all_ok'] is False
        assert result['drawdown_ok'] is False

    def test_emergency_stop(self, sm, tmp_path):
        """Should fail when emergency stop file exists."""
        stop_file = tmp_path / 'STOP'
        stop_file.touch()
        result = sm.run_all_checks(
            qty=0.01, price=100000, balance=10000,
            current_pnl=0, peak_equity=10000, current_equity=10000,
            starting_balance=10000,
            stop_file=str(stop_file),
        )
        assert result['all_ok'] is False
        assert result['emergency_stop'] is True

    def test_multiple_failures(self, sm, tmp_path):
        """Multiple checks can fail simultaneously."""
        stop_file = tmp_path / 'STOP'
        stop_file.touch()
        result = sm.run_all_checks(
            qty=0.05, price=100000, balance=10000,
            current_pnl=-1000, peak_equity=15000, current_equity=10000,
            starting_balance=10000, max_position_pct=10,
            daily_loss_limit_pct=5, max_drawdown_pct=10,
            stop_file=str(stop_file),
        )
        assert result['all_ok'] is False
        assert result['position_size_ok'] is False
        assert result['daily_loss_ok'] is False
        assert result['drawdown_ok'] is False
        assert result['emergency_stop'] is True

    def test_custom_limits(self, sm, tmp_path):
        """Should respect custom limit values."""
        # Tight limits
        result = sm.run_all_checks(
            qty=0.005, price=100000, balance=10000,
            current_pnl=-50, peak_equity=10000, current_equity=9900,
            starting_balance=10000,
            max_position_pct=5, daily_loss_limit_pct=1, max_drawdown_pct=2,
            stop_file=str(tmp_path / 'NO'),
        )
        assert result['position_size_ok'] is True  # 500/10000 = 5%, at limit
        assert result['daily_loss_ok'] is True  # 50/10000 = 0.5% < 1%
        assert result['drawdown_ok'] is True  # 100/10000 = 1% < 2%
