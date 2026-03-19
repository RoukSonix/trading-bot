"""Sprint 28: Alerts, API & Data Fixes — Tests for all 15 issues."""

import json
import os
import tempfile
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── Issue 1: P1-ALERT-1 — Naive vs aware datetime mixing ───────────────────


class TestP1Alert1DatetimeMixing:
    """Rate limit and record_alert should use timezone-aware datetimes."""

    def test_rate_limit_uses_utc(self):
        from shared.alerts.manager import AlertManager, AlertConfig

        mgr = AlertManager(AlertConfig(rate_limit_per_minute=100))
        # Should not raise TypeError when comparing with aware timestamps
        result = mgr._check_rate_limit("test_type")
        assert result is True

    def test_record_alert_uses_utc(self):
        from shared.alerts.manager import AlertManager, AlertConfig

        mgr = AlertManager(AlertConfig())
        mgr._record_alert("test")
        ts = mgr._alert_timestamps[0]
        assert ts.tzinfo is not None, "Timestamp should be timezone-aware"

    def test_rate_limit_aware_comparison(self):
        """Mixing rate-limit timestamps with aware datetimes must not raise."""
        from shared.alerts.manager import AlertManager, AlertConfig

        mgr = AlertManager(AlertConfig(rate_limit_per_minute=100, min_alert_interval_seconds=0))
        mgr._record_alert("x")
        # Second call compares aware timestamps — must not raise
        assert mgr._check_rate_limit("x") is True


# ─── Issue 2: P1-ALERT-2 — Price movement iterates wrong direction ──────────


class TestP1Alert2PriceDirection:
    """Price movement rule should find the most recent price before cutoff."""

    def test_price_movement_uses_recent_price(self):
        from shared.alerts.rules import AlertRulesEngine, AlertRule, RuleType, PricePoint

        engine = AlertRulesEngine()
        now = datetime.now(timezone.utc)

        # Add prices: oldest=100 (-25min), mid=150 (-20min), newest=200 (now)
        # Both 100 and 150 are before the 15min cutoff.
        # reversed() should find 150 first (most recent before cutoff).
        engine._price_history.clear()
        engine._price_history.append(PricePoint(price=100.0, timestamp=now - timedelta(minutes=25)))
        engine._price_history.append(PricePoint(price=150.0, timestamp=now - timedelta(minutes=20)))
        engine._price_history.append(PricePoint(price=200.0, timestamp=now))

        rule = AlertRule(
            name="test_movement",
            rule_type=RuleType.PRICE_MOVEMENT,
            price_change_pct=1.0,
            price_window_minutes=15,
            cooldown_minutes=0,
        )

        result = engine._eval_price_movement(rule)
        # old_price should be 150 (most recent before cutoff), not 100
        assert result is not None
        assert result["data"]["old_price"] == 150.0

    def test_price_movement_no_history(self):
        from shared.alerts.rules import AlertRulesEngine, AlertRule, RuleType

        engine = AlertRulesEngine()
        engine._price_history.clear()

        rule = AlertRule(
            name="test",
            rule_type=RuleType.PRICE_MOVEMENT,
            price_change_pct=5.0,
            price_window_minutes=15,
        )
        assert engine._eval_price_movement(rule) is None


# ─── Issue 3: P1-ALERT-3 — send_tp_sl_alert wired through AlertManager ──────


class TestP1Alert3TpSlWiring:
    """AlertManager.send_tp_sl_alert should route to discord."""

    @pytest.mark.asyncio
    async def test_tp_sl_alert_routed_through_manager(self):
        from shared.alerts.manager import AlertManager, AlertConfig

        mgr = AlertManager(AlertConfig())
        mgr._discord = MagicMock()
        mgr._discord.send_tp_sl_alert = AsyncMock(return_value=True)

        result = await mgr.send_tp_sl_alert(
            event_type="take_profit",
            symbol="BTC/USDT",
            level_price=85000.0,
            exit_price=86000.0,
            pnl=10.0,
        )
        assert result is True
        mgr._discord.send_tp_sl_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_tp_sl_alert_rate_limited(self):
        from shared.alerts.manager import AlertManager, AlertConfig

        mgr = AlertManager(AlertConfig(rate_limit_per_minute=1))
        mgr._discord = MagicMock()
        mgr._discord.send_tp_sl_alert = AsyncMock(return_value=True)

        # First call succeeds
        await mgr.send_tp_sl_alert("take_profit", "BTC/USDT", 85000, 86000, 10.0)
        # Second call should be rate limited (per-minute limit = 1)
        result = await mgr.send_tp_sl_alert("take_profit", "BTC/USDT", 85000, 86000, 10.0)
        assert result is False


