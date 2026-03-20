"""Sprint 29: Architecture & Decoupling — Tests for all 11 issues."""

import importlib
import os
import re
import sys
import inspect
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest


# ─── Helpers ────────────────────────────────────────────────────────────────


def _make_ohlcv(n: int = 60, base: float = 85000.0) -> pd.DataFrame:
    """Create a simple OHLCV DataFrame for testing."""
    np.random.seed(42)
    close = base + np.cumsum(np.random.randn(n) * 100)
    return pd.DataFrame(
        {
            "open": close - np.random.rand(n) * 50,
            "high": close + np.abs(np.random.randn(n)) * 100,
            "low": close - np.abs(np.random.randn(n)) * 100,
            "close": close,
            "volume": np.random.rand(n) * 1000,
        },
        index=pd.date_range("2026-01-01", periods=n, freq="1h"),
    )


# ═══════════════════════════════════════════════════════════════════════════
# Issue 1: P1-BACK-1 — shared/ imports from binance_bot
# ═══════════════════════════════════════════════════════════════════════════


class TestP1Back1SharedImports:
    """shared/ must not import binance_bot at module level."""

    def test_shared_backtest_engine_no_toplevel_binance_import(self):
        """engine.py should NOT have top-level binance_bot imports."""
        src = Path(__file__).resolve().parents[2] / "shared" / "backtest" / "engine.py"
        text = src.read_text()

        # Find non-comment, non-TYPE_CHECKING import lines
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("if TYPE_CHECKING"):
                continue
            # Skip lines inside TYPE_CHECKING block (indented imports after it)
            # We only care about top-level (unindented) import statements
            if not line.startswith((" ", "\t")) and "from binance_bot" in stripped:
                pytest.fail(f"Top-level binance_bot import found: {stripped}")

    def test_shared_optimizer_no_toplevel_binance_import(self):
        """optimizer.py should NOT have top-level binance_bot imports."""
        src = Path(__file__).resolve().parents[2] / "shared" / "optimization" / "optimizer.py"
        text = src.read_text()

        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if not line.startswith((" ", "\t")) and "from binance_bot" in stripped:
                pytest.fail(f"Top-level binance_bot import found: {stripped}")


# ═══════════════════════════════════════════════════════════════════════════
# Issue 2: P1-STRAT-3 — Hardcoded BTC/USDT in order_manager
# ═══════════════════════════════════════════════════════════════════════════


class TestP1Strat3HardcodedSymbol:
    """execute_signal must use signal.symbol, not hardcoded BTC/USDT."""

    def test_signal_has_symbol_field(self):
        from binance_bot.strategies.base import Signal, SignalType

        sig = Signal(type=SignalType.BUY, price=100, amount=1, reason="test", symbol="ETH/USDT")
        assert sig.symbol == "ETH/USDT"

    def test_signal_default_symbol(self):
        from binance_bot.strategies.base import Signal, SignalType

        sig = Signal(type=SignalType.BUY, price=100, amount=1, reason="test")
        assert sig.symbol == "BTC/USDT"

    def test_execute_signal_uses_signal_symbol(self):
        """execute_signal should pass signal.symbol to order methods."""
        src = Path(__file__).resolve().parents[2] / "binance-bot" / "src" / "binance_bot" / "core" / "order_manager.py"
        text = src.read_text()

        # Find execute_signal method and check it uses signal.symbol
        in_method = False
        for line in text.splitlines():
            if "def execute_signal" in line:
                in_method = True
            elif in_method and line.strip().startswith("def "):
                break
            elif in_method:
                # Should not have hardcoded symbol="BTC/USDT" in the method body
                if 'symbol="BTC/USDT"' in line:
                    pytest.fail(f"Hardcoded BTC/USDT in execute_signal: {line.strip()}")


# ═══════════════════════════════════════════════════════════════════════════
# Issue 3: P1-STRAT-6 — No retry in ExchangeClient
# ═══════════════════════════════════════════════════════════════════════════


