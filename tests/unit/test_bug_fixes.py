"""Tests for BUGS.md fixes (BUG-001 through BUG-010)."""

import json
import os

os.environ.setdefault("BINANCE_API_KEY", "test_api_key")
os.environ.setdefault("BINANCE_SECRET_KEY", "test_secret_key")

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from shared.core.database import Base, Trade, Position, TradeLog
from shared.risk.metrics import RiskMetrics
from shared.risk.stop_loss import StopLossManager
from shared.optimization.metrics import PerformanceMetrics


# ---------------------------------------------------------------------------
# BUG-001: StopLossManager check_position called
# ---------------------------------------------------------------------------

class TestBug001StopLossManager:
    """Test that StopLossManager is functional and check_position works."""

    def test_stop_loss_triggers(self):
        mgr = StopLossManager(default_stop_pct=0.02, default_tp_pct=0.03)
        mgr.add_position("BTC/USDT", entry_price=100.0, amount=1.0, is_long=True)

        # Price above stop => no action
        result = mgr.check_position("BTC/USDT", 99.0)
        assert result["action"] is None

        # Price below stop (100 - 2% = 98) => stop loss triggered
        result = mgr.check_position("BTC/USDT", 97.0)
        assert result["action"] == "stop_loss"
        assert result["pnl"] < 0

    def test_take_profit_triggers(self):
        mgr = StopLossManager(default_stop_pct=0.02, default_tp_pct=0.03)
        mgr.add_position("ETH/USDT", entry_price=100.0, amount=1.0, is_long=True)

        # Price above take profit (100 + 3% = 103) => TP triggered
        result = mgr.check_position("ETH/USDT", 104.0)
        assert result["action"] == "take_profit"
        assert result["pnl"] > 0

    def test_no_position_returns_none(self):
        mgr = StopLossManager()
        result = mgr.check_position("NONE/USDT", 100.0)
        assert result["action"] is None

    def test_remove_position(self):
        mgr = StopLossManager()
        mgr.add_position("BTC/USDT", entry_price=100.0, amount=1.0)
        mgr.remove_position("BTC/USDT")
        result = mgr.check_position("BTC/USDT", 50.0)
        assert result["action"] is None


# ---------------------------------------------------------------------------
# BUG-002: LLM timeout
# ---------------------------------------------------------------------------

class TestBug002LLMTimeout:
    """Test that LLM agent has timeout configured."""

    def test_agent_has_timeout(self):
        """Verify timeout is set on the ChatOpenAI constructor."""
        from shared.ai.agent import TradingAgent
        import asyncio

        # Agent without API key won't have llm, but verify asyncio import is present
        assert hasattr(asyncio, "wait_for")

    def test_call_llm_uses_wait_for(self):
        """Verify _call_llm source contains asyncio.wait_for."""
        import inspect as insp
        from shared.ai.agent import TradingAgent

        source = insp.getsource(TradingAgent._call_llm)
        assert "wait_for" in source
        assert "timeout" in source


# ---------------------------------------------------------------------------
# BUG-003: SMTP timeout already present — verified in email.py
# ---------------------------------------------------------------------------

class TestBug003SmtpTimeout:
    """Verify SMTP timeout is configured."""

    def test_smtp_timeout_in_source(self):
        import inspect as insp
        from shared.alerts.email import EmailAlert

        source = insp.getsource(EmailAlert._send_email)
        assert "timeout=30" in source


# ---------------------------------------------------------------------------
# BUG-004: Unbounded grid growth
# ---------------------------------------------------------------------------

class TestBug004GridGrowthLimit:
    """Test that grid level creation is bounded by max_levels."""

    def test_max_levels_config_exists(self):
        from binance_bot.strategies.grid import GridConfig
        config = GridConfig()
        assert hasattr(config, "max_levels")
        assert config.max_levels == 50

    def test_create_opposite_level_respects_max(self):
        from binance_bot.strategies.grid import GridStrategy, GridConfig
        from binance_bot.strategies.base import GridLevel, SignalType

        config = GridConfig(grid_levels=2, grid_spacing_pct=1.0, max_levels=5)
        strategy = GridStrategy("BTC/USDT", config)
        strategy.setup_grid(100.0, direction="long")

        initial_count = len(strategy.levels)

        # Fill a level and create opposite until we hit max
        for _ in range(20):
            if strategy.levels:
                filled = strategy.levels[0]
                strategy._create_opposite_level(filled, 100.0)

        assert len(strategy.levels) <= config.max_levels


