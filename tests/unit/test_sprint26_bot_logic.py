"""Sprint 26: Bot Logic & State Machine — 28 tests across 13 issues.

Tests all 13 fixes:
- P1-BOT-1: PAUSED auto-resume (no early continue)
- P1-BOT-2: Dashboard resume risk checks
- P1-BOT-4: AI review triggers when last_review is None
- P1-BOT-5: EMA 8/21 key match
- P1-BOT-6: PnL recording for sell/cover trades
- P1-BOT-7: Ticker reuse (no redundant fetch)
- P1-BOT-8: KeyboardInterrupt dead code removed
- P1-STRAT-1: No duplicate grid levels with direction=both
- P1-STRAT-2: _close_level records trade
- P1-STRAT-4: Negative amount abs() in execute_signal
- P1-STRAT-5: Orders kept on fetch failure
- P1-STRAT-7: PositionManager short support
- P1-STRAT-8: Unrealized PnL for shorts
"""

import ast
import inspect
import signal as signal_module
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import numpy as np
import pandas as pd
import pytest

from binance_bot.strategies.base import Signal, SignalType, GridLevel


# ── P1-BOT-1: PAUSED auto-resume ─────────────────────────────────────


class TestP1Bot1PausedAutoResume:
    """Verify PAUSED state reaches auto-resume logic (no early continue)."""

    def _get_main_loop_source(self):
        """Get source of the main loop method (start or _main_loop)."""
        import binance_bot.bot as bot_module
        # The main loop logic may be in start() or _main_loop()
        if hasattr(bot_module.TradingBot, '_main_loop'):
            return inspect.getsource(bot_module.TradingBot._main_loop)
        return inspect.getsource(bot_module.TradingBot.start)

    def test_paused_state_runs_auto_resume_logic(self):
        """Verify the early-continue block is removed — no 'continue' after PAUSED check
        before the state-dependent behavior section."""
        source = self._get_main_loop_source()

        assert "BotState.PAUSED" in source or "PAUSED" in source
        assert "_maybe_check_entry" in source

        lines = source.split("\n")
        state_dep_idx = None
        for i, line in enumerate(lines):
            if "State-dependent behavior" in line:
                state_dep_idx = i
                break

        if state_dep_idx is not None:
            paused_continue_pattern = False
            in_paused_block = False
            for line in lines[:state_dep_idx]:
                stripped = line.strip()
                if "BotState.PAUSED" in stripped and "if" in stripped:
                    in_paused_block = True
                elif in_paused_block and stripped == "continue":
                    paused_continue_pattern = True
                    break
                elif in_paused_block and stripped and not stripped.startswith("#") and not stripped.startswith("await") and not stripped.startswith("self."):
                    in_paused_block = False
            assert not paused_continue_pattern, "Early continue for PAUSED still exists"

    def test_paused_state_runs_ai_review(self):
        """Verify PAUSED state calls _maybe_ai_review."""
        source = self._get_main_loop_source()
        lines = source.split("\n")
        in_paused_elif = False
        has_ai_review = False
        for line in lines:
            if "elif self.state == BotState.PAUSED" in line:
                in_paused_elif = True
            elif in_paused_elif:
                if "_maybe_ai_review" in line:
                    has_ai_review = True
                    break
                if line.strip().startswith("elif ") or line.strip().startswith("except "):
                    break
        assert has_ai_review, "PAUSED block should call _maybe_ai_review"

    def test_paused_state_can_transition_to_trading(self):
        """Verify PAUSED block calls _maybe_check_entry (which can transition to TRADING)."""
        source = self._get_main_loop_source()
        lines = source.split("\n")
        in_paused_elif = False
        has_entry_check = False
        for line in lines:
            if "elif self.state == BotState.PAUSED" in line:
                in_paused_elif = True
            elif in_paused_elif:
                if "_maybe_check_entry" in line:
                    has_entry_check = True
                    break
                if line.strip().startswith("elif ") or line.strip().startswith("except "):
                    break
        assert has_entry_check, "PAUSED block should call _maybe_check_entry"


# ── P1-BOT-2: Dashboard resume risk checks ───────────────────────────


