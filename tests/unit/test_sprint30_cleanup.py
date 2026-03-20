"""Sprint 30 — Code Quality & Cleanup Tests.

Validates all 15 fixes from the sprint-30-plan:
  P3-BOT-1..4, P3-STRAT-1a..d, P3-STRAT-2, P3-ALERT-2,
  P3-API-2, P3-API-3, P3-BACK-1, P3-BACK-2,
  P3-JESSE-1, P3-JESSE-2, P3-JESSE-3,
  P1-MON-1, P2-CORE-4
"""

import ast
import inspect
import textwrap

import pytest


# ---------------------------------------------------------------------------
# Helper: parse file into AST
# ---------------------------------------------------------------------------

def _parse_file(path: str) -> ast.Module:
    with open(path) as f:
        return ast.parse(f.read(), filename=path)


def _read_source(path: str) -> str:
    with open(path) as f:
        return f.read()


# ===========================================================================
# P3-BOT-1: Unused import read_state removed
# ===========================================================================

class TestP3Bot1:
    """read_state removed from bot.py imports; read_command added."""

    def test_no_read_state_import(self):
        src = _read_source("binance-bot/src/binance_bot/bot.py")
        assert "read_state" not in src

    def test_read_command_import_exists(self):
        src = _read_source("binance-bot/src/binance_bot/bot.py")
        assert "read_command" in src


# ===========================================================================
# P3-BOT-2: Unused variable old_state removed
# ===========================================================================

class TestP3Bot2:
    def test_no_old_state(self):
        src = _read_source("binance-bot/src/binance_bot/bot.py")
        assert "old_state" not in src


# ===========================================================================
# P3-BOT-3: Import moved out of loop to file level
# ===========================================================================

class TestP3Bot3:
    def test_no_import_inside_run_loop(self):
        """read_command should not be imported inside the run method body."""
        tree = _parse_file("binance-bot/src/binance_bot/bot.py")
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "run":
                for child in ast.walk(node):
                    if isinstance(child, ast.ImportFrom) and child.module and "read_command" in (
                        alias.name for alias in child.names
                    ):
                        pytest.fail("read_command is still imported inside the run() method")


# ===========================================================================
# P3-BOT-4: Duplicate _write_shared_state(current_price=None) removed
# ===========================================================================

class TestP3Bot4:
    def test_no_write_shared_state_none(self):
        src = _read_source("binance-bot/src/binance_bot/bot.py")
        assert "current_price=None" not in src


# ===========================================================================
# P3-STRAT-1a: Unused 'delete' import removed from data_collector
# ===========================================================================

class TestP3Strat1a:
    def test_no_delete_import(self):
        src = _read_source("binance-bot/src/binance_bot/core/data_collector.py")
        assert "delete" not in src


# ===========================================================================
# P3-STRAT-1b: Unused 'from datetime import datetime' in data_collector
# ===========================================================================

class TestP3Strat1b:
    def test_no_datetime_import(self):
        src = _read_source("binance-bot/src/binance_bot/core/data_collector.py")
        assert "from datetime import datetime" not in src


# ===========================================================================
# P3-STRAT-1c: Unused 'field' import in position_manager
# ===========================================================================

class TestP3Strat1c:
    def test_no_field_import(self):
        src = _read_source("binance-bot/src/binance_bot/core/position_manager.py")
        # Should import dataclass but not field
        assert "from dataclasses import dataclass\n" in src
        assert "field" not in src.split("from dataclasses")[1].split("\n")[0]


# ===========================================================================
# P3-STRAT-1d: Unused 'from datetime import datetime' in position_manager
# ===========================================================================

class TestP3Strat1d:
    def test_no_datetime_import(self):
        src = _read_source("binance-bot/src/binance_bot/core/position_manager.py")
        assert "from datetime import datetime" not in src


# ===========================================================================
# P3-STRAT-2: Unused pnl_color removed
# ===========================================================================

class TestP3Strat2:
    def test_no_pnl_color(self):
        src = _read_source("binance-bot/src/binance_bot/core/position_manager.py")
        assert "pnl_color" not in src


# ===========================================================================
# P3-ALERT-2: trades_list propagated to Discord
# ===========================================================================

class TestP3Alert2:
    def test_discord_accepts_trades_list(self):
        from shared.alerts.discord import DiscordAlert

        sig = inspect.signature(DiscordAlert.send_daily_summary)
        assert "trades_list" in sig.parameters

    def test_manager_passes_trades_list(self):
        src = _read_source("shared/alerts/manager.py")
        assert "trades_list=trades_list" in src


# ===========================================================================
# P3-API-2: force_buy/force_sell deduplicated via _force_trade helper
# ===========================================================================