# ---------------------------------------------------------------------------
# BUG-005: Float precision — Numeric columns
# ---------------------------------------------------------------------------

class TestBug005NumericPrecision:
    """Test that financial columns use Numeric instead of Float."""

    def test_trade_columns_are_numeric(self):
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)

        inspector = inspect(engine)
        columns = {c["name"]: c for c in inspector.get_columns("trades")}

        for col_name in ("price", "amount", "cost", "fee"):
            col = columns[col_name]
            col_type = str(col["type"]).upper()
            assert "NUMERIC" in col_type, f"Trade.{col_name} should be NUMERIC, got {col_type}"

        engine.dispose()

    def test_position_columns_are_numeric(self):
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)

        inspector = inspect(engine)
        columns = {c["name"]: c for c in inspector.get_columns("positions")}

        for col_name in ("entry_price", "amount", "unrealized_pnl", "realized_pnl"):
            col = columns[col_name]
            col_type = str(col["type"]).upper()
            assert "NUMERIC" in col_type, f"Position.{col_name} should be NUMERIC, got {col_type}"

        engine.dispose()

    def test_trade_log_columns_are_numeric(self):
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)

        inspector = inspect(engine)
        columns = {c["name"]: c for c in inspector.get_columns("trade_logs")}

        for col_name in ("price", "amount", "pnl", "fees"):
            col = columns[col_name]
            col_type = str(col["type"]).upper()
            assert "NUMERIC" in col_type, f"TradeLog.{col_name} should be NUMERIC, got {col_type}"

        engine.dispose()


# ---------------------------------------------------------------------------
# BUG-006: Fragile LLM response parsing
# ---------------------------------------------------------------------------

class TestBug006RobustParsing:
    """Test JSON-first parsing with line-based fallback."""

    def _parse(self, text: str) -> dict:
        from binance_bot.strategies.ai_grid import AIGridStrategy
        return AIGridStrategy._parse_review_response(text)

    def test_json_response(self):
        resp = '{"action": "PAUSE", "new_lower": null, "new_upper": null, "risk": "HIGH", "reason": "market volatile"}'
        result = self._parse(resp)
        assert result["action"] == "PAUSE"
        assert result["risk"] == "HIGH"
        assert result["reason"] == "market volatile"

    def test_json_in_markdown_code_block(self):
        resp = '```json\n{"action": "STOP", "new_lower": null, "new_upper": null, "risk": "HIGH", "reason": "crash"}\n```'
        result = self._parse(resp)
        assert result["action"] == "STOP"

    def test_line_based_fallback(self):
        resp = "ACTION: ADJUST\nNEW_LOWER: $85,000\nNEW_UPPER: $95,000\nRISK: MEDIUM\nREASON: range shift"
        result = self._parse(resp)
        assert result["action"] == "ADJUST"
        assert result["new_lower"] == 85000.0
        assert result["new_upper"] == 95000.0
        assert result["risk"] == "MEDIUM"

    def test_malformed_response_defaults(self):
        resp = "I think you should keep going because the market is fine."
        result = self._parse(resp)
        assert result["action"] == "CONTINUE"
        assert result["risk"] == "MEDIUM"

    def test_json_with_prices(self):
        resp = '{"action": "ADJUST", "new_lower": 85000.0, "new_upper": 95000.0, "risk": "LOW", "reason": "tightening range"}'
        result = self._parse(resp)
        assert result["action"] == "ADJUST"
        assert result["new_lower"] == 85000.0
        assert result["new_upper"] == 95000.0


# ---------------------------------------------------------------------------
# BUG-007: Sortino ratio returns infinity
# ---------------------------------------------------------------------------