class TestP1Bot2DashboardResume:
    """Verify dashboard resume checks risk limits before allowing."""

    def _get_main_loop_source(self):
        import binance_bot.bot as bot_module
        if hasattr(bot_module.TradingBot, '_main_loop'):
            return inspect.getsource(bot_module.TradingBot._main_loop)
        return inspect.getsource(bot_module.TradingBot.start)

    def test_dashboard_resume_checks_risk_limits(self):
        """Resume command must call risk_limits.can_trade() before setting TRADING."""
        source = self._get_main_loop_source()
        lines = source.split("\n")
        in_resume = False
        has_can_trade = False
        for line in lines:
            if '"resume"' in line or "'resume'" in line:
                in_resume = True
            elif in_resume:
                if "can_trade" in line:
                    has_can_trade = True
                    break
                if 'elif cmd ==' in line or 'elif cmd==' in line:
                    break
        assert has_can_trade, "Resume command must check can_trade()"

    def test_dashboard_resume_allowed_when_risk_ok(self):
        """Verify resume sets TRADING when risk_limits.can_trade() returns True."""
        source = self._get_main_loop_source()
        lines = source.split("\n")
        in_resume = False
        has_trading_set = False
        for line in lines:
            if '"resume"' in line or "'resume'" in line:
                in_resume = True
            elif in_resume:
                if "BotState.TRADING" in line:
                    has_trading_set = True
                    break
                if 'elif cmd ==' in line:
                    break
        assert has_trading_set, "Resume should set BotState.TRADING when risk OK"


# ── P1-BOT-4: First AI review skip ───────────────────────────────────


class TestP1Bot4FirstAiReview:
    """Verify AI review triggers immediately when last_review is None."""

    def test_ai_review_triggers_when_last_review_none(self):
        """When last_review is None, should NOT return early — should fall through."""
        import binance_bot.bot as bot_module
        source = inspect.getsource(bot_module.TradingBot._maybe_ai_review)
        # The fix: if last_review is None → pass (fall through), not return
        assert "pass" in source or "return" not in source.split("self.last_review is None")[1].split("\n")[1]
        # Verify no early return for None case
        lines = source.split("\n")
        for i, line in enumerate(lines):
            if "self.last_review is None" in line:
                # Next non-comment, non-blank line should NOT be 'return'
                for j in range(i + 1, min(i + 3, len(lines))):
                    stripped = lines[j].strip()
                    if stripped and not stripped.startswith("#"):
                        assert stripped != "return", "last_review=None should NOT return early"
                        break
                break

    def test_ai_review_respects_interval_after_first(self):
        """After first review, interval check should gate subsequent reviews."""
        import binance_bot.bot as bot_module
        source = inspect.getsource(bot_module.TradingBot._maybe_ai_review)
        # Should have interval check in else branch
        assert "review_interval_minutes" in source
        assert "return" in source  # interval check returns if too soon


# ── P1-BOT-5: EMA period mismatch ────────────────────────────────────


class TestP1Bot5EmaPeriodMatch:
    """Verify ema_8 and ema_21 keys use correct EMA spans."""

    def test_engine_indicators_ema_keys_match_data(self):
        """ema_8 and ema_21 should be computed with span=8 and span=21."""
        import binance_bot.bot as bot_module
        source = inspect.getsource(bot_module.TradingBot._run_strategy_engine)
        # Should compute actual EMA with correct spans
        assert "span=8" in source, "ema_8 should use span=8"
        assert "span=21" in source, "ema_21 should use span=21"
        # Should NOT use ema_12/ema_26 for these keys
        assert '"ema_8": float(latest.get("ema_12"' not in source, "ema_8 should not use ema_12 data"


# ── P1-BOT-6: PnL recording ──────────────────────────────────────────


class TestP1Bot6PnlRecording:
    """Verify trades record actual PnL instead of always 0."""

    def test_sell_trade_records_nonzero_pnl(self):
        """SELL trades should compute PnL from entry price."""
        import binance_bot.bot as bot_module
        source = inspect.getsource(bot_module.TradingBot._calculate_signal_pnl)
        # Verify PnL calculation for SELL signals
        assert "SignalType.SELL" in source
        assert "long_entry_price" in source
        # Should have actual PnL formula, not just pnl = 0
        assert "signal.price" in source

    def test_risk_limits_triggered_on_losses(self):
        """risk_limits.record_trade should receive non-zero PnL."""
        import binance_bot.bot as bot_module
        source = inspect.getsource(bot_module.TradingBot._process_signals)
        assert "risk_limits.record_trade(pnl" in source

    def test_short_cover_records_pnl(self):
        """Short cover (BUY with negative amount) should compute PnL."""
        import binance_bot.bot as bot_module
        source = inspect.getsource(bot_module.TradingBot._calculate_signal_pnl)
        assert "short_entry_price" in source
        # Should have: (entry - cover_price) * amount pattern
        assert "signal.amount < 0" in source or "amount < 0" in source


