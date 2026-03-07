"""Unit tests for multi-strategy engine (Sprint 22)."""

import pytest

from shared.strategies.base import StrategyInterface
from shared.strategies.momentum_strategy import MomentumStrategy
from shared.strategies.mean_reversion_strategy import MeanReversionStrategy
from shared.strategies.breakout_strategy import BreakoutStrategy
from shared.strategies.grid_strategy import GridStrategyAdapter
from shared.strategies.regime import MarketRegime, MarketRegimeDetector
from shared.strategies.engine import StrategyEngine
from shared.strategies.registry import StrategyRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def momentum():
    return MomentumStrategy()


@pytest.fixture
def mean_reversion():
    return MeanReversionStrategy()


@pytest.fixture
def breakout():
    return BreakoutStrategy()


@pytest.fixture
def grid_adapter():
    return GridStrategyAdapter()


@pytest.fixture
def engine():
    """Pre-loaded strategy engine with all built-in strategies."""
    eng = StrategyEngine()
    for name in StrategyRegistry.list_all():
        eng.register(StrategyRegistry.get(name))
    return eng


def _make_candles(close: float = 50000.0, volume: float = 500.0, n: int = 5):
    """Helper to create a list of candle dicts."""
    return [
        {"open": close, "high": close * 1.01, "low": close * 0.99, "close": close, "volume": volume}
        for _ in range(n)
    ]


# ---------------------------------------------------------------------------
# Momentum Strategy
# ---------------------------------------------------------------------------

class TestMomentumStrategy:
    def test_should_long_bullish(self, momentum):
        """Long when fast EMA > slow EMA and RSI < 70."""
        indicators = {"ema_8": 51000, "ema_21": 50000, "rsi_14": 55}
        assert momentum.should_long(_make_candles(), indicators) is True

    def test_should_not_long_overbought(self, momentum):
        """No long when RSI >= 70 even if EMAs are bullish."""
        indicators = {"ema_8": 51000, "ema_21": 50000, "rsi_14": 75}
        assert momentum.should_long(_make_candles(), indicators) is False

    def test_should_short_bearish(self, momentum):
        """Short when fast EMA < slow EMA and RSI > 30."""
        indicators = {"ema_8": 49000, "ema_21": 50000, "rsi_14": 45}
        assert momentum.should_short(_make_candles(), indicators) is True

    def test_should_not_short_oversold(self, momentum):
        """No short when RSI <= 30."""
        indicators = {"ema_8": 49000, "ema_21": 50000, "rsi_14": 25}
        assert momentum.should_short(_make_candles(), indicators) is False

    def test_go_long_returns_dict(self, momentum):
        momentum.set_price(50000)
        result = momentum.go_long()
        assert result["side"] == "long"
        assert result["entry"] == pytest.approx(50000 * 0.999)
        assert result["qty_pct"] == 0.05

    def test_go_short_returns_dict(self, momentum):
        momentum.set_price(50000)
        result = momentum.go_short()
        assert result["side"] == "short"
        assert result["entry"] == pytest.approx(50000 * 1.001)

    def test_implements_interface(self, momentum):
        assert isinstance(momentum, StrategyInterface)

    def test_name(self, momentum):
        assert momentum.name == "MomentumStrategy"


# ---------------------------------------------------------------------------
# Mean Reversion Strategy
# ---------------------------------------------------------------------------

class TestMeanReversionStrategy:
    def test_should_long_oversold(self, mean_reversion):
        """Long when price < BB lower and RSI < 30."""
        candles = _make_candles(close=48000)
        indicators = {"bb_lower": 49000, "rsi_14": 25}
        assert mean_reversion.should_long(candles, indicators) is True

    def test_should_not_long_normal(self, mean_reversion):
        """No long when price above BB lower."""
        candles = _make_candles(close=50000)
        indicators = {"bb_lower": 49000, "rsi_14": 50}
        assert mean_reversion.should_long(candles, indicators) is False

    def test_should_short_overbought(self, mean_reversion):
        """Short when price > BB upper and RSI > 70."""
        candles = _make_candles(close=52000)
        indicators = {"bb_upper": 51000, "rsi_14": 75}
        assert mean_reversion.should_short(candles, indicators) is True

    def test_should_not_short_normal(self, mean_reversion):
        """No short when price below BB upper."""
        candles = _make_candles(close=50000)
        indicators = {"bb_upper": 51000, "rsi_14": 50}
        assert mean_reversion.should_short(candles, indicators) is False

    def test_go_long_signal(self, mean_reversion):
        mean_reversion.set_price(48000)
        result = mean_reversion.go_long()
        assert result["side"] == "long"
        assert result["entry"] == 48000


# ---------------------------------------------------------------------------
# Breakout Strategy
# ---------------------------------------------------------------------------

