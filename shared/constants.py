"""Centralized named constants for the trading bot system.

Replaces magic numbers scattered across modules with descriptive names.
"""

# ── Timing ──────────────────────────────────────────────────────────────────

TICK_INTERVAL_SEC = 5           # Seconds between price checks in main loop
RULES_CHECK_INTERVAL = 12      # Ticks between alert-rule evaluations (~1 min)
STATUS_UPDATE_INTERVAL = 60    # Ticks between status log prints (~5 min)

# ── RSI Thresholds ──────────────────────────────────────────────────────────

RSI_OVERSOLD = 30
RSI_WEAK_BEAR = 45
RSI_NEUTRAL = 50
RSI_WEAK_BULL = 55
RSI_OVERBOUGHT = 70

# ── Trend Detection ────────────────────────────────────────────────────────

ADX_STRONG_THRESHOLD = 25      # ADX above this = strong trend
MIN_CANDLES_TREND = 50         # Minimum candles needed for trend detection
TREND_SCORE_THRESHOLD = 4      # Minimum score to classify bullish/bearish

# ── Grid Bias Ratios ───────────────────────────────────────────────────────

GRID_BIAS_BEARISH = 0.3
GRID_BIAS_NEUTRAL = 0.5
GRID_BIAS_BULLISH = 0.7

# ── Position Precision ─────────────────────────────────────────────────────

MIN_POSITION_AMOUNT = 1e-8     # Positions below this are treated as zero
PRICE_MATCH_TOLERANCE = 0.001  # 0.1% tolerance for price matching

# ── AI Defaults ─────────────────────────────────────────────────────────────

AI_REVIEW_INTERVAL_MIN = 15
MIN_CONFIDENCE_DEFAULT = 50
MIN_CONFIDENCE_TRADE = 60
DEFAULT_ADJUSTMENT_CONFIDENCE = 70

# ── Grid Suitability ───────────────────────────────────────────────────────

MIN_GRID_SUITABILITY = 0.3
JESSE_MIN_GRID_SUITABILITY = 0.235

# ── Risk ────────────────────────────────────────────────────────────────────

HALF_KELLY_FACTOR = 0.5
RISK_WARNING_THRESHOLD = 0.7
ATR_STOP_MULTIPLIER = 2.0

# ── Retry / Network ────────────────────────────────────────────────────────

MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0
RETRY_BACKOFF_BASE = 2
LLM_TIMEOUT_SEC = 90

# ── Order Book / Data ──────────────────────────────────────────────────────

ORDER_BOOK_DEPTH_SMALL = 10
ORDER_BOOK_DEPTH_DEFAULT = 30
CANDLE_FETCH_LIMIT = 100

# ── Fallback Prices ────────────────────────────────────────────────────────

BID_FALLBACK_FACTOR = 0.999
ASK_FALLBACK_FACTOR = 1.001

# ── Volatility Filter ──────────────────────────────────────────────────────

MAX_ATR_VOLATILITY = 0.08      # Reject trades if ATR / price > 8%
MAX_GRID_FILL_PCT = 0.7        # Max fraction of grid levels that can be filled