class TestP1Strat6ExchangeRetry:
    """ExchangeClient methods should have retry decorator."""

    def test_retry_decorator_exists(self):
        src = Path(__file__).resolve().parents[2] / "binance-bot" / "src" / "binance_bot" / "core" / "exchange.py"
        text = src.read_text()
        assert "_retry_on_network_error" in text

    def test_all_public_methods_decorated(self):
        """All public get_* methods should have retry decorator."""
        src = Path(__file__).resolve().parents[2] / "binance-bot" / "src" / "binance_bot" / "core" / "exchange.py"
        text = src.read_text()

        methods = ["get_balance", "get_all_balances", "get_ticker", "get_order_book", "get_ohlcv"]
        for method in methods:
            # Find the method and check previous line has decorator
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if f"def {method}" in line:
                    # Check decorator in preceding lines
                    found_decorator = False
                    for j in range(max(0, i - 3), i):
                        if "_retry_on_network_error" in lines[j]:
                            found_decorator = True
                            break
                    assert found_decorator, f"{method} missing retry decorator"

    def test_retry_no_catch_auth_error(self):
        """Retry should only catch NetworkError and ExchangeNotAvailable."""
        src = Path(__file__).resolve().parents[2] / "binance-bot" / "src" / "binance_bot" / "core" / "exchange.py"
        text = src.read_text()
        assert "AuthenticationError" not in text.split("def _retry_on_network_error")[1].split("class ")[0]


# ═══════════════════════════════════════════════════════════════════════════
# Issue 4: P1-STRAT-9 — Relative paths for emergency stop
# ═══════════════════════════════════════════════════════════════════════════


class TestP1Strat9EmergencyPaths:
    """Emergency paths should use configurable data directory."""

    def test_trigger_file_in_data_dir(self):
        from binance_bot.core.emergency import EmergencyStop

        assert ".emergency_stop" in str(EmergencyStop.TRIGGER_FILE)
        # Should be under data dir, not bare relative path
        assert str(EmergencyStop.TRIGGER_FILE) != ".emergency_stop"

    def test_state_file_in_data_dir(self):
        from binance_bot.core.emergency import EmergencyStop

        assert "emergency_state.json" in str(EmergencyStop.STATE_FILE)

    def test_custom_data_dir(self):
        """BOT_DATA_DIR env var should control paths."""
        src = Path(__file__).resolve().parents[2] / "binance-bot" / "src" / "binance_bot" / "core" / "emergency.py"
        text = src.read_text()
        assert "BOT_DATA_DIR" in text


# ═══════════════════════════════════════════════════════════════════════════
# Issue 5: P1-STRAT-10 — Hardcoded $0.01 tolerance
# ═══════════════════════════════════════════════════════════════════════════


class TestP1Strat10PriceTolerance:
    """_get_level_number should use relative tolerance."""

    def test_no_hardcoded_tolerance(self):
        """ai_grid.py should NOT have hardcoded 0.01 tolerance."""
        src = Path(__file__).resolve().parents[2] / "binance-bot" / "src" / "binance_bot" / "strategies" / "ai_grid.py"
        text = src.read_text()

        in_method = False
        for line in text.splitlines():
            if "_get_level_number" in line and "def " in line:
                in_method = True
            elif in_method and line.strip().startswith("def "):
                break
            elif in_method and "< 0.01" in line:
                pytest.fail("Hardcoded 0.01 tolerance still present")

    def test_level_matching_btc_price(self):
        """Levels at BTC prices should match with small offset."""
        from binance_bot.strategies.ai_grid import AIGridStrategy

        strategy = AIGridStrategy(symbol="BTC/USDT")
        strategy.setup_grid(85000.0)

        # Find a level and check matching with slight offset
        if strategy.levels:
            level_price = strategy.levels[0].price
            result = strategy._get_level_number(level_price + 0.001)
            assert result > 0, "Should match level at BTC price with tiny offset"

    def test_level_matching_cheap_token(self):
        """Levels at cheap token prices should use relative tolerance."""
        from binance_bot.strategies.ai_grid import AIGridStrategy, AIGridConfig

        config = AIGridConfig(grid_spacing_pct=5.0, amount_per_level=100)
        strategy = AIGridStrategy(symbol="DOGE/USDT", config=config)
        strategy.setup_grid(0.10)

        if strategy.levels:
            level_price = strategy.levels[0].price
            # Use an offset that's large relative to price (~3%) but doesn't land on another level
            # Tolerance is max(price * 0.001, 0.001) ~ 0.001 for cheap tokens
            # So 0.003 offset (~3% of $0.10) should NOT match
            result = strategy._get_level_number(level_price + 0.003)
            assert result == 0, "Should not match with 3% offset on cheap token"

    def test_level_matching_no_match(self):
        """Price far from any level should return 0."""
        from binance_bot.strategies.ai_grid import AIGridStrategy

        strategy = AIGridStrategy(symbol="BTC/USDT")
        strategy.setup_grid(85000.0)
        result = strategy._get_level_number(999999.0)
        assert result == 0


