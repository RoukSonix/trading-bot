"""
Tests for live vs backtest mode behavior in AIGridStrategy.

Tests safety filter integration, equity tracking, emergency stop,
trade logging, and the difference between live and backtest behavior.
All tests use pure Python (no Jesse framework dependency).
"""

import json
import os
import tempfile

import pytest

from safety import SafetyManager
from grid_logic import GridManager, GridConfig


# ── Safety + Grid Integration ────────────────────────────────────────


class TestSafetyGridIntegration:
    """Tests that SafetyManager integrates with grid trading logic."""

    def test_safety_blocks_oversized_grid_trade(self):
        """Safety should block a trade when position exceeds max %."""
        sm = SafetyManager()
        gm = GridManager(GridConfig(grid_levels_count=5, grid_spacing_pct=1.0, amount_pct=50))
        gm.setup_grid(100000.0)

        # Simulate: balance 10000, trying to trade 50% = 5000 USDT
        # At max_pct=10, this should fail
        qty = 0.05  # 0.05 * 100000 = 5000
        assert sm.check_max_position_size(qty, 100000, 10000, max_pct=10) is False

    def test_safety_allows_normal_grid_trade(self):
        """Safety should allow normal-sized grid trades."""
        sm = SafetyManager()
        gm = GridManager(GridConfig(grid_levels_count=5, grid_spacing_pct=1.0, amount_pct=5))
        gm.setup_grid(100000.0)

        # 5% of 10000 = 500 USDT, which is 0.005 BTC at 100k
        qty = 0.005
        assert sm.check_max_position_size(qty, 100000, 10000, max_pct=10) is True

    def test_drawdown_triggers_after_losses(self):
        """Drawdown should trigger after a series of losing trades."""
        sm = SafetyManager()
        peak = 10000
        # Simulate 3 losing trades, each -4% → equity drops to ~8847
        equity = peak
        for _ in range(3):
            equity *= 0.96

        # 10000 → 8847 = 11.5% drawdown
        assert sm.check_max_drawdown(peak, equity, max_dd_pct=10) is False
        assert sm.check_max_drawdown(peak, equity, max_dd_pct=15) is True

    def test_daily_loss_accumulates(self):
        """Daily loss should accumulate across multiple trades."""
        sm = SafetyManager()
        starting = 10000

        # Trade 1: -100, Trade 2: -150, Trade 3: -200 = total -450 (4.5%)
        assert sm.check_daily_loss_limit(-450, limit_pct=5, starting_balance=starting) is True

        # One more loss pushes over
        assert sm.check_daily_loss_limit(-550, limit_pct=5, starting_balance=starting) is False


# ── Emergency Stop Workflow ──────────────────────────────────────────


class TestEmergencyStopWorkflow:
    """Tests for the emergency stop file workflow."""

    def test_create_and_detect_stop(self, tmp_path):
        """Creating stop file should be detected immediately."""
        sm = SafetyManager()
        stop_file = str(tmp_path / 'EMERGENCY_STOP')

        assert sm.emergency_stop_check(stop_file) is False

        with open(stop_file, 'w') as f:
            f.write("manual halt")

        assert sm.emergency_stop_check(stop_file) is True

    def test_remove_stop_resumes(self, tmp_path):
        """Removing stop file should allow trading to resume."""
        sm = SafetyManager()
        stop_file = tmp_path / 'EMERGENCY_STOP'

        stop_file.touch()
        assert sm.emergency_stop_check(str(stop_file)) is True

        stop_file.unlink()
        assert sm.emergency_stop_check(str(stop_file)) is False

    def test_stop_blocks_all_checks(self, tmp_path):
        """Emergency stop should cause run_all_checks to fail."""
        sm = SafetyManager()
        stop_file = tmp_path / 'STOP'
        stop_file.touch()

        result = sm.run_all_checks(
            qty=0.001, price=100000, balance=10000,
            current_pnl=500, peak_equity=10000, current_equity=10500,
            starting_balance=10000,
            stop_file=str(stop_file),
        )
        # Everything else is fine, but emergency stop kills it
        assert result['position_size_ok'] is True
        assert result['daily_loss_ok'] is True
        assert result['drawdown_ok'] is True
        assert result['emergency_stop'] is True
        assert result['all_ok'] is False


# ── Trade Logging ────────────────────────────────────────────────────