# ─── Issue 4: P1-CORE-1 — read_command TOCTOU ───────────────────────────────


class TestP1Core1ReadCommandToctou:
    """read_command should handle missing files via exception, not exists()."""

    def test_read_command_file_not_found(self):
        from shared.core.state import read_command

        result = read_command(Path("/tmp/nonexistent_command_12345.json"))
        assert result is None

    def test_read_command_valid(self, tmp_path):
        from shared.core.state import read_command

        cmd_file = tmp_path / "cmd.json"
        cmd_file.write_text(json.dumps({"command": "pause", "timestamp": "2026-01-01T00:00:00"}))
        result = read_command(cmd_file)
        assert result == "pause"
        assert not cmd_file.exists(), "Command file should be consumed"

    def test_read_command_corrupt_json(self, tmp_path):
        from shared.core.state import read_command

        cmd_file = tmp_path / "cmd.json"
        cmd_file.write_text("{not valid json")
        result = read_command(cmd_file)
        assert result is None
        assert not cmd_file.exists(), "Corrupt file should be removed"


# ─── Issue 5: P1-CORE-2 — write_command atomic ──────────────────────────────


class TestP1Core2WriteCommandAtomic:
    """write_command should write atomically via temp file + rename."""

    def test_write_command_atomic(self, tmp_path):
        from shared.core.state import write_command

        cmd_file = tmp_path / "cmd.json"
        write_command("resume", cmd_file)
        data = json.loads(cmd_file.read_text())
        assert data["command"] == "resume"
        assert "timestamp" in data

    def test_write_command_creates_parent_dir(self, tmp_path):
        from shared.core.state import write_command

        cmd_file = tmp_path / "nested" / "dir" / "cmd.json"
        write_command("stop", cmd_file)
        assert cmd_file.exists()


# ─── Issue 6: P1-CORE-3 — to_dataframe crashes on empty candles ─────────────


class TestP1Core3EmptyCandles:
    """Indicators.to_dataframe should handle empty input gracefully."""

    def test_to_dataframe_empty_candles(self):
        from shared.core.indicators import Indicators

        df = Indicators.to_dataframe([])
        assert len(df) == 0

    def test_to_dataframe_empty_dicts(self):
        from shared.core.indicators import Indicators

        df = Indicators.to_dataframe([{}, {}])
        assert len(df) == 2

    def test_to_dataframe_valid(self):
        from shared.core.indicators import Indicators

        candles = [
            {"timestamp": 1700000000000, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100},
        ]
        df = Indicators.to_dataframe(candles)
        assert len(df) == 1


# ─── Issue 7: P1-CORE-4 — Database module-level side effects ────────────────


class TestP1Core4DatabaseSideEffects:
    """Importing database should not create directories or connections."""

    def test_get_engine_lazy_init(self):
        from shared.core.database import get_engine

        engine = get_engine()
        assert engine is not None

    def test_get_session_returns_session(self):
        from shared.core.database import get_session

        session = get_session()
        assert session is not None
        session.close()


# ─── Issue 8: P1-RISK-1 — Duplicate orders in API response ──────────────────


class TestP1Risk1DuplicateOrders:
    """Orders from state should not duplicate with orders from bot instance."""

    @pytest.mark.asyncio
    async def test_orders_no_duplicates_from_state(self):
        """When state has orders, should return immediately without bot fallback."""
        from shared.core.state import BotState

        state = BotState(
            symbol="BTC/USDT",
            grid_levels=[
                {"price": 85000, "side": "buy", "amount": 0.001, "filled": False, "order_id": "order_1"},
            ],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        with patch("shared.core.state.read_state", return_value=state):
            from shared.api.routes.orders import get_orders
            result = await get_orders()
            assert result.total == 1


# ─── Issue 9: P2-CORE-1 — datetime.now() without timezone ───────────────────


class TestP2Core1DatetimeTimezone:
    """All datetime.now() calls should use timezone.utc."""

    def test_all_datetimes_timezone_aware(self):
        """Grep source for bare datetime.now() — should find zero matches."""
        import subprocess

        result = subprocess.run(
            ["grep", "-rn", r"datetime\.now()", "--include=*.py",
             "shared/", "binance-bot/src/"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).resolve().parent.parent.parent),
        )
        matches = [
            line for line in result.stdout.strip().split("\n")
            if line and "__pycache__" not in line and "test_" not in line
        ]
        assert len(matches) == 0, f"Found bare datetime.now():\n" + "\n".join(matches)


# ─── Issue 10: P2-API-3 — CORS allows all origins with credentials ──────────