# ═══════════════════════════════════════════════════════════════════════════
# Issue 6: P1-STRAT-11 — Regex rejects nested JSON
# ═══════════════════════════════════════════════════════════════════════════


class TestP1Strat11NestedJson:
    """AI grid should parse nested JSON from LLM responses."""

    def test_parse_flat_json(self):
        from binance_bot.strategies.ai_grid import _extract_json

        result = _extract_json('{"action": "CONTINUE", "risk": "LOW"}')
        assert result is not None
        assert result["action"] == "CONTINUE"

    def test_parse_nested_json(self):
        from binance_bot.strategies.ai_grid import _extract_json

        result = _extract_json('{"action": "ADJUST", "params": {"lower": 80000}}')
        assert result is not None
        assert result["action"] == "ADJUST"
        assert result["params"]["lower"] == 80000

    def test_parse_json_in_markdown(self):
        from binance_bot.strategies.ai_grid import AIGridStrategy

        response = '```json\n{"action": "PAUSE", "risk": "HIGH", "reason": "test"}\n```'
        result = AIGridStrategy._parse_review_response(response)
        assert result["action"] == "PAUSE"

    def test_parse_no_json(self):
        from binance_bot.strategies.ai_grid import _extract_json

        result = _extract_json("Just a plain text response")
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# Issue 7: P1-AI-1 — LLM parsing false positives on negation
# ═══════════════════════════════════════════════════════════════════════════


class TestP1Ai1NegationParsing:
    """Market analysis should handle negated keywords."""

    def _agent(self):
        from shared.ai.agent import TradingAgent

        agent = TradingAgent.__new__(TradingAgent)
        agent.llm = None
        return agent

    def test_trend_bullish(self):
        agent = self._agent()
        result = agent._parse_market_analysis("The market is bullish", 85000, 86000, 84000)
        assert result.trend.value == "bullish"

    def test_trend_not_bullish(self):
        agent = self._agent()
        result = agent._parse_market_analysis("The market is not bullish", 85000, 86000, 84000)
        assert result.trend.value != "bullish"

    def test_trend_bearish(self):
        agent = self._agent()
        result = agent._parse_market_analysis("The market is bearish", 85000, 86000, 84000)
        assert result.trend.value == "bearish"

    def test_trend_bearish_negated(self):
        agent = self._agent()
        result = agent._parse_market_analysis("I don't think it's bearish", 85000, 86000, 84000)
        assert result.trend.value != "bearish"

    def test_risk_high(self):
        agent = self._agent()
        result = agent._parse_market_analysis("This is a high risk situation", 85000, 86000, 84000)
        assert result.risk_level.value == "high"

    def test_risk_not_high(self):
        agent = self._agent()
        result = agent._parse_market_analysis("Risk is not high, moderate at best", 85000, 86000, 84000)
        assert result.risk_level.value != "high"


# ═══════════════════════════════════════════════════════════════════════════
# Issue 8: P1-AI-2 — assess_risk is NOT dead code
# ═══════════════════════════════════════════════════════════════════════════


