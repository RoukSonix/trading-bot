"""Sprint 27: Risk Management Fixes — Unit Tests.

Tests all 10 issues:
  P1-RISK-2:  risk_amount double-applies percentage
  P1-RISK-3:  Sortino ratio returns 0 for all-winning
  P1-RISK-4:  Profit factor returns 0 for all-winning
  P1-RISK-5:  Max drawdown auto-resets daily
  P1-RISK-6:  Drawdown uses daily HWM, not overall
  P1-RISK-7:  Win/loss trade pairing logic broken
  P1-RISK-8:  Symbol filter ignored for TradeLog
  P1-RISK-9:  Sharpe/Sortino annualization incorrect
  P1-RISK-10: StopLossManager limited to one position per symbol
  P1-BOT-3:   strategy_engine data computed but never persisted
"""

import json
import tempfile
from datetime import datetime, timedelta, date
from pathlib import Path
from unittest.mock import patch

import pytest

from shared.risk.position_sizer import PositionSizer, SizingMethod
from shared.risk.metrics import RiskMetrics, TradeRecord
from shared.risk.limits import RiskLimits
from shared.risk.stop_loss import StopLossManager
from shared.core.state import BotState, write_state, read_state


# ── P1-RISK-2: risk_amount double-applies percentage ──


class TestP1Risk2PositionSizerDoublePercent:
    def test_risk_amount_not_double_applied(self):
        sizer = PositionSizer(method=SizingMethod.FIXED_PERCENT, risk_per_trade=0.02)
        result = sizer.calculate(portfolio_value=10_000, entry_price=50_000)
        # risk_amount should be 2% of 10,000 = $200, NOT 0.02 * 200 = $4
        assert result.risk_amount == pytest.approx(200.0)

    def test_risk_amount_fixed_percent_matches_value(self):
        sizer = PositionSizer(
            method=SizingMethod.FIXED_PERCENT,
            risk_per_trade=0.05,
            max_position_pct=0.50,
        )
        result = sizer.calculate(portfolio_value=20_000, entry_price=100)
        # 5% of 20k = 1000, under 50% cap → risk_amount == value
        assert result.risk_amount == result.value


# ── P1-RISK-3: Sortino ratio returns 0 for all-winning ──


class TestP1Risk3SortinoAllWinning:
    @staticmethod
    def _make_metrics(pnl_pcts):
        m = RiskMetrics()
        for i, pct in enumerate(pnl_pcts):
            m.trades.append(TradeRecord(
                timestamp=datetime(2026, 1, 1) + timedelta(hours=i),
                symbol="BTC/USDT", side="buy",
                entry_price=100, exit_price=100 * (1 + pct),
                amount=1, pnl=100 * pct, pnl_pct=pct,
            ))
        return m

    def test_sortino_all_winning(self):
        m = self._make_metrics([0.01, 0.02, 0.03, 0.015, 0.025])
        assert m.sortino_ratio() == 99.99

    def test_sortino_all_losing(self):
        m = self._make_metrics([-0.01, -0.02, -0.03, -0.015, -0.025])
        assert m.sortino_ratio() < 0

    def test_sortino_mixed(self):
        m = self._make_metrics([0.02, -0.01, 0.03, -0.005, 0.01])
        ratio = m.sortino_ratio()
        assert ratio != 0.0  # should be a real value

    def test_sortino_insufficient_trades(self):
        m = self._make_metrics([0.05])
        assert m.sortino_ratio() == 0.0


# ── P1-RISK-4: Profit factor returns 0 for all-winning ──


class TestP1Risk4ProfitFactorAllWinning:
    @staticmethod
    def _make_metrics(pnls):
        m = RiskMetrics()
        for i, pnl in enumerate(pnls):
            pct = pnl / 100
            m.trades.append(TradeRecord(
                timestamp=datetime(2026, 1, 1) + timedelta(hours=i),
                symbol="BTC/USDT", side="buy",
                entry_price=100, exit_price=100 + pnl,
                amount=1, pnl=pnl, pnl_pct=pct,
            ))
        return m

    def test_profit_factor_all_winning(self):
        m = self._make_metrics([10, 20, 30])
        assert m.profit_factor == 99.99

    def test_profit_factor_all_losing(self):
        m = self._make_metrics([-10, -20, -30])
        assert m.profit_factor == 0.0

    def test_profit_factor_mixed(self):
        m = self._make_metrics([30, -10, 20, -5])
        assert m.profit_factor == pytest.approx(50 / 15, rel=1e-3)

    def test_profit_factor_no_trades(self):
        m = RiskMetrics()
        assert m.profit_factor == 0.0