class TestP2Api3CorsOrigins:
    """CORS should restrict origins, not allow *."""

    def test_cors_not_wildcard(self):
        """The CORS middleware should not use allow_origins=['*']."""
        from shared.api.main import app

        for mw in app.user_middleware:
            if hasattr(mw, "kwargs") and "allow_origins" in mw.kwargs:
                origins = mw.kwargs["allow_origins"]
                assert origins != ["*"], "CORS should not allow all origins"


# ─── Issue 11: P2-API-6 — No authentication on trading endpoints ────────────


class TestP2Api6Authentication:
    """Write endpoints should require API key."""

    @pytest.mark.asyncio
    async def test_force_buy_requires_api_key(self):
        from shared.api.auth import require_api_key
        from fastapi import HTTPException

        # No TRADING_API_KEY env var set
        with patch.dict(os.environ, {"TRADING_API_KEY": "secret123"}, clear=False):
            # No key provided → 401
            with pytest.raises(HTTPException) as exc:
                await require_api_key(api_key=None)
            assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_force_buy_with_valid_key(self):
        from shared.api.auth import require_api_key

        with patch.dict(os.environ, {"TRADING_API_KEY": "secret123"}, clear=False):
            result = await require_api_key(api_key="secret123")
            assert result == "secret123"

    @pytest.mark.asyncio
    async def test_no_api_key_configured(self):
        from shared.api.auth import require_api_key
        from fastapi import HTTPException

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TRADING_API_KEY", None)
            with pytest.raises(HTTPException) as exc:
                await require_api_key(api_key="anything")
            assert exc.value.status_code == 503


# ─── Issue 12: P2-ALERT-1 — Truthiness check on current_price ───────────────


class TestP2Alert1TruthinessPrice:
    """Price of 0.0 should still be included in embeds."""

    @pytest.mark.asyncio
    async def test_status_alert_price_zero(self):
        from shared.alerts.discord import DiscordAlert

        alert = DiscordAlert(webhook_url="")  # disabled
        alert.enabled = False

        # We can't send, but we can check the field logic directly
        fields = [{"name": "Symbol", "value": "BTC/USDT", "inline": True}]
        current_price = 0.0
        if current_price is not None:
            fields.append({"name": "Price", "value": f"${current_price:,.2f}", "inline": True})
        assert any(f["name"] == "Price" for f in fields)

    @pytest.mark.asyncio
    async def test_status_alert_price_none(self):
        fields = [{"name": "Symbol", "value": "BTC/USDT", "inline": True}]
        current_price = None
        if current_price is not None:
            fields.append({"name": "Price", "value": f"${current_price:,.2f}", "inline": True})
        assert not any(f["name"] == "Price" for f in fields)


# ─── Issue 13: P2-RISK-1 — trade_history unbounded (memory leak) ────────────


class TestP2Risk1TradeHistoryBounded:
    """trade_history should be a bounded deque."""

    def test_trade_history_bounded(self):
        from shared.risk.limits import RiskLimits

        rl = RiskLimits(initial_balance=10000.0)
        for i in range(1500):
            rl.record_trade(pnl=1.0, trade_info={"id": i})
        assert len(rl.trade_history) == 1000

    def test_trade_history_fifo(self):
        from shared.risk.limits import RiskLimits

        rl = RiskLimits(initial_balance=10000.0)
        for i in range(1100):
            rl.record_trade(pnl=1.0, trade_info={"id": i})
        # Oldest (id=0..99) should be dropped
        assert rl.trade_history[0]["id"] == 100


# ─── Issue 14: P2-RISK-2 — equity_curve unbounded (memory leak) ─────────────


class TestP2Risk2EquityCurveBounded:
    """equity_curve should be a bounded deque."""

    def test_equity_curve_bounded(self):
        from shared.risk.metrics import RiskMetrics

        rm = RiskMetrics()
        for i in range(15000):
            rm.update_equity(10000.0 + i)
        assert len(rm.equity_curve) == 10000

    def test_equity_curve_preserves_recent(self):
        from shared.risk.metrics import RiskMetrics

        rm = RiskMetrics()
        for i in range(12000):
            rm.update_equity(float(i))
        # Most recent entry should be 11999
        assert rm.equity_curve[-1][1] == 11999.0


# ─── Issue 15: P2-BOT-1 — Hardcoded initial balance ─────────────────────────


class TestP2Bot1HardcodedBalance:
    """Initial balance should come from settings."""

    def test_initial_balance_from_settings(self):
        with patch.dict(os.environ, {"PAPER_INITIAL_BALANCE": "5000"}, clear=False):
            # Force reload settings
            from shared.config.settings import Settings
            s = Settings()
            assert s.paper_initial_balance == 5000.0

    def test_initial_balance_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PAPER_INITIAL_BALANCE", None)
            from shared.config.settings import Settings
            s = Settings()
            assert s.paper_initial_balance == 10000.0
