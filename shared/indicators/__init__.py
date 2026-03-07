"""Expanded indicator library (Sprint 23).

50+ technical indicators across trend, momentum, volatility, volume,
support/resistance, and candlestick pattern categories.
"""

from shared.indicators import (
    correlation,
    custom,
    momentum,
    multi_timeframe,
    pattern,
    support_resistance,
    trend,
    volatility,
    volume,
)
from shared.indicators.correlation import IndicatorCorrelation
from shared.indicators.custom import IndicatorBuilder
from shared.indicators.momentum import (
    ao,
    macd,
    mfi,
    momentum as simple_momentum,
    roc,
    rsi,
    stoch_rsi,
    stochastic,
    tsi,
    ultimate,
    williams_r,
)
from shared.indicators.multi_timeframe import MultiTimeframe
from shared.indicators.pattern import (
    doji,
    engulfing,
    hammer,
    morning_star,
    three_soldiers,
)
from shared.indicators.support_resistance import (
    fibonacci_extension,
    fibonacci_retracement,
    pivot_points,
    support_resistance_levels,
)
from shared.indicators.trend import (
    adx,
    aroon,
    cci,
    dema,
    ema,
    ichimoku,
    kama,
    psar,
    sma,
    supertrend,
    tema,
    vwap,
    wma,
)
from shared.indicators.volatility import (
    atr,
    atr_percent,
    bollinger_bands,
    chaikin_volatility,
    donchian,
    historical_volatility,
    keltner,
    natr,
    true_range,
)
from shared.indicators.volume import (
    ad_line,
    cmf,
    eom,
    force_index,
    nvi,
    obv,
    pvt,
    volume_profile,
)

# Also export vwap from volume module under explicit name
from shared.indicators.volume import vwap as volume_vwap

__all__ = [
    # Modules
    "trend", "momentum", "volatility", "volume",
    "support_resistance", "pattern", "custom",
    "multi_timeframe", "correlation",
    # Trend
    "sma", "ema", "wma", "dema", "tema", "kama", "vwap",
    "supertrend", "psar", "ichimoku", "adx", "aroon", "cci",
    # Momentum
    "rsi", "macd", "stochastic", "stoch_rsi", "williams_r",
    "mfi", "roc", "tsi", "ultimate", "ao", "simple_momentum",
    # Volatility
    "atr", "true_range", "bollinger_bands", "keltner", "donchian",
    "atr_percent", "historical_volatility", "chaikin_volatility", "natr",
    # Volume
    "obv", "volume_vwap", "ad_line", "cmf", "force_index",
    "eom", "volume_profile", "pvt", "nvi",
    # Support/Resistance
    "pivot_points", "fibonacci_retracement", "fibonacci_extension",
    "support_resistance_levels",
    # Pattern
    "doji", "hammer", "engulfing", "morning_star", "three_soldiers",
    # Custom & Multi-timeframe
    "IndicatorBuilder", "MultiTimeframe", "IndicatorCorrelation",
]