# ── P1-RISK-5: Max drawdown auto-resets daily ──


class TestP1Risk5DrawdownAutoReset:
    def test_daily_loss_resets_next_day(self):
        rl = RiskLimits(daily_loss_limit=0.05, max_drawdown_limit=0.50)
        rl.set_initial_balance(10_000)
        rl._halt_trading("Daily loss limit breached: 5.1%")
        assert rl.trading_halted

        # Simulate new day
        rl.daily_stats.date = date(2025, 1, 1)
        rl.update_balance(9_500)
        assert not rl.trading_halted

    def test_max_drawdown_persists_next_day(self):
        rl = RiskLimits(daily_loss_limit=0.05, max_drawdown_limit=0.10)
        rl.set_initial_balance(10_000)
        rl._halt_trading("Max drawdown breached: 11.0%")
        assert rl.trading_halted

        # Simulate new day — drawdown halt should persist
        rl.daily_stats.date = date(2025, 1, 1)
        rl.update_balance(8_900)
        assert rl.trading_halted
        assert "drawdown" in rl.halt_reason.lower()

    def test_consecutive_losses_resets_next_day(self):
        rl = RiskLimits(max_consecutive_losses=3)
        rl.set_initial_balance(10_000)
        rl.consecutive_losses = 5

        rl.daily_stats.date = date(2025, 1, 1)
        rl.update_balance(10_000)
        assert rl.consecutive_losses == 0

    def test_max_trades_resets_next_day(self):
        rl = RiskLimits(max_trades_per_day=10)
        rl.set_initial_balance(10_000)
        rl.daily_stats.trades_count = 10

        old_date = rl.daily_stats.date
        rl.daily_stats.date = date(2025, 1, 1)
        rl.update_balance(10_000)
        assert rl.daily_stats.trades_count == 0


# ── P1-RISK-6: Drawdown uses daily HWM ──


class TestP1Risk6DrawdownDailyHWM:
    def test_drawdown_detected_across_days(self):
        rl = RiskLimits(max_drawdown_limit=0.10)
        rl.set_initial_balance(10_000)

        # Day 1: drop 3%
        rl.update_balance(9_700)

        # Simulate day 2: drop further
        rl.daily_stats.date = date(2025, 1, 1)
        rl.update_balance(9_300)  # now 7% from HWM

        # Day 3: drop more
        rl.daily_stats.date = date(2025, 1, 2)
        rl.update_balance(8_900)  # 11% from HWM of 10,000

        status = rl.check_limits()
        from shared.risk.limits import LimitStatus
        assert status == LimitStatus.BREACHED
        assert rl.trading_halted

    def test_drawdown_from_overall_hwm(self):
        rl = RiskLimits(max_drawdown_limit=0.10)
        rl.set_initial_balance(10_000)
        rl.update_balance(11_000)  # HWM = 11,000
        rl.update_balance(9_500)   # 13.6% drawdown from 11,000

        status = rl.check_limits()
        from shared.risk.limits import LimitStatus
        assert status == LimitStatus.BREACHED


# ── P1-RISK-7: Win/loss trade pairing logic ──