class TestP1Ai2AssessRiskNotDead:
    """assess_risk must exist and have caller documentation."""

    def test_assess_risk_exists(self):
        from shared.ai.agent import TradingAgent

        assert hasattr(TradingAgent, "assess_risk")
        assert callable(getattr(TradingAgent, "assess_risk"))

    def test_assess_risk_docstring_mentions_caller(self):
        from shared.ai.agent import TradingAgent

        docstring = TradingAgent.assess_risk.__doc__ or ""
        assert "jesse-bot" in docstring.lower() or "jesse" in docstring.lower(), \
            "assess_risk docstring should mention jesse-bot as caller"


# ═══════════════════════════════════════════════════════════════════════════
# Issue 9: P1-AI-3 — All LLM parsing should try JSON first
# ═══════════════════════════════════════════════════════════════════════════


class TestP1Ai3JsonFirstParsing:
    """All parsers should try JSON extraction first."""

    def _agent(self):
        from shared.ai.agent import TradingAgent

        agent = TradingAgent.__new__(TradingAgent)
        agent.llm = None
        return agent

    def test_try_parse_json_flat(self):
        agent = self._agent()
        result = agent._try_parse_json('{"trend": "bullish"}')
        assert result == {"trend": "bullish"}

    def test_try_parse_json_markdown(self):
        agent = self._agent()
        result = agent._try_parse_json('```json\n{"trend": "bearish"}\n```')
        assert result is not None
        assert result["trend"] == "bearish"

    def test_try_parse_json_nested(self):
        agent = self._agent()
        result = agent._try_parse_json('Here is the analysis: {"trend": "bullish", "details": {"rsi": 65}}')
        assert result is not None
        assert result["trend"] == "bullish"
        assert result["details"]["rsi"] == 65

    def test_try_parse_json_no_json(self):
        agent = self._agent()
        result = agent._try_parse_json("No JSON here at all")
        assert result is None

    def test_parse_market_json(self):
        agent = self._agent()
        response = '{"trend": "bullish", "risk": "low", "grid_recommended": true, "volatility_suitable": true}'
        result = agent._parse_market_analysis(response, 85000, 86000, 84000)
        assert result.trend.value == "bullish"
        assert result.risk_level.value == "low"
        assert result.grid_recommended is True

    def test_parse_market_markdown_json(self):
        agent = self._agent()
        response = '```json\n{"trend": "bearish", "risk": "high"}\n```'
        result = agent._parse_market_analysis(response, 85000, 86000, 84000)
        assert result.trend.value == "bearish"
        assert result.risk_level.value == "high"

    def test_parse_market_fallback_string(self):
        """String fallback should still work."""
        agent = self._agent()
        response = "The market is bullish with low risk"
        result = agent._parse_market_analysis(response, 85000, 86000, 84000)
        assert result.trend.value == "bullish"

    def test_parse_grid_json(self):
        agent = self._agent()
        response = '{"grid_lower": 80000, "grid_upper": 90000, "num_levels": 15, "confidence": 85}'
        result = agent._parse_grid_optimization(response, 82000, 88000, 10)
        assert result.lower_price == 80000
        assert result.upper_price == 90000
        assert result.num_levels == 15
        assert result.confidence == 85

    def test_parse_grid_fallback_lines(self):
        agent = self._agent()
        response = "GRID_LOWER: 80000\nGRID_UPPER: 90000\nNUM_LEVELS: 12\nCONFIDENCE: 75%"
        result = agent._parse_grid_optimization(response, 82000, 88000, 10)
        assert result.lower_price == 80000
        assert result.upper_price == 90000
        assert result.num_levels == 12

    def test_parse_risk_json(self):
        agent = self._agent()
        response = '{"risk_score": 7, "action": "HOLD", "stop_loss": 80000, "take_profit": 95000}'
        result = agent._parse_risk_assessment(response, 85000)
        assert result.risk_score == 7
        assert result.action == "HOLD"
        assert result.stop_loss == 80000
        assert result.take_profit == 95000

    def test_parse_risk_fallback_lines(self):
        agent = self._agent()
        response = "Risk Score: 6\nAction: REDUCE\nStop Loss: $82,000\nTake Profit: $92,000"
        result = agent._parse_risk_assessment(response, 85000)
        assert result.risk_score == 6
        assert result.action == "REDUCE"