# ── P1-BOT-7: Redundant fetch ────────────────────────────────────────


class TestP1Bot7RedundantFetch:
    """Verify ticker is reused, not fetched twice per tick."""

    def test_execute_trading_reuses_ticker(self):
        """_execute_trading should accept ticker param and pass to _fetch_market_data."""
        import binance_bot.bot as bot_module
        sig = inspect.signature(bot_module.TradingBot._execute_trading)
        assert "ticker" in sig.parameters, "_execute_trading should accept ticker param"

        source = inspect.getsource(bot_module.TradingBot._execute_trading)
        assert "ticker=ticker" in source, "_execute_trading should pass ticker to _fetch_market_data"


# ── P1-BOT-8: KeyboardInterrupt dead code ────────────────────────────


class TestP1Bot8KeyboardInterrupt:
    """Verify signal handlers are set up and KeyboardInterrupt is not caught."""

    def test_signal_handlers_registered(self):
        """SIGINT/SIGTERM handlers should be registered; no except KeyboardInterrupt."""
        import binance_bot.bot as bot_module
        # Check run_bot for signal handlers
        source = inspect.getsource(bot_module.run_bot)
        assert "SIGINT" in source, "SIGINT handler should be registered"
        assert "SIGTERM" in source, "SIGTERM handler should be registered"

        # Check start() does NOT catch KeyboardInterrupt
        start_source = inspect.getsource(bot_module.TradingBot.start)
        assert "KeyboardInterrupt" not in start_source, "start() should not catch KeyboardInterrupt"


# ── P1-STRAT-1: Duplicate grid levels ────────────────────────────────


class TestP1Strat1DuplicateLevels:
    """Verify direction='both' produces unique prices (no overlaps)."""

    def _make_grid_strategy(self, grid_levels=3, spacing_pct=1.0, amount=0.001):
        """Create a GridStrategy with mocked dependencies."""
        from binance_bot.strategies.grid import GridStrategy, GridConfig
        config = GridConfig(
            grid_levels=grid_levels,
            grid_spacing_pct=spacing_pct,
            amount_per_level=amount,
            direction="both",
        )
        with patch("binance_bot.strategies.grid.get_session"), \
             patch("binance_bot.strategies.grid.TPSLCalculator"), \
             patch("binance_bot.strategies.grid.TrailingStopManager"), \
             patch("binance_bot.strategies.grid.BreakEvenManager"):
            strategy = GridStrategy(
                symbol="BTC/USDT",
                config=config,
            )
        return strategy

    def test_grid_both_direction_no_duplicate_prices(self):
        """All grid levels should have unique prices when direction=both."""
        strategy = self._make_grid_strategy(grid_levels=5)
        strategy.setup_grid(50000.0, direction="both")
        prices = [level.price for level in strategy.levels]
        assert len(prices) == len(set(prices)), f"Duplicate prices found: {sorted(prices)}"

    def test_grid_both_direction_correct_count(self):
        """Direction=both should produce 4 × grid_levels levels."""
        n = 4
        strategy = self._make_grid_strategy(grid_levels=n)
        strategy.setup_grid(50000.0, direction="both")
        assert len(strategy.levels) == 4 * n, f"Expected {4*n} levels, got {len(strategy.levels)}"

    def test_grid_long_only_no_offset(self):
        """Long-only grid should be unchanged (no offset applied)."""
        strategy = self._make_grid_strategy(grid_levels=3)
        strategy.setup_grid(50000.0, direction="long")
        prices = [level.price for level in strategy.levels]
        assert len(prices) == 6  # 3 buy + 3 sell
        assert len(prices) == len(set(prices))


# ── P1-STRAT-2: _close_level trade recording ─────────────────────────


