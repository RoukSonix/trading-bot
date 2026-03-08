"""
Tests for AlertsMixin and state_provider — Sprint M5.

Tests alert sending, backtest suppression, graceful fallback,
state export format, and state_provider output.
All tests mock external dependencies (no network).
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import numpy as np
import pytest

# Add strategy module to path
grid_logic_path = os.path.join(os.path.dirname(__file__), '..', 'strategies', 'AIGridStrategy')
sys.path.insert(0, grid_logic_path)

# Add jesse-bot root for state_provider
jesse_bot_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if jesse_bot_dir not in sys.path:
    sys.path.insert(0, jesse_bot_dir)

from alerts_mixin import AlertsMixin, _HAS_ALERTS
from state_provider import (
    get_bot_state, get_trade_history, write_state, export_state,
    _safe_serialize, DEFAULT_STATE_FILE,
)


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def alerts_mixin_live():
    """AlertsMixin configured as live (alerts enabled)."""
    with patch('alerts_mixin._HAS_ALERTS', True):
        mixin = AlertsMixin(is_live=True)
        # Mock the AlertManager to avoid real network calls
        mock_manager = MagicMock()
        mock_manager.send_trade_alert = AsyncMock(return_value=True)
        mock_manager.send_status_alert = AsyncMock(return_value=True)
        mock_manager.send_error_alert = AsyncMock(return_value=True)
        mock_manager.send_custom_alert = AsyncMock(return_value=True)
        mixin._alert_manager = mock_manager
        mixin._initialized = True
        return mixin


@pytest.fixture
def alerts_mixin_backtest():
    """AlertsMixin configured for backtesting (alerts suppressed)."""
    return AlertsMixin(is_live=False)


@pytest.fixture
def alerts_mixin_no_shared():
    """AlertsMixin without shared/alerts available."""
    with patch('alerts_mixin._HAS_ALERTS', False):
        mixin = AlertsMixin(is_live=True)
        return mixin


@pytest.fixture
def mock_strategy():
    """Mock Jesse strategy for state_provider tests."""
    strategy = MagicMock()
    strategy.symbol = 'BTC-USDT'
    strategy.exchange = 'Binance Perpetual Futures'
    strategy.balance = 10000.0
    strategy.available_margin = 9500.0
    strategy.price = 95000.0
    strategy.is_long = True

    # Position
    pos = MagicMock()
    pos.is_open = True
    pos.qty = 0.1
    pos.entry_price = 94000.0
    pos.pnl = 100.0
    pos.pnl_percentage = 1.06
    strategy.position = pos

    # Grid manager
    gm = MagicMock()
    gm.levels = [
        {'price': 94000.0, 'side': 'buy', 'filled': True},
        {'price': 95000.0, 'side': 'sell', 'filled': False},
        {'price': 96000.0, 'side': 'sell', 'filled': False},
    ]
    gm.direction = 'long_only'

    # Trailing stop
    tsm = MagicMock()
    tsm.active = True
    tsm.stop_price = 93500.0
    tsm.highest_price = 95200.0
    tsm.lowest_price = None

    strategy.vars = {
        'grid_manager': gm,
        'candle_count': 42,
        'last_factors': {
            'momentum_5d': 0.3,
            'volatility': 0.05,
            'rsi': 55.0,
            'volume_ratio': 1.2,
        },
        'last_sentiment': {
            'score': 0.4,
            'confidence': 0.7,
            'article_count': 5,
        },
        'last_ai_analysis': {
            'trend': 'uptrend',
            'confidence': 0.8,
            'recommendation': 'TRADE',
        },
        'trailing_stop': tsm,
    }

    # Trades
    trade1 = MagicMock()
    trade1.symbol = 'BTC-USDT'
    trade1.type = 'long'
    trade1.entry_price = 93000.0
    trade1.exit_price = 94500.0
    trade1.pnl = 150.0
    trade1.pnl_percentage = 1.61
    trade1.qty = 0.1
    trade1.opened_at = '2026-03-08T10:00:00'
    trade1.closed_at = '2026-03-08T12:00:00'
    strategy.trades = [trade1]

    return strategy


@pytest.fixture
def tmp_state_file(tmp_path):
    """Temporary state file path."""
    return tmp_path / "jesse_state.json"


# ==============================================================================
# AlertsMixin Tests
# ==============================================================================


class TestAlertsMixinLive:
    """Test alerts are sent in live mode."""

    def test_send_trade_alert(self, alerts_mixin_live):
        """Trade alert is sent in live mode."""
        alerts_mixin_live.send_trade_alert({
            'action': 'open',
            'symbol': 'BTC-USDT',
            'side': 'long',
            'price': 95000.0,
            'amount': 0.1,
        })
        alerts_mixin_live._alert_manager.send_trade_alert.assert_called_once()

    def test_send_trade_alert_with_pnl(self, alerts_mixin_live):
        """Trade alert includes PnL on position close."""
        alerts_mixin_live.send_trade_alert({
            'action': 'close',
            'symbol': 'BTC-USDT',
            'side': 'long',
            'price': 96000.0,
            'amount': 0.1,
            'pnl': 100.0,
            'pnl_pct': 1.05,
        })
        call_kwargs = alerts_mixin_live._alert_manager.send_trade_alert.call_args
        assert call_kwargs[1]['pnl'] == 100.0
        assert call_kwargs[1]['pnl_pct'] == 1.05

    def test_send_status_alert(self, alerts_mixin_live):
        """Status alert is sent in live mode."""
        alerts_mixin_live.send_status_alert({
            'status': 'running',
            'symbol': 'BTC-USDT',
            'current_price': 95000.0,
            'total_value': 10000.0,
        })
        alerts_mixin_live._alert_manager.send_status_alert.assert_called_once()

    def test_send_error_alert(self, alerts_mixin_live):
        """Error alert is sent in live mode."""
        alerts_mixin_live.send_error_alert("Test error", context="test")
        alerts_mixin_live._alert_manager.send_error_alert.assert_called_once_with(
            error="Test error", context="test", exc=None,
        )

    def test_send_error_alert_with_exception(self, alerts_mixin_live):
        """Error alert includes exception object."""
        exc = ValueError("bad value")
        alerts_mixin_live.send_error_alert("Test error", exc=exc)
        call_kwargs = alerts_mixin_live._alert_manager.send_error_alert.call_args
        assert call_kwargs[1]['exc'] is exc

    def test_send_ai_decision_alert(self, alerts_mixin_live):
        """AI decision alert is sent with fields."""
        # Mock AlertLevel since the real import may not be available
        mock_level = MagicMock()
        mock_level.INFO = "info"
        with patch('alerts_mixin.AlertLevel', mock_level):
            analysis = {
                'trend': 'uptrend',
                'confidence': 0.85,
                'recommendation': 'TRADE',
                'reasoning': 'Strong bullish momentum',
                'grid_params': {'direction': 'long_only'},
            }
            alerts_mixin_live.send_ai_decision_alert(analysis)
            alerts_mixin_live._alert_manager.send_custom_alert.assert_called_once()


class TestAlertsMixinBacktest:
    """Test alerts are suppressed during backtesting."""

    def test_trade_alert_suppressed(self, alerts_mixin_backtest):
        """Trade alerts not sent during backtest."""
        alerts_mixin_backtest.send_trade_alert({
            'action': 'open',
            'symbol': 'BTC-USDT',
            'side': 'long',
            'price': 95000.0,
            'amount': 0.1,
        })
        # No manager should be initialized
        assert alerts_mixin_backtest._alert_manager is None

    def test_status_alert_suppressed(self, alerts_mixin_backtest):
        """Status alerts not sent during backtest."""
        alerts_mixin_backtest.send_status_alert({'status': 'running'})
        assert alerts_mixin_backtest._alert_manager is None

    def test_error_alert_suppressed(self, alerts_mixin_backtest):
        """Error alerts not sent during backtest."""
        alerts_mixin_backtest.send_error_alert("Error", context="test")
        assert alerts_mixin_backtest._alert_manager is None

    def test_ai_decision_suppressed(self, alerts_mixin_backtest):
        """AI decision alerts not sent during backtest."""
        alerts_mixin_backtest.send_ai_decision_alert({'recommendation': 'TRADE'})
        assert alerts_mixin_backtest._alert_manager is None


class TestAlertsMixinFallback:
    """Test graceful fallback when shared/alerts unavailable."""

    def test_no_crash_without_shared(self, alerts_mixin_no_shared):
        """No crash when shared.alerts is not installed."""
        # Should just log warning and return
        alerts_mixin_no_shared.send_trade_alert({
            'symbol': 'BTC-USDT', 'side': 'long', 'price': 95000.0, 'amount': 0.1,
        })
        assert alerts_mixin_no_shared._alert_manager is None

    def test_ensure_init_returns_false(self, alerts_mixin_no_shared):
        """_ensure_init returns False when shared unavailable."""
        result = alerts_mixin_no_shared._ensure_init()
        assert result is False
        assert alerts_mixin_no_shared._initialized is True

    def test_should_send_false_without_shared(self, alerts_mixin_no_shared):
        """_should_send returns False when shared unavailable."""
        assert alerts_mixin_no_shared._should_send() is False

    def test_alert_manager_init_failure(self):
        """Graceful handling when AlertManager constructor raises."""
        with patch('alerts_mixin._HAS_ALERTS', True):
            with patch('alerts_mixin.AlertManager', side_effect=RuntimeError("init fail")):
                mixin = AlertsMixin(is_live=True)
                result = mixin._ensure_init()
                assert result is False
                assert mixin._alert_manager is None


# ==============================================================================
# State Provider Tests
# ==============================================================================


class TestGetBotState:
    """Test get_bot_state() output format."""

    def test_basic_fields(self, mock_strategy):
        """State contains all required top-level fields."""
        state = get_bot_state(mock_strategy)
        assert state['bot'] == 'jesse'
        assert state['symbol'] == 'BTC-USDT'
        assert state['balance'] == 10000.0
        assert state['current_price'] == 95000.0
        assert 'timestamp' in state

    def test_position_open(self, mock_strategy):
        """State includes open position details."""
        state = get_bot_state(mock_strategy)
        pos = state['position']
        assert pos['is_open'] is True
        assert pos['side'] == 'long'
        assert pos['entry_price'] == 94000.0
        assert pos['pnl'] == 100.0

    def test_position_closed(self, mock_strategy):
        """State shows closed position correctly."""
        mock_strategy.position.is_open = False
        state = get_bot_state(mock_strategy)
        assert state['position']['is_open'] is False

    def test_grid_levels(self, mock_strategy):
        """State includes grid levels from GridManager."""
        state = get_bot_state(mock_strategy)
        assert len(state['grid_levels']) == 3
        assert state['grid_levels'][0]['price'] == 94000.0
        assert state['grid_levels'][0]['filled'] is True
        assert state['grid_direction'] == 'long_only'

    def test_factors_included(self, mock_strategy):
        """State includes factor analysis data."""
        state = get_bot_state(mock_strategy)
        assert state['factors'] is not None
        assert state['factors']['rsi'] == 55.0

    def test_sentiment_included(self, mock_strategy):
        """State includes sentiment data."""
        state = get_bot_state(mock_strategy)
        assert state['sentiment'] is not None
        assert state['sentiment']['score'] == 0.4

    def test_ai_analysis_included(self, mock_strategy):
        """State includes last AI analysis."""
        state = get_bot_state(mock_strategy)
        assert state['last_ai_analysis'] is not None
        assert state['last_ai_analysis']['recommendation'] == 'TRADE'

    def test_trailing_stop_included(self, mock_strategy):
        """State includes trailing stop status."""
        state = get_bot_state(mock_strategy)
        ts = state['trailing_stop']
        assert ts is not None
        assert ts['active'] is True
        assert ts['stop_price'] == 93500.0

    def test_candle_count(self, mock_strategy):
        """State includes candle count."""
        state = get_bot_state(mock_strategy)
        assert state['candle_count'] == 42

    def test_no_grid_manager(self, mock_strategy):
        """State handles missing grid manager gracefully."""
        mock_strategy.vars['grid_manager'] = None
        state = get_bot_state(mock_strategy)
        assert state['grid_levels'] == []
        assert state['grid_direction'] == 'both'

    def test_no_factors(self, mock_strategy):
        """State handles missing factors gracefully."""
        mock_strategy.vars['last_factors'] = None
        state = get_bot_state(mock_strategy)
        assert state['factors'] is None

    def test_no_trailing_stop(self, mock_strategy):
        """State handles missing trailing stop gracefully."""
        mock_strategy.vars['trailing_stop'] = None
        state = get_bot_state(mock_strategy)
        assert state['trailing_stop'] is None


class TestGetTradeHistory:
    """Test get_trade_history() output."""

    def test_trade_history_format(self, mock_strategy):
        """Trade history returns list of dicts with correct fields."""
        trades = get_trade_history(mock_strategy)
        assert len(trades) == 1
        trade = trades[0]
        assert trade['symbol'] == 'BTC-USDT'
        assert trade['side'] == 'long'
        assert trade['entry_price'] == 93000.0
        assert trade['exit_price'] == 94500.0
        assert trade['pnl'] == 150.0

    def test_empty_trades(self, mock_strategy):
        """Returns empty list when no trades."""
        mock_strategy.trades = []
        trades = get_trade_history(mock_strategy)
        assert trades == []

    def test_trade_limit(self, mock_strategy):
        """Respects limit parameter."""
        mock_strategy.trades = [MagicMock() for _ in range(100)]
        trades = get_trade_history(mock_strategy, limit=10)
        assert len(trades) == 10

    def test_trade_history_error_handling(self, mock_strategy):
        """Handles errors gracefully."""
        mock_strategy.trades = None  # Will cause iteration error
        trades = get_trade_history(mock_strategy)
        assert trades == []


class TestWriteState:
    """Test atomic state file writing."""

    def test_write_and_read(self, tmp_state_file):
        """State can be written and read back."""
        state = {"bot": "jesse", "balance": 10000.0}
        write_state(state, tmp_state_file)

        with open(tmp_state_file) as f:
            loaded = json.load(f)

        assert loaded['bot'] == 'jesse'
        assert loaded['balance'] == 10000.0

    def test_atomic_write(self, tmp_state_file):
        """Write uses atomic rename (no partial writes)."""
        state = {"test": True}
        write_state(state, tmp_state_file)

        # File should exist
        assert tmp_state_file.exists()

        # No temp files should remain
        temp_files = list(tmp_state_file.parent.glob(".jesse_state_*.tmp"))
        assert len(temp_files) == 0

    def test_creates_directory(self, tmp_path):
        """Creates parent directory if needed."""
        nested_path = tmp_path / "deep" / "nested" / "state.json"
        write_state({"test": True}, nested_path)
        assert nested_path.exists()

    def test_overwrites_existing(self, tmp_state_file):
        """Overwrites existing state file."""
        write_state({"v": 1}, tmp_state_file)
        write_state({"v": 2}, tmp_state_file)

        with open(tmp_state_file) as f:
            loaded = json.load(f)
        assert loaded['v'] == 2


class TestExportState:
    """Test export_state() convenience function."""

    def test_export_writes_file(self, mock_strategy, tmp_state_file):
        """export_state writes state to file and returns dict."""
        state = export_state(mock_strategy, tmp_state_file)

        assert isinstance(state, dict)
        assert state['bot'] == 'jesse'
        assert 'trade_history' in state
        assert tmp_state_file.exists()

    def test_export_includes_trades(self, mock_strategy, tmp_state_file):
        """Exported state includes trade history."""
        state = export_state(mock_strategy, tmp_state_file)
        assert len(state['trade_history']) == 1


class TestSafeSerialize:
    """Test _safe_serialize handles edge cases."""

    def test_nan_replaced(self):
        """NaN is replaced with None."""
        assert _safe_serialize(float('nan')) is None

    def test_inf_replaced(self):
        """Infinity is replaced with None."""
        assert _safe_serialize(float('inf')) is None
        assert _safe_serialize(float('-inf')) is None

    def test_normal_float(self):
        """Normal floats pass through."""
        assert _safe_serialize(1.5) == 1.5

    def test_nested_dict(self):
        """Handles nested dicts with special values."""
        data = {'a': 1.0, 'b': float('nan'), 'c': {'d': float('inf')}}
        result = _safe_serialize(data)
        assert result == {'a': 1.0, 'b': None, 'c': {'d': None}}

    def test_list_with_special_values(self):
        """Handles lists with special values."""
        data = [1.0, float('nan'), 2.0]
        result = _safe_serialize(data)
        assert result == [1.0, None, 2.0]

    def test_numpy_int(self):
        """Handles numpy int types."""
        val = np.int64(42)
        result = _safe_serialize(val)
        assert result == 42
        assert isinstance(result, int)

    def test_numpy_float(self):
        """Handles numpy float types."""
        val = np.float64(3.14)
        result = _safe_serialize(val)
        assert result == pytest.approx(3.14)

    def test_numpy_nan(self):
        """Handles numpy NaN."""
        val = np.float64('nan')
        result = _safe_serialize(val)
        assert result is None


class TestStateExportInterval:
    """Test state export interval behavior."""

    def test_export_called_at_interval(self, mock_strategy, tmp_state_file):
        """export_state is called correctly at intervals."""
        # Simulate calling at different candle counts
        for candle in [10, 20, 30]:
            mock_strategy.vars['candle_count'] = candle
            state = export_state(mock_strategy, tmp_state_file)
            assert state['candle_count'] == candle

    def test_state_json_valid(self, mock_strategy, tmp_state_file):
        """Written state file is valid JSON."""
        export_state(mock_strategy, tmp_state_file)

        with open(tmp_state_file) as f:
            data = json.load(f)

        # Verify all top-level keys
        expected_keys = {
            'bot', 'timestamp', 'symbol', 'exchange', 'balance',
            'available_margin', 'current_price', 'position',
            'grid_levels', 'grid_direction', 'factors', 'sentiment',
            'last_ai_analysis', 'trailing_stop', 'candle_count',
            'trade_history',
        }
        assert expected_keys.issubset(set(data.keys()))