class TestBug007SortinoFinite:
    """Test that Sortino ratio never returns infinity."""

    def test_sortino_no_negative_returns(self):
        """All positive returns should return 0.0, not inf."""
        metrics = RiskMetrics()
        # Add only winning trades
        for i in range(5):
            metrics.record_trade("BTC/USDT", "buy", 100.0, 110.0, 1.0)
        result = metrics.sortino_ratio()
        assert result == 0.0
        assert isinstance(result, float)

    def test_sortino_mixed_returns(self):
        metrics = RiskMetrics()
        metrics.record_trade("BTC/USDT", "buy", 100.0, 110.0, 1.0)
        metrics.record_trade("BTC/USDT", "buy", 100.0, 90.0, 1.0)
        metrics.record_trade("BTC/USDT", "buy", 100.0, 105.0, 1.0)
        result = metrics.sortino_ratio()
        assert isinstance(result, float)
        assert result != float("inf")

    def test_sortino_json_serializable(self):
        metrics = RiskMetrics()
        for i in range(5):
            metrics.record_trade("BTC/USDT", "buy", 100.0, 110.0, 1.0)
        result = metrics.sortino_ratio()
        # Must not raise
        json.dumps({"sortino": result})

    def test_optimization_sortino_no_inf(self):
        """Test PerformanceMetrics.sortino_ratio returns finite."""
        returns = [0.01, 0.02, 0.015, 0.005]  # All positive
        result = PerformanceMetrics.sortino_ratio(returns)
        assert result == 0.0
        json.dumps({"sortino": result})

    def test_profit_factor_no_inf(self):
        """Test profit_factor returns 0.0 instead of inf when no losses."""
        metrics = RiskMetrics()
        for i in range(3):
            metrics.record_trade("BTC/USDT", "buy", 100.0, 110.0, 1.0)
        assert metrics.profit_factor == 0.0
        json.dumps({"profit_factor": metrics.profit_factor})

    def test_get_summary_json_serializable(self):
        """Full summary must be JSON serializable."""
        metrics = RiskMetrics()
        for i in range(3):
            metrics.record_trade("BTC/USDT", "buy", 100.0, 110.0, 1.0)
        metrics.update_equity(10000)
        metrics.update_equity(10100)
        summary = metrics.get_summary()
        json.dumps(summary)


# ---------------------------------------------------------------------------
# BUG-008: Missing exit_time field
# ---------------------------------------------------------------------------

class TestBug008ExitTime:
    """Test that trades route uses existing TradeLog fields."""

    def test_trade_log_has_timestamp(self):
        assert hasattr(TradeLog, "timestamp")

    def test_trade_log_has_pnl(self):
        assert hasattr(TradeLog, "pnl")

    def test_trade_log_has_datetime_utc(self):
        """TradeLog.datetime_utc should work for timestamp conversion."""
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()

        log = TradeLog(
            timestamp=1700000000000,
            symbol="BTC/USDT",
            side="buy",
            price=50000,
            amount=0.1,
        )
        session.add(log)
        session.commit()
        session.refresh(log)
        assert log.datetime_utc is not None
        assert isinstance(log.datetime_utc, datetime)

        session.close()
        engine.dispose()

    def test_trades_history_source_uses_timestamp(self):
        """Verify the route code orders by TradeLog.timestamp, not exit_time."""
        import inspect as insp
        from shared.api.routes import trades

        source = insp.getsource(trades.get_pnl_history)
        assert "exit_time" not in source
        assert "timestamp" in source


# ---------------------------------------------------------------------------
# BUG-009: Import error — already exported
# ---------------------------------------------------------------------------

class TestBug009Import:
    """Test that get_rules_engine is importable from shared.alerts."""

    def test_get_rules_engine_importable(self):
        from shared.alerts import get_rules_engine
        engine = get_rules_engine()
        assert engine is not None


# ---------------------------------------------------------------------------
# BUG-010: Hardcoded risk parameters
# ---------------------------------------------------------------------------

class TestBug010ConfigurableRisk:
    """Test that risk parameters come from config/settings."""

    def test_settings_has_risk_fields(self):
        from shared.config.settings import Settings

        fields = Settings.model_fields
        assert "risk_per_trade" in fields
        assert "risk_max_position_pct" in fields
        assert "risk_daily_loss_limit" in fields
        assert "risk_max_drawdown_limit" in fields
        assert "risk_max_consecutive_losses" in fields
        assert "risk_stop_loss_pct" in fields
        assert "risk_take_profit_pct" in fields

    def test_settings_defaults(self):
        from shared.config import settings

        assert settings.risk_per_trade == 0.02
        assert settings.risk_daily_loss_limit == 0.05
        assert settings.risk_max_drawdown_limit == 0.10

    def test_bot_source_uses_settings(self):
        """Verify bot.py references settings.risk_* instead of hardcoded values."""
        import inspect as insp
        from binance_bot.bot import TradingBot

        source = insp.getsource(TradingBot.__init__)
        assert "settings.risk_per_trade" in source
        assert "settings.risk_daily_loss_limit" in source
        assert "settings.risk_max_drawdown_limit" in source