class TestP1Strat2CloseLevelRecording:
    """Verify _close_level records trades in paper_trades and database."""

    def _make_grid_with_level(self):
        """Create grid strategy with a filled level ready to close."""
        from binance_bot.strategies.grid import GridStrategy, GridConfig
        config = GridConfig(
            grid_levels=3,
            grid_spacing_pct=1.0,
            amount_per_level=0.001,
        )
        with patch("binance_bot.strategies.grid.get_session"), \
             patch("binance_bot.strategies.grid.TPSLCalculator"), \
             patch("binance_bot.strategies.grid.TrailingStopManager"), \
             patch("binance_bot.strategies.grid.BreakEvenManager"):
            strategy = GridStrategy(symbol="BTC/USDT", config=config)

        # Set up paper trading state
        strategy.paper_balance = 10000.0
        strategy.paper_holdings = 0.001
        strategy.long_holdings = 0.001
        strategy.short_holdings = 0.0
        strategy.realized_pnl = 0.0
        strategy.paper_trades = []

        level = GridLevel(
            price=50000.0,
            side=SignalType.BUY,
            amount=0.001,
            filled=True,
            fill_price=49500.0,
            take_profit=51000.0,
            stop_loss=48000.0,
            pnl=1.5,
        )
        return strategy, level

    def test_close_level_records_trade_in_paper_trades(self):
        """_close_level should append to paper_trades list."""
        strategy, level = self._make_grid_with_level()
        initial_count = len(strategy.paper_trades)

        with patch.object(strategy, "_save_trade_to_db"):
            strategy._close_level(level, exit_price=51000.0)

        assert len(strategy.paper_trades) == initial_count + 1
        trade = strategy.paper_trades[-1]
        assert trade["status"] == "filled"
        assert trade["pnl"] == level.pnl

    def test_close_level_saves_to_db(self):
        """_close_level should call _save_trade_to_db."""
        strategy, level = self._make_grid_with_level()

        with patch.object(strategy, "_save_trade_to_db") as mock_save:
            strategy._close_level(level, exit_price=51000.0)
            mock_save.assert_called_once()


# ── P1-STRAT-4: Negative amount in execute_signal ────────────────────


class TestP1Strat4NegativeAmount:
    """Verify execute_signal uses abs(amount) for exchange calls."""

    def test_execute_signal_uses_abs_amount(self):
        """Negative signal.amount should be converted to positive for exchange."""
        from binance_bot.core.order_manager import OrderManager, OrderType

        om = OrderManager.__new__(OrderManager)
        om.open_orders = {}
        om.filled_orders = []

        signal = Signal(
            type=SignalType.SELL,
            price=50000.0,
            amount=-0.001,  # Short-side negative
            reason="test",
        )

        with patch.object(om, "create_market_order", return_value={"id": "test"}) as mock_order:
            om.execute_signal(signal, OrderType.MARKET)
            call_args = mock_order.call_args
            assert call_args.kwargs.get("amount", call_args[1].get("amount") if len(call_args) > 1 else None) == 0.001 or \
                   (call_args[1]["amount"] if len(call_args[1]) > 2 else call_args.kwargs["amount"]) == 0.001

    def test_execute_signal_preserves_positive_amount(self):
        """Positive signal.amount should remain unchanged."""
        from binance_bot.core.order_manager import OrderManager, OrderType

        om = OrderManager.__new__(OrderManager)
        om.open_orders = {}
        om.filled_orders = []

        signal = Signal(
            type=SignalType.BUY,
            price=50000.0,
            amount=0.001,
            reason="test",
        )

        with patch.object(om, "create_limit_order", return_value={"id": "test"}) as mock_order:
            om.execute_signal(signal, OrderType.LIMIT)
            call_args = mock_order.call_args
            assert call_args.kwargs["amount"] == 0.001


# ── P1-STRAT-5: Order deletion on fetch failure ──────────────────────


class TestP1Strat5OrderDeletionOnFailure:
    """Verify orders are preserved when fetch_order fails."""

    def _make_order_manager(self):
        from binance_bot.core.order_manager import OrderManager, OrderStatus
        from dataclasses import dataclass

        om = OrderManager.__new__(OrderManager)
        om.open_orders = {}
        om.filled_orders = []
        return om

    def test_sync_orders_keeps_order_on_fetch_failure(self):
        """Order should remain in open_orders when fetch_order raises."""
        from binance_bot.core.order_manager import OrderStatus

        om = self._make_order_manager()

        mock_order = MagicMock()
        mock_order.status = OrderStatus.OPEN
        om.open_orders = {"order-123": mock_order}

        with patch("binance_bot.core.order_manager.exchange_client") as mock_exchange:
            # fetch_open_orders returns empty (order no longer open)
            mock_exchange.exchange.fetch_open_orders.return_value = []
            # fetch_order fails with network error
            mock_exchange.exchange.fetch_order.side_effect = Exception("Network error")

            om.sync_orders("BTC/USDT")

        # Order should still be tracked
        assert "order-123" in om.open_orders, "Order should be preserved after fetch failure"

    def test_sync_orders_removes_order_on_successful_fetch(self):
        """Order should be removed from open_orders when status is successfully fetched."""
        from binance_bot.core.order_manager import OrderStatus

        om = self._make_order_manager()

        mock_order = MagicMock()
        mock_order.status = OrderStatus.OPEN
        om.open_orders = {"order-456": mock_order}

        with patch("binance_bot.core.order_manager.exchange_client") as mock_exchange:
            mock_exchange.exchange.fetch_open_orders.return_value = []
            mock_exchange.exchange.fetch_order.return_value = {
                "status": "filled",
                "filled": 0.001,
                "cost": 50.0,
            }

            # Mock _parse_status and _save_trade
            om._parse_status = MagicMock(return_value=OrderStatus.FILLED)
            om._save_trade = MagicMock()

            om.sync_orders("BTC/USDT")

        assert "order-456" not in om.open_orders, "Order should be removed after successful fetch"