class TestBreakoutStrategy:
    def test_should_long_breakout(self, breakout):
        """Long when price exceeds 20-period high."""
        candles = _make_candles(close=51000)
        indicators = {"highest_20": 50500}
        assert breakout.should_long(candles, indicators) is True

    def test_should_not_long_below(self, breakout):
        """No long when price below 20-period high."""
        candles = _make_candles(close=50000)
        indicators = {"highest_20": 50500}
        assert breakout.should_long(candles, indicators) is False

    def test_should_short_breakdown(self, breakout):
        """Short when price drops below 20-period low."""
        candles = _make_candles(close=49000)
        indicators = {"lowest_20": 49500}
        assert breakout.should_short(candles, indicators) is True

    def test_should_not_short_above(self, breakout):
        """No short when price above 20-period low."""
        candles = _make_candles(close=50000)
        indicators = {"lowest_20": 49500}
        assert breakout.should_short(candles, indicators) is False


# ---------------------------------------------------------------------------
# Market Regime Detection
# ---------------------------------------------------------------------------

class TestRegimeDetection:
    def test_ranging_default(self):
        """Default to RANGING when no strong signals."""
        detector = MarketRegimeDetector()
        candles = _make_candles()
        indicators = {
            "adx": 15,
            "atr": 500,
            "bb_upper": 51000,
            "bb_lower": 49000,
            "bb_middle": 50000,
            "ema_8": 50000,
            "ema_21": 50000,
            "rsi_14": 50,
            "highest_20": 52000,
            "lowest_20": 48000,
            "volume_sma": 500,
        }
        regime = detector.detect(candles, indicators)
        assert regime == MarketRegime.RANGING

    def test_trending_up(self):
        """TRENDING_UP when ADX > 25 and fast EMA > slow EMA."""
        detector = MarketRegimeDetector()
        candles = _make_candles()
        indicators = {
            "adx": 30,
            "atr": 700,
            "bb_upper": 51500,
            "bb_lower": 48500,
            "bb_middle": 50000,
            "ema_8": 51000,
            "ema_21": 49500,
            "rsi_14": 55,
            "highest_20": 52000,
            "lowest_20": 48000,
            "volume_sma": 500,
        }
        regime = detector.detect(candles, indicators)
        assert regime == MarketRegime.TRENDING_UP

    def test_trending_down(self):
        """TRENDING_DOWN when ADX > 25 and fast EMA < slow EMA."""
        detector = MarketRegimeDetector()
        candles = _make_candles()
        indicators = {
            "adx": 30,
            "atr": 700,
            "bb_upper": 51500,
            "bb_lower": 48500,
            "bb_middle": 50000,
            "ema_8": 49000,
            "ema_21": 50500,
            "rsi_14": 45,
            "highest_20": 52000,
            "lowest_20": 48000,
            "volume_sma": 500,
        }
        regime = detector.detect(candles, indicators)
        assert regime == MarketRegime.TRENDING_DOWN

    def test_high_volatility(self):
        """HIGH_VOLATILITY when ATR/price > 3%."""
        detector = MarketRegimeDetector()
        candles = _make_candles(close=50000)
        indicators = {
            "adx": 20,
            "atr": 2000,  # 4% of price
            "bb_upper": 55000,
            "bb_lower": 45000,
            "bb_middle": 50000,
            "ema_8": 50000,
            "ema_21": 50000,
            "rsi_14": 50,
            "highest_20": 52000,
            "lowest_20": 48000,
            "volume_sma": 500,
        }
        regime = detector.detect(candles, indicators)
        assert regime == MarketRegime.HIGH_VOLATILITY

    def test_breakout(self):
        """BREAKOUT when price >= highest_20 and volume spike."""
        detector = MarketRegimeDetector()
        candles = _make_candles(close=53000, volume=1000)
        indicators = {
            "adx": 20,
            "atr": 500,
            "bb_upper": 51000,
            "bb_lower": 49000,
            "bb_middle": 50000,
            "ema_8": 50500,
            "ema_21": 50000,
            "rsi_14": 55,
            "highest_20": 52000,
            "lowest_20": 48000,
            "volume_sma": 500,  # current 1000 > 500 * 1.5
        }
        regime = detector.detect(candles, indicators)
        assert regime == MarketRegime.BREAKOUT

    def test_low_volatility(self):
        """LOW_VOLATILITY when BB width < 2%."""
        detector = MarketRegimeDetector()
        candles = _make_candles(close=50000)
        indicators = {
            "adx": 10,
            "atr": 200,
            "bb_upper": 50400,
            "bb_lower": 49600,
            "bb_middle": 50000,
            "ema_8": 50000,
            "ema_21": 50000,
            "rsi_14": 50,
            "highest_20": 51000,
            "lowest_20": 49000,
            "volume_sma": 500,
        }
        regime = detector.detect(candles, indicators)
        assert regime == MarketRegime.LOW_VOLATILITY

    def test_empty_candles(self):
        """Return RANGING for empty candles."""
        detector = MarketRegimeDetector()
        regime = detector.detect([], {})
        assert regime == MarketRegime.RANGING