# ═══════════════════════════════════════════════════════════════════════════
# Issue 10: P1-DASH-1 — time.sleep blocks Streamlit thread
# ═══════════════════════════════════════════════════════════════════════════


class TestP1Dash1NoSleep:
    """Dashboard should not use time.sleep for refresh."""

    def test_no_time_sleep_in_main(self):
        """app.py main() should not call time.sleep()."""
        src = Path(__file__).resolve().parents[2] / "shared" / "dashboard" / "app.py"
        text = src.read_text()

        # Find the main function
        in_main = False
        for line in text.splitlines():
            if "def main()" in line:
                in_main = True
            elif in_main and line.strip().startswith("def "):
                break
            elif in_main and "time.sleep" in line:
                pytest.fail("time.sleep() found in main()")


# ═══════════════════════════════════════════════════════════════════════════
# Issue 11: P3-STRAT-3 — Duplicate indicator implementations
# ═══════════════════════════════════════════════════════════════════════════


class TestP3Strat3DuplicateIndicators:
    """GridStrategy should use shared/indicators/ instead of inline calculations."""

    def test_detect_trend_uses_shared_ema(self):
        """detect_trend should call shared ema, not inline ewm."""
        src = Path(__file__).resolve().parents[2] / "binance-bot" / "src" / "binance_bot" / "strategies" / "grid.py"
        text = src.read_text()

        # Find detect_trend method body
        in_method = False
        method_body = []
        for line in text.splitlines():
            if "def detect_trend" in line:
                in_method = True
                continue
            elif in_method and (line.strip().startswith("def ") and not line.startswith(" " * 8)):
                break
            elif in_method:
                method_body.append(line)

        body = "\n".join(method_body)
        assert "shared_ema" in body or "shared_ema(" in body, "detect_trend should use shared ema"
        assert ".ewm(" not in body, "detect_trend should not have inline ewm calculation"

    def test_no_calculate_adx_method(self):
        """_calculate_adx should be removed (replaced by shared adx)."""
        src = Path(__file__).resolve().parents[2] / "binance-bot" / "src" / "binance_bot" / "strategies" / "grid.py"
        text = src.read_text()
        assert "def _calculate_adx" not in text, "_calculate_adx should be removed"

    def test_update_atr_uses_shared(self):
        """update_atr should call shared atr, not inline calculation."""
        src = Path(__file__).resolve().parents[2] / "binance-bot" / "src" / "binance_bot" / "strategies" / "grid.py"
        text = src.read_text()

        in_method = False
        method_body = []
        for line in text.splitlines():
            if "def update_atr" in line:
                in_method = True
                continue
            elif in_method and (line.strip().startswith("def ") and not line.startswith(" " * 8)):
                break
            elif in_method:
                method_body.append(line)

        body = "\n".join(method_body)
        assert "shared_atr" in body, "update_atr should use shared atr"
        # Should NOT have manual tr1/tr2/tr3 calculation
        assert "tr1" not in body, "update_atr should not have inline TR calculation"

    def test_detect_trend_still_works(self):
        """detect_trend should produce valid output with shared indicators."""
        from binance_bot.strategies.grid import GridStrategy

        strategy = GridStrategy()
        df = _make_ohlcv(60)
        result = strategy.detect_trend(df)
        assert result in ("bullish", "bearish", "sideways")

    def test_update_atr_still_works(self):
        """update_atr should compute a positive ATR with shared indicators."""
        from binance_bot.strategies.grid import GridStrategy

        strategy = GridStrategy()
        df = _make_ohlcv(30)
        strategy.update_atr(df)
        assert strategy.current_atr > 0

    def test_shared_imports_present(self):
        """grid.py should import from shared.indicators."""
        src = Path(__file__).resolve().parents[2] / "binance-bot" / "src" / "binance_bot" / "strategies" / "grid.py"
        text = src.read_text()
        assert "from shared.indicators" in text