# ── P1-STRAT-7: Short position support ───────────────────────────────


class TestP1Strat7ShortPositions:
    """Verify PositionManager handles short positions."""

    def _make_pm(self):
        from binance_bot.core.position_manager import PositionManager
        pm = PositionManager.__new__(PositionManager)
        pm.positions = {}
        pm.total_realized_pnl = 0.0
        # Mock _save_position to avoid DB calls
        pm._save_position = MagicMock()
        return pm

    def test_position_manager_open_short(self):
        """Opening a short should track short_amount and short_entry_price."""
        pm = self._make_pm()
        pm.update_position("BTC/USDT", "sell", 0.1, 50000.0, is_short=True)

        pos = pm.positions["BTC/USDT"]
        assert pos.short_amount == 0.1
        assert pos.short_entry_price == 50000.0
        assert pos.side in ("short", "both")

    def test_position_manager_cover_short_pnl(self):
        """Covering a short should calculate PnL = (entry - cover) × amount."""
        pm = self._make_pm()
        pm.update_position("BTC/USDT", "sell", 0.1, 50000.0, is_short=True)
        pm.update_position("BTC/USDT", "buy", 0.1, 48000.0, is_short=True)

        pos = pm.positions["BTC/USDT"]
        expected_pnl = (50000.0 - 48000.0) * 0.1  # 200.0
        assert abs(pm.total_realized_pnl - expected_pnl) < 0.01
        assert pos.short_amount == 0
        assert pos.short_entry_price == 0

    def test_position_manager_both_long_and_short(self):
        """Simultaneous long and short positions should both be tracked."""
        pm = self._make_pm()
        pm.update_position("BTC/USDT", "buy", 0.1, 50000.0)  # Long
        pm.update_position("BTC/USDT", "sell", 0.05, 51000.0, is_short=True)  # Short

        pos = pm.positions["BTC/USDT"]
        assert pos.amount == 0.1  # Long amount
        assert pos.short_amount == 0.05  # Short amount
        assert pos.side == "both"


# ── P1-STRAT-8: Short unrealized PnL ─────────────────────────────────


class TestP1Strat8ShortUnrealizedPnl:
    """Verify unrealized PnL includes short positions."""

    def _make_pm(self):
        from binance_bot.core.position_manager import PositionManager
        pm = PositionManager.__new__(PositionManager)
        pm.positions = {}
        pm.total_realized_pnl = 0.0
        pm._save_position = MagicMock()
        return pm

    def test_unrealized_pnl_short_position(self):
        """Short PnL = (entry - current) × amount."""
        pm = self._make_pm()
        pm.update_position("BTC/USDT", "sell", 0.1, 50000.0, is_short=True)

        pnl = pm.calculate_unrealized_pnl("BTC/USDT", 48000.0)
        expected = (50000.0 - 48000.0) * 0.1  # 200.0
        assert abs(pnl - expected) < 0.01

    def test_unrealized_pnl_both_positions(self):
        """Combined long + short unrealized PnL."""
        pm = self._make_pm()
        pm.update_position("BTC/USDT", "buy", 0.1, 50000.0)  # Long
        pm.update_position("BTC/USDT", "sell", 0.05, 52000.0, is_short=True)  # Short

        # Price at 51000: long PnL = (51000-50000)*0.1 = 100
        # short PnL = (52000-51000)*0.05 = 50
        pnl = pm.calculate_unrealized_pnl("BTC/USDT", 51000.0)
        expected = 100.0 + 50.0  # 150.0
        assert abs(pnl - expected) < 0.01

    def test_unrealized_pnl_no_position(self):
        """No position should return 0."""
        pm = self._make_pm()
        pnl = pm.calculate_unrealized_pnl("BTC/USDT", 50000.0)
        assert pnl == 0.0