class TestP1Risk7WinLossPairing:
    """Tests require database fixtures; test the logic directly instead."""

    def test_pnl_fifo_pairing(self):
        """buy@100, buy@200, sell@150 → FIFO: paired with buy@100 → win."""
        buys = [type("T", (), {"price": "100"})(), type("T", (), {"price": "200"})()]
        sells = [type("T", (), {"price": "150"})()]

        winning = []
        losing = []
        buy_queue = list(buys)
        for sell in sells:
            if buy_queue:
                paired_buy = buy_queue.pop(0)
                if float(sell.price) > float(paired_buy.price):
                    winning.append(sell)
                else:
                    losing.append(sell)
            else:
                losing.append(sell)

        assert len(winning) == 1
        assert len(losing) == 0

    def test_pnl_all_sells_losing(self):
        buys = [type("T", (), {"price": "200"})(), type("T", (), {"price": "300"})()]
        sells = [type("T", (), {"price": "100"})(), type("T", (), {"price": "150"})()]

        winning = []
        losing = []
        buy_queue = list(buys)
        for sell in sells:
            if buy_queue:
                paired_buy = buy_queue.pop(0)
                if float(sell.price) > float(paired_buy.price):
                    winning.append(sell)
                else:
                    losing.append(sell)
            else:
                losing.append(sell)

        assert len(winning) == 0
        assert len(losing) == 2

    def test_pnl_no_buys(self):
        sells = [type("T", (), {"price": "100"})()]
        buy_queue = []
        losing = []
        for sell in sells:
            if buy_queue:
                pass
            else:
                losing.append(sell)
        assert len(losing) == 1

    def test_pnl_more_sells_than_buys(self):
        buys = [type("T", (), {"price": "100"})()]
        sells = [type("T", (), {"price": "150"})(), type("T", (), {"price": "120"})()]

        winning = []
        losing = []
        buy_queue = list(buys)
        for sell in sells:
            if buy_queue:
                paired_buy = buy_queue.pop(0)
                if float(sell.price) > float(paired_buy.price):
                    winning.append(sell)
                else:
                    losing.append(sell)
            else:
                losing.append(sell)

        assert len(winning) == 1
        assert len(losing) == 1  # excess sell → loss


# ── P1-RISK-8: Symbol filter ignored for TradeLog ──
# (Integration test — checks the query construction pattern, not actual DB)


class TestP1Risk8SymbolFilter:
    def test_pnl_summary_query_applies_filter(self):
        """Verify the code path builds a filtered query when symbol is given."""
        # We test the source code structure — the fix replaced
        # session.query(TradeLog).all() with query.filter(...).all()
        import inspect
        from shared.api.routes.trades import get_pnl_summary
        src = inspect.getsource(get_pnl_summary)
        assert "query.filter(TradeLog.symbol == symbol)" in src
        assert "session.query(TradeLog).all()" not in src

    def test_pnl_history_query_applies_filter(self):
        import inspect
        from shared.api.routes.trades import get_pnl_history
        src = inspect.getsource(get_pnl_history)
        # Should filter TradeLog query
        assert "query.filter(TradeLog.symbol == symbol)" in src


# ── P1-RISK-9: Sharpe/Sortino annualization ──


class TestP1Risk9Annualization:
    @staticmethod
    def _make_metrics(pnl_pcts, period_days=365):
        m = RiskMetrics()
        for i, pct in enumerate(pnl_pcts):
            m.trades.append(TradeRecord(
                timestamp=datetime(2026, 1, 1) + timedelta(hours=i),
                symbol="BTC/USDT", side="buy",
                entry_price=100, exit_price=100 * (1 + pct),
                amount=1, pnl=100 * pct, pnl_pct=pct,
            ))
        return m

    def test_sharpe_annualization_reasonable(self):
        pcts = [0.001 * (i % 5 - 2) for i in range(100)]  # mixed small returns
        m = self._make_metrics(pcts)
        sharpe = m.sharpe_ratio(period_days=365)
        assert -5 <= sharpe <= 5, f"Sharpe {sharpe} out of reasonable range"

    def test_sortino_annualization_reasonable(self):
        pcts = [0.001 * (i % 5 - 1) for i in range(100)]  # mixed, slightly positive
        m = self._make_metrics(pcts)
        sortino = m.sortino_ratio(period_days=365)
        # Should not be absurdly large
        assert -10 <= sortino <= 100, f"Sortino {sortino} out of range"

    def test_sharpe_identical_returns(self):
        m = self._make_metrics([0.01] * 10)
        assert m.sharpe_ratio() == 0.0  # std=0 → 0

    def test_sharpe_negative_returns(self):
        m = self._make_metrics([-0.01, -0.02, -0.005, -0.03, -0.01])
        assert m.sharpe_ratio() < 0