class TestP3Api2:
    def test_force_trade_helper_exists(self):
        src = _read_source("shared/api/routes/orders.py")
        assert "_force_trade" in src

    def test_force_buy_delegates(self):
        src = _read_source("shared/api/routes/orders.py")
        # force_buy should call _force_trade
        assert '_force_trade("buy"' in src or "_force_trade('buy'" in src

    def test_force_sell_delegates(self):
        src = _read_source("shared/api/routes/orders.py")
        assert '_force_trade("sell"' in src or "_force_trade('sell'" in src


# ===========================================================================
# P3-API-3: Drawdown computation deduplicated
# ===========================================================================

class TestP3Api3:
    def test_compute_drawdowns_exists(self):
        from shared.risk.metrics import RiskMetrics

        assert hasattr(RiskMetrics, "_compute_drawdowns")

    def test_drawdown_values(self):
        from shared.risk.metrics import RiskMetrics

        rm = RiskMetrics()
        rm.update_equity(100)
        rm.update_equity(90)
        rm.update_equity(95)

        pct, amt = rm._compute_drawdowns()
        assert pct == pytest.approx(0.10, abs=0.01)
        assert amt == pytest.approx(10.0, abs=0.1)


# ===========================================================================
# P3-BACK-1: Unused 'colors' variable removed from charts.py
# ===========================================================================

class TestP3Back1:
    def test_no_colors_variable(self):
        src = _read_source("shared/backtest/charts.py")
        assert "colors =" not in src


# ===========================================================================
# P3-BACK-2: Unused numpy import removed from charts.py
# ===========================================================================

class TestP3Back2:
    def test_no_numpy_import(self):
        src = _read_source("shared/backtest/charts.py")
        assert "import numpy" not in src


# ===========================================================================
# P3-JESSE-1: Duplicate logger removed
# ===========================================================================

class TestP3Jesse1:
    def test_single_logger(self):
        src = _read_source("jesse-bot/strategies/AIGridStrategy/__init__.py")
        count = src.count("logger = logging.getLogger(__name__)")
        assert count == 1, f"Expected 1 logger assignment, found {count}"


# ===========================================================================
# P3-JESSE-2: Deprecated asyncio.get_event_loop() replaced
# ===========================================================================

class TestP3Jesse2:
    def test_no_get_event_loop(self):
        src = _read_source("jesse-bot/strategies/AIGridStrategy/ai_mixin.py")
        assert "get_event_loop()" not in src

    def test_uses_get_running_loop(self):
        src = _read_source("jesse-bot/strategies/AIGridStrategy/ai_mixin.py")
        assert "get_running_loop()" in src


# ===========================================================================
# P3-JESSE-3: Unused 'atr' param removed from setup_grid
# ===========================================================================

class TestP3Jesse3:
    def test_no_atr_in_setup_grid_signature(self):
        src = _read_source("jesse-bot/live_trader.py")
        # Find the setup_grid definition line
        for line in src.splitlines():
            if "def setup_grid(" in line:
                assert "atr" not in line, f"atr still in signature: {line}"
                break

    def test_call_site_no_atr(self):
        src = _read_source("jesse-bot/live_trader.py")
        assert "setup_grid(price, atr" not in src


# ===========================================================================
# P1-MON-1: __new__ singleton removed from TradingMetrics
# ===========================================================================

class TestP1Mon1:
    def test_no_new_singleton(self):
        src = _read_source("shared/monitoring/metrics.py")
        assert "__new__" not in src

    def test_get_metrics_factory(self):
        src = _read_source("shared/monitoring/metrics.py")
        assert "def get_metrics(" in src

    def test_creates_different_instances(self):
        from shared.monitoring.metrics import TradingMetrics

        a = TradingMetrics()
        b = TradingMetrics()
        assert a is not b, "__new__ singleton was not removed"


# ===========================================================================
# P2-CORE-4: Duplicate index=True removed from TradeLog.timestamp
# ===========================================================================

class TestP2Core4:
    def test_no_index_true_on_timestamp(self):
        src = _read_source("shared/core/database.py")
        # Find the timestamp column line in TradeLog
        in_trade_log = False
        for line in src.splitlines():
            if "class TradeLog" in line:
                in_trade_log = True
            elif in_trade_log and line.strip().startswith("class "):
                break
            elif in_trade_log and "timestamp" in line and "Column" in line:
                assert "index=True" not in line, f"index=True still on timestamp: {line}"
                break

    def test_explicit_index_in_table_args(self):
        src = _read_source("shared/core/database.py")
        assert "idx_trade_logs_timestamp" in src