# ---------------------------------------------------------------------------
# Strategy Selection
# ---------------------------------------------------------------------------

class TestStrategySelection:
    def test_selects_momentum_for_trending(self, engine):
        """Momentum selected for trending market."""
        candles = _make_candles()
        indicators = {
            "adx": 30, "atr": 700,
            "bb_upper": 51500, "bb_lower": 48500, "bb_middle": 50000,
            "ema_8": 51000, "ema_21": 49500,
            "rsi_14": 55,
            "highest_20": 52000, "lowest_20": 48000, "volume_sma": 500,
        }
        strategy = engine.select_strategy(candles, indicators)
        assert strategy.name == "MomentumStrategy"

    def test_selects_grid_for_ranging(self, engine):
        """Grid selected for ranging market."""
        candles = _make_candles()
        indicators = {
            "adx": 15, "atr": 500,
            "bb_upper": 51000, "bb_lower": 49000, "bb_middle": 50000,
            "ema_8": 50000, "ema_21": 50000,
            "rsi_14": 50,
            "highest_20": 52000, "lowest_20": 48000, "volume_sma": 500,
        }
        strategy = engine.select_strategy(candles, indicators)
        assert strategy.name == "GridStrategyAdapter"

    def test_selects_mean_reversion_for_oversold(self, engine):
        """Mean reversion selected when RSI < 30."""
        candles = _make_candles()
        indicators = {
            "adx": 15, "atr": 500,
            "bb_upper": 51000, "bb_lower": 49000, "bb_middle": 50000,
            "ema_8": 50000, "ema_21": 50000,
            "rsi_14": 25,  # Oversold
            "highest_20": 52000, "lowest_20": 48000, "volume_sma": 500,
        }
        strategy = engine.select_strategy(candles, indicators)
        assert strategy.name == "MeanReversionStrategy"

    def test_selects_breakout_for_breakout(self, engine):
        """Breakout selected for breakout regime."""
        candles = _make_candles(close=53000, volume=1000)
        indicators = {
            "adx": 20, "atr": 500,
            "bb_upper": 51000, "bb_lower": 49000, "bb_middle": 50000,
            "ema_8": 50500, "ema_21": 50000,
            "rsi_14": 60,
            "highest_20": 52000, "lowest_20": 48000, "volume_sma": 500,
        }
        strategy = engine.select_strategy(candles, indicators)
        assert strategy.name == "BreakoutStrategy"


# ---------------------------------------------------------------------------
# Hot Swap
# ---------------------------------------------------------------------------

class TestHotSwap:
    def test_hot_swap_success(self, engine):
        """Hot swap to registered strategy succeeds."""
        assert engine.hot_swap("MomentumStrategy") is True
        assert engine.active_strategy_name == "MomentumStrategy"

    def test_hot_swap_unknown_fails(self, engine):
        """Hot swap to unknown strategy fails."""
        assert engine.hot_swap("DoesNotExist") is False

    def test_hot_swap_records_history(self, engine):
        engine.hot_swap("MomentumStrategy")
        engine.hot_swap("BreakoutStrategy")
        status = engine.get_status()
        assert status["strategy_switches"] == 2
        assert status["switch_history"][-1]["to"] == "BreakoutStrategy"


# ---------------------------------------------------------------------------
# Strategy Registry
# ---------------------------------------------------------------------------

class TestStrategyRegistry:
    def test_list_all(self):
        strategies = StrategyRegistry.list_all()
        assert "grid" in strategies
        assert "momentum" in strategies
        assert "mean_reversion" in strategies
        assert "breakout" in strategies

    def test_get_momentum(self):
        s = StrategyRegistry.get("momentum")
        assert isinstance(s, MomentumStrategy)
        assert isinstance(s, StrategyInterface)

    def test_get_unknown_raises(self):
        with pytest.raises(KeyError):
            StrategyRegistry.get("unknown_strategy")

    def test_register_custom(self):
        """Custom strategies can be registered."""
        class MyStrategy(StrategyInterface):
            def should_long(self, c, i): return False
            def should_short(self, c, i): return False
            def go_long(self): return {}
            def go_short(self): return {}
            def should_cancel_entry(self): return False

        StrategyRegistry.register("custom", MyStrategy)
        assert "custom" in StrategyRegistry.list_all()
        s = StrategyRegistry.get("custom")
        assert isinstance(s, MyStrategy)

        # Cleanup
        del StrategyRegistry.STRATEGIES["custom"]