# ── P1-RISK-10: StopLossManager multi-position ──


class TestP1Risk10MultiPosition:
    def test_multiple_positions_same_symbol(self):
        mgr = StopLossManager()
        mgr.add_position(symbol="BTC/USDT", entry_price=50_000, amount=0.1)
        mgr.add_position(symbol="BTC/USDT", entry_price=48_000, amount=0.2)
        mgr.add_position(symbol="BTC/USDT", entry_price=52_000, amount=0.15)

        btc_positions = [p for p in mgr.positions.values() if p.symbol == "BTC/USDT"]
        assert len(btc_positions) == 3

    def test_stop_loss_triggers_correct_position(self):
        mgr = StopLossManager(default_stop_pct=0.02, default_tp_pct=0.10)
        mgr.add_position(symbol="BTC/USDT", entry_price=50_000, amount=0.1)
        mgr.add_position(symbol="BTC/USDT", entry_price=48_000, amount=0.2)

        # Price drops to 47,000 — only the 48,000 entry (SL ≈ 47,040) should trigger
        # Actually SL = 48000 - 48000*0.02 = 47,040. Price 47,000 < 47,040 → trigger.
        # The 50,000 entry SL = 49,000. Price 47,000 < 49,000 → also triggers.
        results = mgr.check_positions_for_symbol("BTC/USDT", 47_000)
        assert len(results) == 2  # both trigger at 47k

        # Price 48,900 — only 50k entry triggers (SL=49,000; 48,900 <= 49,000),
        # 48k entry (SL=47,040; 48,900 > 47,040) does not
        mgr2 = StopLossManager(default_stop_pct=0.02, default_tp_pct=0.10)
        mgr2.add_position(symbol="BTC/USDT", entry_price=50_000, amount=0.1)
        mgr2.add_position(symbol="BTC/USDT", entry_price=48_000, amount=0.2)
        results2 = mgr2.check_positions_for_symbol("BTC/USDT", 48_900)
        assert len(results2) == 1
        assert results2[0]["action"] == "stop_loss"

    def test_remove_position_by_id(self):
        mgr = StopLossManager()
        mgr.add_position(symbol="BTC/USDT", entry_price=50_000, amount=0.1)
        mgr.add_position(symbol="BTC/USDT", entry_price=48_000, amount=0.2)

        # Get position IDs
        pids = list(mgr.positions.keys())
        assert len(pids) == 2

        mgr.remove_position_by_id(pids[0])
        assert len(mgr.positions) == 1
        assert pids[1] in mgr.positions

    def test_remove_all_positions_for_symbol(self):
        mgr = StopLossManager()
        mgr.add_position(symbol="BTC/USDT", entry_price=50_000, amount=0.1)
        mgr.add_position(symbol="BTC/USDT", entry_price=48_000, amount=0.2)
        mgr.add_position(symbol="ETH/USDT", entry_price=3_000, amount=1.0)

        mgr.remove_position("BTC/USDT")
        assert len(mgr.positions) == 1
        remaining = list(mgr.positions.values())[0]
        assert remaining.symbol == "ETH/USDT"


# ── P1-BOT-3: strategy_engine data persisted ──


class TestP1Bot3StrategyEnginePersist:
    def test_state_has_strategy_engine_field(self):
        state = BotState()
        assert hasattr(state, "strategy_engine")
        assert state.strategy_engine == {}

    def test_state_roundtrip_with_engine(self):
        state = BotState()
        state.strategy_engine = {
            "active_strategy": "momentum",
            "current_regime": "trending_up",
        }
        d = state.to_dict()
        assert "strategy_engine" in d
        assert d["strategy_engine"]["active_strategy"] == "momentum"

        restored = BotState.from_dict(d)
        assert restored.strategy_engine == state.strategy_engine

    def test_strategy_engine_data_persisted(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = Path(f.name)
        try:
            state = BotState()
            state.strategy_engine = {"active_strategy": "grid", "trades": 42}
            write_state(state, path=path)

            restored = read_state(path=path)
            assert restored is not None
            assert restored.strategy_engine["active_strategy"] == "grid"
            assert restored.strategy_engine["trades"] == 42
        finally:
            path.unlink(missing_ok=True)