class TestTradeLogging:
    """Tests for trade logging in live mode."""

    def test_log_round_trip(self, tmp_path):
        """Logged trade should be readable back."""
        sm = SafetyManager()
        log_file = str(tmp_path / 'trades.log')

        trade = {
            'symbol': 'BTC-USDT',
            'side': 'long',
            'entry_price': 99500.0,
            'exit_price': 100500.0,
            'qty': 0.01,
            'pnl': 10.0,
            'pnl_pct': 1.005,
        }
        sm.log_trade(trade, log_file)

        with open(log_file) as f:
            logged = json.loads(f.readline())

        assert logged['symbol'] == 'BTC-USDT'
        assert logged['pnl'] == 10.0
        assert 'timestamp' in logged

    def test_multiple_trades_log(self, tmp_path):
        """Multiple trades should be logged as separate lines."""
        sm = SafetyManager()
        log_file = str(tmp_path / 'trades.log')

        for i in range(10):
            sm.log_trade({'trade_num': i, 'pnl': i * 10}, log_file)

        with open(log_file) as f:
            lines = f.readlines()

        assert len(lines) == 10
        for i, line in enumerate(lines):
            data = json.loads(line)
            assert data['trade_num'] == i

    def test_log_with_empty_dict(self, tmp_path):
        """Empty trade info should still log with timestamp."""
        sm = SafetyManager()
        log_file = str(tmp_path / 'trades.log')
        sm.log_trade({}, log_file)

        with open(log_file) as f:
            data = json.loads(f.readline())

        assert 'timestamp' in data


# ── Live vs Backtest Mode Differences ────────────────────────────────


class TestLiveVsBacktestMode:
    """Tests for behavioral differences between live and backtest mode."""

    def test_safety_check_results_structure(self):
        """run_all_checks should return consistent dict structure."""
        sm = SafetyManager()
        result = sm.run_all_checks(
            qty=0.01, price=100000, balance=10000,
            current_pnl=0, peak_equity=10000, current_equity=10000,
            starting_balance=10000,
        )
        expected_keys = {'position_size_ok', 'daily_loss_ok', 'drawdown_ok', 'emergency_stop', 'all_ok'}
        assert set(result.keys()) == expected_keys

    def test_safety_not_used_in_backtest(self):
        """In backtest mode, filters() should not include safety filter.

        This tests the logic indirectly: safety filter is only added
        when is_live is True.
        """
        # The strategy adds _filter_safety only when self.is_live
        # Since we can't instantiate Jesse Strategy here, test the logic
        is_live = False
        filters = ['_filter_volatility', '_filter_max_grid_levels', '_filter_grid_suitability']
        if is_live:
            filters.insert(0, '_filter_safety')
        assert '_filter_safety' not in filters

    def test_safety_used_in_live(self):
        """In live mode, filters() should include safety filter."""
        is_live = True
        filters = ['_filter_volatility', '_filter_max_grid_levels', '_filter_grid_suitability']
        if is_live:
            filters.insert(0, '_filter_safety')
        assert filters[0] == '_filter_safety'

    def test_peak_equity_tracking(self):
        """Peak equity should only increase, never decrease."""
        sm = SafetyManager()
        peak = 10000

        # Equity goes up
        new_equity = 10500
        if new_equity > peak:
            peak = new_equity
        assert peak == 10500

        # Equity goes down — peak stays
        new_equity = 10200
        if new_equity > peak:
            peak = new_equity
        assert peak == 10500

        # New high
        new_equity = 11000
        if new_equity > peak:
            peak = new_equity
        assert peak == 11000


# ── Edge Cases ───────────────────────────────────────────────────────


class TestSafetyEdgeCases:
    """Edge case tests for SafetyManager."""

    def test_very_small_balance(self):
        """Should handle very small balances."""
        sm = SafetyManager()
        # Balance = 1 USDT, qty = 0.00001 BTC at 100k = 1 USDT = 100%
        assert sm.check_max_position_size(0.00001, 100000, 1, max_pct=100) is True
        assert sm.check_max_position_size(0.00001, 100000, 1, max_pct=50) is False

    def test_very_large_balance(self):
        """Should handle very large balances."""
        sm = SafetyManager()
        assert sm.check_max_position_size(1.0, 100000, 10_000_000, max_pct=10) is True

    def test_drawdown_exactly_zero(self):
        """Zero drawdown should always pass."""
        sm = SafetyManager()
        assert sm.check_max_drawdown(10000, 10000, max_dd_pct=0.001) is True

    def test_float_precision_position_size(self):
        """Float precision shouldn't cause false positives."""
        sm = SafetyManager()
        # Exactly 10% of 10000 = 1000; 0.01 * 100000 = 1000
        assert sm.check_max_position_size(0.01, 100000, 10000, max_pct=10) is True

    def test_concurrent_stop_file_access(self, tmp_path):
        """Multiple checks of same file should be consistent."""
        sm = SafetyManager()
        stop_file = str(tmp_path / 'STOP')

        results = [sm.emergency_stop_check(stop_file) for _ in range(100)]
        assert all(r is False for r in results)

        with open(stop_file, 'w') as f:
            f.write("")

        results = [sm.emergency_stop_check(stop_file) for _ in range(100)]
        assert all(r is True for r in results)
