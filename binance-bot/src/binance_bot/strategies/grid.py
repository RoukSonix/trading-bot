"""Grid Trading Strategy.

Grid trading places buy orders below the current price and sell orders above it.
When price moves and hits a level, it triggers a trade and creates a new level
on the opposite side to capture the reversal.

Supports bi-directional trading (long + short) with automatic trend detection.
Works best in sideways/ranging markets with clear support and resistance.
"""

from dataclasses import dataclass, field
from typing import Optional
import time
import numpy as np
import pandas as pd
from loguru import logger

from binance_bot.strategies.base import BaseStrategy, Signal, SignalType, GridLevel
from shared.core.database import SessionLocal, Trade, Position
from shared.risk.tp_sl import TPSLCalculator
from shared.risk.trailing_stop import TrailingStopManager
from shared.risk.break_even import BreakEvenManager


@dataclass
class GridConfig:
    """Grid strategy configuration."""

    # Grid parameters
    grid_levels: int = 10           # Number of grid levels on each side
    grid_spacing_pct: float = 1.0   # Spacing between levels (%)

    # Position sizing
    amount_per_level: float = 0.001  # Amount to trade at each level (in base currency)

    # Bounds (optional - if not set, calculated from current price)
    upper_price: Optional[float] = None
    lower_price: Optional[float] = None

    # Risk management
    max_position: float = 0.1       # Maximum total position size
    stop_loss_pct: float = 10.0     # Stop loss percentage from entry

    # Grid growth limit
    max_levels: int = 50            # Maximum total grid levels to prevent unbounded growth

    # Bi-directional grid (Sprint 20)
    direction: str = "both"         # "long", "short", "both"
    leverage: float = 1.0           # 1x = spot, 2x-3x = margin
    trend_bias: bool = True         # Auto-detect trend for direction bias

    # Per-level TP/SL (Sprint 21)
    tp_mode: str = "atr"            # "fixed", "atr", "rr_ratio"
    sl_mode: str = "atr"            # "fixed", "atr"
    tp_pct: float = 2.0             # For fixed mode
    sl_pct: float = 1.0             # For fixed mode
    tp_atr_mult: float = 2.0        # For ATR mode
    sl_atr_mult: float = 1.0        # For ATR mode
    trailing_enabled: bool = True
    trailing_pct: float = 1.0
    trailing_activation_pct: float = 0.5
    break_even_enabled: bool = True
    break_even_pct: float = 1.0
    break_even_offset_pct: float = 0.1


class GridStrategy(BaseStrategy):
    """Grid Trading Strategy implementation."""

    name = "GridStrategy"

    def __init__(
        self,
        symbol: str = "BTC/USDT",
        config: Optional[GridConfig] = None,
    ):
        """Initialize grid strategy.

        Args:
            symbol: Trading pair
            config: Grid configuration
        """
        super().__init__(symbol)
        self.config = config or GridConfig()

        # Grid state
        self.levels: list[GridLevel] = []
        self.center_price: Optional[float] = None
        self.total_position: float = 0.0
        self.realized_pnl: float = 0.0

        # Paper trading state
        self.paper_balance: float = 10000.0  # Starting USDT
        self.paper_holdings: float = 0.0     # BTC holdings (long)
        self.paper_trades: list[dict] = []

        # Short position tracking (Sprint 20)
        self.long_holdings: float = 0.0
        self.short_holdings: float = 0.0
        self.long_entry_price: float = 0.0
        self.short_entry_price: float = 0.0

        # TP/SL managers (Sprint 21)
        self.current_atr: float = 0.0
        self.tp_sl_calc = TPSLCalculator()
        self.trailing_mgr = TrailingStopManager(
            trail_pct=self.config.trailing_pct,
            activation_pct=self.config.trailing_activation_pct,
        )
        self.break_even_mgr = BreakEvenManager(
            activation_pct=self.config.break_even_pct,
            offset_pct=self.config.break_even_offset_pct,
        )
        self.tp_sl_alerts: list[dict] = []  # Pending TP/SL alert events

    def setup_grid(self, current_price: float, direction: Optional[str] = None) -> list[GridLevel]:
        """Set up grid levels around current price.

        Args:
            current_price: Current market price
            direction: Override direction ("long", "short", "both").
                       If None, uses config.direction.

        Returns:
            List of grid levels
        """
        self.center_price = current_price
        self.levels = []

        direction = direction or self.config.direction

        if direction in ("long", "both"):
            self._setup_long_levels(current_price)
        if direction in ("short", "both"):
            self._setup_short_levels(current_price)

        # Sort by price
        self.levels.sort(key=lambda x: x.price)

        logger.info(f"Grid setup: {len(self.levels)} levels around ${current_price:,.2f} (direction={direction})")
        if self.levels:
            logger.info(f"  Range: ${self.levels[0].price:,.2f} - ${self.levels[-1].price:,.2f}")
        logger.info(f"  Spacing: {self.config.grid_spacing_pct}% ")

        return self.levels

    def _setup_long_levels(self, center_price: float):
        """Set up long grid: BUY levels below center, SELL (TP) levels above."""
        spacing = center_price * (self.config.grid_spacing_pct / 100)

        # Buy levels below current price
        for i in range(1, self.config.grid_levels + 1):
            price = center_price - (spacing * i)
            level = GridLevel(
                price=price,
                side=SignalType.BUY,
                amount=self.config.amount_per_level,
            )
            self.levels.append(level)

        # Sell (take profit) levels above current price
        for i in range(1, self.config.grid_levels + 1):
            price = center_price + (spacing * i)
            level = GridLevel(
                price=price,
                side=SignalType.SELL,
                amount=self.config.amount_per_level,
            )
            self.levels.append(level)

    def _setup_short_levels(self, center_price: float):
        """Set up short grid: SELL levels above center, BUY (TP) levels below.

        For short grid, SELL levels open short positions above price,
        and BUY levels close (take profit) shorts below price.
        These are tagged with is_short=True via negative amount convention:
        negative amount signals a short-side level.
        """
        spacing = center_price * (self.config.grid_spacing_pct / 100)

        # Short-sell levels above current price (open short)
        for i in range(1, self.config.grid_levels + 1):
            price = center_price + (spacing * i)
            level = GridLevel(
                price=price,
                side=SignalType.SELL,
                amount=-self.config.amount_per_level,  # Negative = short
            )
            self.levels.append(level)

        # Buy-to-cover levels below current price (close short)
        for i in range(1, self.config.grid_levels + 1):
            price = center_price - (spacing * i)
            level = GridLevel(
                price=price,
                side=SignalType.BUY,
                amount=-self.config.amount_per_level,  # Negative = short
            )
            self.levels.append(level)

    def detect_trend(self, ohlcv_df: pd.DataFrame) -> str:
        """Detect market trend using multiple indicators.

        Returns: "bullish", "bearish", or "sideways"

        Uses:
        - EMA 20 vs EMA 50 crossover
        - Price position relative to EMAs
        - ADX for trend strength
        - RSI divergence
        """
        if len(ohlcv_df) < 50:
            return "sideways"

        close = ohlcv_df["close"]
        high = ohlcv_df["high"]
        low = ohlcv_df["low"]

        # EMA crossover
        ema_20 = close.ewm(span=20, adjust=False).mean()
        ema_50 = close.ewm(span=50, adjust=False).mean()

        ema_bullish = ema_20.iloc[-1] > ema_50.iloc[-1]
        ema_bearish = ema_20.iloc[-1] < ema_50.iloc[-1]

        # Price position relative to EMAs
        current_price = close.iloc[-1]
        price_above_ema20 = current_price > ema_20.iloc[-1]
        price_above_ema50 = current_price > ema_50.iloc[-1]

        # ADX for trend strength
        adx = self._calculate_adx(high, low, close, period=14)
        strong_trend = adx > 25

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi = rsi.fillna(100.0)
        current_rsi = rsi.iloc[-1]

        # Scoring
        bull_score = 0
        bear_score = 0

        if ema_bullish:
            bull_score += 2
        if ema_bearish:
            bear_score += 2
        if price_above_ema20:
            bull_score += 1
        else:
            bear_score += 1
        if price_above_ema50:
            bull_score += 1
        else:
            bear_score += 1
        if current_rsi > 55:
            bull_score += 1
        elif current_rsi < 45:
            bear_score += 1

        if not strong_trend:
            return "sideways"

        if bull_score >= 4:
            return "bullish"
        elif bear_score >= 4:
            return "bearish"
        return "sideways"

    def _calculate_adx(self, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
        """Calculate ADX (Average Directional Index)."""
        plus_dm = high.diff()
        minus_dm = -low.diff()

        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr = tr.ewm(alpha=1/period, min_periods=period).mean()
        plus_di = 100 * (plus_dm.ewm(alpha=1/period, min_periods=period).mean() / atr)
        minus_di = 100 * (minus_dm.ewm(alpha=1/period, min_periods=period).mean() / atr)

        di_sum = (plus_di + minus_di).replace(0, np.nan)
        dx = 100 * ((plus_di - minus_di).abs() / di_sum)
        dx = dx.fillna(0.0)
        adx = dx.ewm(alpha=1/period, min_periods=period).mean()

        return float(adx.iloc[-1]) if not np.isnan(adx.iloc[-1]) else 0.0

    def get_grid_bias(self, trend: str) -> tuple[float, float]:
        """Convert trend to grid direction bias.

        Args:
            trend: "bullish", "bearish", or "sideways"

        Returns:
            Tuple of (long_ratio, short_ratio) that sum to 1.0
            bullish  → 70% long levels, 30% short
            bearish  → 30% long levels, 70% short
            sideways → 50/50
        """
        if trend == "bullish":
            return (0.7, 0.3)
        elif trend == "bearish":
            return (0.3, 0.7)
        else:
            return (0.5, 0.5)

    def setup_grid_with_trend(self, current_price: float, ohlcv_df: pd.DataFrame) -> list[GridLevel]:
        """Set up grid with trend-based bias on level allocation.

        Args:
            current_price: Current market price
            ohlcv_df: OHLCV DataFrame for trend detection

        Returns:
            List of grid levels
        """
        if not self.config.trend_bias or self.config.direction != "both":
            return self.setup_grid(current_price)

        trend = self.detect_trend(ohlcv_df)
        long_ratio, short_ratio = self.get_grid_bias(trend)

        self.center_price = current_price
        self.levels = []

        total_levels = self.config.grid_levels
        long_levels = max(1, int(total_levels * long_ratio))
        short_levels = max(1, total_levels - long_levels)

        spacing = current_price * (self.config.grid_spacing_pct / 100)

        # Long grid levels
        for i in range(1, long_levels + 1):
            price = current_price - (spacing * i)
            self.levels.append(GridLevel(price=price, side=SignalType.BUY, amount=self.config.amount_per_level))
        for i in range(1, long_levels + 1):
            price = current_price + (spacing * i)
            self.levels.append(GridLevel(price=price, side=SignalType.SELL, amount=self.config.amount_per_level))

        # Short grid levels
        for i in range(1, short_levels + 1):
            price = current_price + (spacing * (long_levels + i))
            self.levels.append(GridLevel(price=price, side=SignalType.SELL, amount=-self.config.amount_per_level))
        for i in range(1, short_levels + 1):
            price = current_price - (spacing * (long_levels + i))
            self.levels.append(GridLevel(price=price, side=SignalType.BUY, amount=-self.config.amount_per_level))

        self.levels.sort(key=lambda x: x.price)

        logger.info(f"Grid setup with trend bias: trend={trend}, long_levels={long_levels}, short_levels={short_levels}")
        if self.levels:
            logger.info(f"  Range: ${self.levels[0].price:,.2f} - ${self.levels[-1].price:,.2f}")

        return self.levels
    
    def calculate_signals(self, df: pd.DataFrame, current_price: float) -> list[Signal]:
        """Check grid levels and generate signals.

        Also updates ATR for TP/SL calculation and checks existing
        filled levels for TP/SL hits.

        Args:
            df: OHLCV DataFrame (used for context and ATR calculation)
            current_price: Current market price

        Returns:
            List of signals for levels that should be triggered
        """
        if not self.levels:
            self.setup_grid(current_price)
            return []

        # Update ATR from latest data
        self.update_atr(df)

        # Check TP/SL on existing filled levels
        tp_sl_events = self.check_tp_sl(current_price)
        if tp_sl_events:
            self.tp_sl_alerts.extend(tp_sl_events)

        signals = []

        for level in self.levels:
            if level.filled:
                continue

            # Check if price crossed this level
            should_trigger = False

            if level.side == SignalType.BUY and current_price <= level.price:
                should_trigger = True
            elif level.side == SignalType.SELL and current_price >= level.price:
                should_trigger = True

            if should_trigger:
                is_short = level.amount < 0
                abs_amount = abs(level.amount)
                if is_short and level.side == SignalType.SELL:
                    reason = f"Short SELL (open) at ${level.price:,.2f}"
                elif is_short and level.side == SignalType.BUY:
                    reason = f"Short BUY (cover) at ${level.price:,.2f}"
                else:
                    reason = f"Grid level hit at ${level.price:,.2f}"

                signal = Signal(
                    type=level.side,
                    price=level.price,
                    amount=level.amount,
                    reason=reason,
                )
                signals.append(signal)
                level.filled = True
                level.fill_price = level.price
                level.fill_time = int(time.time() * 1000)
                level.trailing_high = level.price
                level.trailing_low = level.price

                # Set TP/SL for this newly filled level
                self._set_tp_sl_for_level(level)

                # Create opposite level
                self._create_opposite_level(level, current_price)

        return signals
    
    def _create_opposite_level(self, filled_level: GridLevel, current_price: float):
        """Create opposite level after a fill.

        When a buy fills, create a sell above it.
        When a sell fills, create a buy below it.
        Preserves the short flag (negative amount) for short-side levels.
        """
        if len(self.levels) >= self.config.max_levels:
            logger.warning(
                f"Grid at max levels ({self.config.max_levels}), skipping new level creation"
            )
            return

        spacing = current_price * (self.config.grid_spacing_pct / 100)

        if filled_level.side == SignalType.BUY:
            # Create sell level above
            new_price = filled_level.price + spacing
            new_level = GridLevel(
                price=new_price,
                side=SignalType.SELL,
                amount=filled_level.amount,  # Preserves sign
            )
        else:
            # Create buy level below
            new_price = filled_level.price - spacing
            new_level = GridLevel(
                price=new_price,
                side=SignalType.BUY,
                amount=filled_level.amount,  # Preserves sign
            )

        self.levels.append(new_level)
        self.levels.sort(key=lambda x: x.price)

    def update_atr(self, df: pd.DataFrame, period: int = 14):
        """Calculate and store current ATR from OHLCV data.

        Args:
            df: OHLCV DataFrame with high, low, close columns.
            period: ATR period.
        """
        if len(df) < period:
            return
        high = df["high"]
        low = df["low"]
        close = df["close"]
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1 / period, min_periods=period).mean()
        self.current_atr = float(atr.iloc[-1]) if not np.isnan(atr.iloc[-1]) else 0.0

    def _set_tp_sl_for_level(self, level: GridLevel):
        """Set TP/SL prices for a newly filled level based on config mode."""
        if level.fill_price == 0:
            return

        side = "long" if level.amount > 0 else "short"

        # Calculate TP
        if self.config.tp_mode == "atr" and self.current_atr > 0:
            tp, _ = self.tp_sl_calc.atr_based(
                level.fill_price, side, self.current_atr,
                tp_multiplier=self.config.tp_atr_mult,
            )
        elif self.config.tp_mode == "rr_ratio":
            # Need SL first for rr_ratio
            tp = 0.0  # Will be set after SL
        else:  # fixed
            tp, _ = self.tp_sl_calc.fixed_percentage(
                level.fill_price, side,
                tp_pct=self.config.tp_pct,
            )

        # Calculate SL
        if self.config.sl_mode == "atr" and self.current_atr > 0:
            _, sl = self.tp_sl_calc.atr_based(
                level.fill_price, side, self.current_atr,
                sl_multiplier=self.config.sl_atr_mult,
            )
        else:  # fixed
            _, sl = self.tp_sl_calc.fixed_percentage(
                level.fill_price, side,
                sl_pct=self.config.sl_pct,
            )

        # For rr_ratio mode, calculate TP from SL
        if self.config.tp_mode == "rr_ratio" and sl > 0:
            tp = self.tp_sl_calc.risk_reward_ratio(
                level.fill_price, side, sl, rr_ratio=self.config.tp_atr_mult,
            )

        level.take_profit = tp
        level.stop_loss = sl

        logger.debug(
            f"TP/SL set: fill=${level.fill_price:,.2f} TP=${tp:,.2f} SL=${sl:,.2f} ({side})"
        )

    def check_tp_sl(self, current_price: float) -> list[dict]:
        """Check all filled levels for TP/SL hits, trailing stops, and break-even.

        This should be called on every price update (tick).

        Args:
            current_price: Current market price.

        Returns:
            List of event dicts for levels that were closed by TP/SL.
        """
        events = []

        for level in self.levels:
            if not level.filled or level.fill_price == 0:
                continue
            # Skip levels that have already been closed (pnl != 0 and TP/SL = 0)
            if level.take_profit == 0 and level.stop_loss == 0:
                continue

            is_long = level.amount > 0

            # 1. Check break-even activation
            if self.config.break_even_enabled and not level.break_even_triggered:
                self.break_even_mgr.check_and_activate(level, current_price)

            # 2. Check trailing stop
            if self.config.trailing_enabled:
                if self.trailing_mgr.update(level, current_price):
                    pnl = self._calc_level_pnl(level, current_price)
                    level.pnl = pnl
                    events.append({
                        "type": "trailing_stop",
                        "level": level,
                        "price": current_price,
                        "pnl": pnl,
                    })
                    self._close_level(level, current_price)
                    continue

            # 3. Check take-profit
            tp_hit = False
            if level.take_profit > 0:
                if is_long and current_price >= level.take_profit:
                    tp_hit = True
                elif not is_long and current_price <= level.take_profit:
                    tp_hit = True

            if tp_hit:
                pnl = self._calc_level_pnl(level, current_price)
                level.pnl = pnl
                events.append({
                    "type": "take_profit",
                    "level": level,
                    "price": current_price,
                    "pnl": pnl,
                })
                self._close_level(level, current_price)
                continue

            # 4. Check stop-loss
            sl_hit = False
            if level.stop_loss > 0:
                if is_long and current_price <= level.stop_loss:
                    sl_hit = True
                elif not is_long and current_price >= level.stop_loss:
                    sl_hit = True

            if sl_hit:
                pnl = self._calc_level_pnl(level, current_price)
                level.pnl = pnl
                events.append({
                    "type": "stop_loss",
                    "level": level,
                    "price": current_price,
                    "pnl": pnl,
                })
                self._close_level(level, current_price)

        return events

    def _calc_level_pnl(self, level: GridLevel, exit_price: float) -> float:
        """Calculate P&L for a level at given exit price."""
        abs_amount = abs(level.amount)
        if level.amount > 0:  # Long
            return (exit_price - level.fill_price) * abs_amount
        else:  # Short
            return (level.fill_price - exit_price) * abs_amount

    def _close_level(self, level: GridLevel, exit_price: float):
        """Close a level hit by TP/SL — update paper positions.

        Simulates the closing trade (sell for long, buy for short).
        """
        abs_amount = abs(level.amount)
        cost = exit_price * abs_amount

        if level.amount > 0:
            # Close long: sell
            if self.paper_holdings >= abs_amount:
                self.paper_balance += cost
                self.paper_holdings -= abs_amount
                self.long_holdings -= abs_amount
                if self.long_holdings < 0.00000001:
                    self.long_holdings = 0
                    self.long_entry_price = 0
        else:
            # Close short: buy to cover
            if self.short_holdings >= abs_amount and self.paper_balance >= cost:
                self.paper_balance -= cost
                self.short_holdings -= abs_amount
                if self.short_holdings < 0.00000001:
                    self.short_holdings = 0
                    self.short_entry_price = 0

        self.realized_pnl += level.pnl

        # Clear TP/SL so this level isn't checked again
        level.take_profit = 0.0
        level.stop_loss = 0.0

        logger.info(
            f"Level closed: fill=${level.fill_price:,.2f} exit=${exit_price:,.2f} "
            f"PnL=${level.pnl:+,.2f}"
        )

    def execute_paper_trade(self, signal: Signal) -> dict:
        """Execute a paper trade (simulation).

        Supports both long and short trades. Short trades are indicated by
        negative signal.amount.

        Args:
            signal: Trading signal to execute

        Returns:
            Trade result dict
        """
        is_short = signal.amount < 0
        abs_amount = abs(signal.amount)
        cost = signal.price * abs_amount

        if is_short:
            status = self._execute_short_paper(signal.type, signal.price, abs_amount, cost)
        else:
            status = self._execute_long_paper(signal.type, signal.price, abs_amount, cost)

        trade = {
            "signal": signal,
            "status": status,
            "balance": self.paper_balance,
            "holdings": self.paper_holdings,
            "long_holdings": self.long_holdings,
            "short_holdings": self.short_holdings,
            "is_short": is_short,
        }

        if status == "filled":
            self.paper_trades.append(trade)
            direction = "SHORT " if is_short else ""
            logger.info(f"Paper trade: {direction}{signal.type.value.upper()} {abs_amount:.6f} @ ${signal.price:,.2f}")

            # Save to database
            self._save_trade_to_db(signal, is_short, abs_amount, cost)

        return trade

    def _execute_long_paper(self, signal_type: SignalType, price: float, amount: float, cost: float) -> str:
        """Execute long-side paper trade."""
        if signal_type == SignalType.BUY:
            if self.paper_balance >= cost:
                self.paper_balance -= cost
                self.paper_holdings += amount
                self.long_holdings += amount
                # Track average entry
                if self.long_holdings > 0:
                    prev_cost = self.long_entry_price * (self.long_holdings - amount)
                    self.long_entry_price = (prev_cost + cost) / self.long_holdings
                return "filled"
            return "insufficient_funds"
        else:  # SELL (take profit on long)
            if self.paper_holdings >= amount:
                self.paper_balance += cost
                self.paper_holdings -= amount
                self.long_holdings -= amount
                if self.long_holdings < 0.00000001:
                    self.long_holdings = 0
                    self.long_entry_price = 0
                return "filled"
            return "insufficient_holdings"

    def _execute_short_paper(self, signal_type: SignalType, price: float, amount: float, cost: float) -> str:
        """Execute short-side paper trade."""
        if signal_type == SignalType.SELL:
            # Opening short: we receive cash from selling borrowed asset
            self.paper_balance += cost
            self.short_holdings += amount
            # Track average short entry
            if self.short_holdings > 0:
                prev_cost = self.short_entry_price * (self.short_holdings - amount)
                self.short_entry_price = (prev_cost + cost) / self.short_holdings
            return "filled"
        else:  # BUY (cover short)
            if self.short_holdings >= amount:
                if self.paper_balance >= cost:
                    self.paper_balance -= cost
                    self.short_holdings -= amount
                    if self.short_holdings < 0.00000001:
                        self.short_holdings = 0
                        self.short_entry_price = 0
                    return "filled"
                return "insufficient_funds"
            return "insufficient_holdings"

    def _save_trade_to_db(self, signal: Signal, is_short: bool, abs_amount: float, cost: float):
        """Save paper trade to database."""
        db = SessionLocal()
        try:
            side_str = signal.type.value
            direction = "short" if is_short else "long"

            db_trade = Trade(
                symbol=self.symbol,
                side=side_str,
                price=signal.price,
                amount=abs_amount,
                cost=cost,
                fee=0,
                order_id=f"paper_{direction}_{int(time.time() * 1000)}",
                timestamp=int(time.time() * 1000),
            )
            db.add(db_trade)

            # Update position
            position = db.query(Position).filter(Position.symbol == self.symbol).first()
            if position:
                if is_short:
                    self._update_short_position(position, signal.type, signal.price, abs_amount)
                else:
                    self._update_long_position(position, signal.type, signal.price, abs_amount, cost)
            else:
                # Create new position
                position = self._create_position(signal, is_short, abs_amount)
                db.add(position)

            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning(f"Failed to save trade to DB: {e}")
        finally:
            db.close()

    def _update_long_position(self, position: Position, signal_type: SignalType,
                              price: float, amount: float, cost: float):
        """Update position for a long trade."""
        if signal_type == SignalType.BUY:
            total_cost = float(position.entry_price) * float(position.amount) + cost
            position.amount = float(position.amount) + amount
            position.entry_price = total_cost / position.amount if position.amount > 0 else 0
        else:  # SELL
            position.realized_pnl = float(position.realized_pnl or 0) + (price - float(position.entry_price)) * amount
            position.amount = float(position.amount) - amount
            if position.amount <= 0:
                position.amount = 0
                position.entry_price = 0
        position.side = "long" if float(position.amount) > 0.00000001 else "flat"
        if float(position.amount) < 0.00000001:
            position.amount = 0
            position.entry_price = 0

    def _update_short_position(self, position: Position, signal_type: SignalType,
                               price: float, amount: float):
        """Update position for a short trade."""
        if signal_type == SignalType.SELL:
            # Opening short — track short entry
            short_amount = float(position.short_amount) if hasattr(position, 'short_amount') and position.short_amount else 0
            short_entry = float(position.short_entry) if hasattr(position, 'short_entry') and position.short_entry else 0
            total_cost = short_entry * short_amount + price * amount
            new_amount = short_amount + amount
            position.short_amount = new_amount
            position.short_entry = total_cost / new_amount if new_amount > 0 else 0
            position.direction = "both" if float(position.amount) > 0.00000001 else "short"
        else:  # BUY (cover)
            short_amount = float(position.short_amount) if hasattr(position, 'short_amount') and position.short_amount else 0
            short_entry = float(position.short_entry) if hasattr(position, 'short_entry') and position.short_entry else 0
            if short_amount > 0:
                pnl = (short_entry - price) * amount
                position.realized_pnl = float(position.realized_pnl or 0) + pnl
                position.short_amount = short_amount - amount
                if position.short_amount < 0.00000001:
                    position.short_amount = 0
                    position.short_entry = 0
            if (position.amount or 0) < 0.00000001 and (position.short_amount or 0) < 0.00000001:
                position.side = "flat"
            elif (position.short_amount or 0) > 0.00000001 and (position.amount or 0) > 0.00000001:
                position.side = "long"  # Net long if both
                position.direction = "both"
            elif (position.short_amount or 0) > 0.00000001:
                position.side = "short"
            else:
                position.side = "long"

    def _create_position(self, signal: Signal, is_short: bool, abs_amount: float) -> Position:
        """Create a new position record."""
        if is_short and signal.type == SignalType.SELL:
            return Position(
                symbol=self.symbol,
                side="short",
                entry_price=0,
                amount=0,
                unrealized_pnl=0,
                realized_pnl=0,
                direction="short",
                short_amount=abs_amount,
                short_entry=signal.price,
            )
        elif signal.type == SignalType.BUY:
            return Position(
                symbol=self.symbol,
                side="long",
                entry_price=signal.price,
                amount=abs_amount,
                unrealized_pnl=0,
                realized_pnl=0,
                direction="long",
                short_amount=0,
                short_entry=0,
            )
        else:
            return Position(
                symbol=self.symbol,
                side="flat",
                entry_price=0,
                amount=0,
                unrealized_pnl=0,
                realized_pnl=0,
            )
    
    def get_net_exposure(self) -> float:
        """Get net exposure: long_holdings - short_holdings."""
        return self.long_holdings - self.short_holdings

    def get_status(self) -> dict:
        """Get current grid status."""
        active_buys = [l for l in self.levels if l.side == SignalType.BUY and not l.filled]
        active_sells = [l for l in self.levels if l.side == SignalType.SELL and not l.filled]
        filled = [l for l in self.levels if l.filled]

        # Separate long and short levels
        long_levels = [l for l in self.levels if l.amount > 0]
        short_levels = [l for l in self.levels if l.amount < 0]

        # Calculate paper portfolio value
        current_value = self.paper_balance
        if self.center_price:
            if self.long_holdings > 0:
                current_value += self.long_holdings * self.center_price
            if self.short_holdings > 0:
                # Short PnL: entry_price - current_price per unit
                current_value += self.short_holdings * (self.short_entry_price - self.center_price)

        net_exposure = self.get_net_exposure()

        # TP/SL stats (Sprint 21)
        levels_with_tp = [l for l in filled if l.take_profit > 0]
        levels_with_sl = [l for l in filled if l.stop_loss > 0]
        levels_with_be = [l for l in filled if l.break_even_triggered]
        closed_by_tp_sl = [l for l in filled if l.pnl != 0]

        return {
            "strategy": self.name,
            "symbol": self.symbol,
            "is_active": self.is_active,
            "center_price": self.center_price,
            "total_levels": len(self.levels),
            "active_buy_levels": len(active_buys),
            "active_sell_levels": len(active_sells),
            "filled_levels": len(filled),
            "long_levels": len(long_levels),
            "short_levels": len(short_levels),
            "config": {
                "grid_levels": self.config.grid_levels,
                "spacing_pct": self.config.grid_spacing_pct,
                "amount_per_level": self.config.amount_per_level,
                "direction": self.config.direction,
                "leverage": self.config.leverage,
                "tp_mode": self.config.tp_mode,
                "sl_mode": self.config.sl_mode,
                "trailing_enabled": self.config.trailing_enabled,
                "break_even_enabled": self.config.break_even_enabled,
            },
            "paper_trading": {
                "balance_usdt": self.paper_balance,
                "holdings_btc": self.paper_holdings,
                "long_holdings": self.long_holdings,
                "short_holdings": self.short_holdings,
                "long_entry_price": self.long_entry_price,
                "short_entry_price": self.short_entry_price,
                "net_exposure": net_exposure,
                "total_value": current_value,
                "trades_count": len(self.paper_trades),
                "realized_pnl": self.realized_pnl,
            },
            "tp_sl": {
                "current_atr": self.current_atr,
                "levels_with_tp": len(levels_with_tp),
                "levels_with_sl": len(levels_with_sl),
                "break_even_active": len(levels_with_be),
                "closed_by_tp_sl": len(closed_by_tp_sl),
                "total_tp_sl_pnl": sum(l.pnl for l in closed_by_tp_sl),
            },
        }

    def print_grid(self):
        """Print visual representation of the grid."""
        if not self.levels:
            logger.info("Grid not initialized")
            return

        logger.info(f"\n{'='*60}")
        logger.info(f"Grid Status for {self.symbol} (direction={self.config.direction})")
        logger.info(f"Center: ${self.center_price:,.2f} | ATR: ${self.current_atr:,.2f}")
        logger.info(f"Long: {self.long_holdings:.6f} | Short: {self.short_holdings:.6f} | Net: {self.get_net_exposure():.6f}")
        logger.info(f"Realized PnL: ${self.realized_pnl:+,.2f}")
        logger.info(f"{'='*60}")

        for level in reversed(self.levels):  # Top to bottom
            status = "✓ FILLED" if level.filled else "○ ACTIVE"
            is_short = level.amount < 0
            if is_short:
                side = "S-SELL" if level.side == SignalType.SELL else "S-BUY "
                marker = "<<<" if level.side == SignalType.SELL else "   "
            else:
                side = "SELL  " if level.side == SignalType.SELL else "BUY   "
                marker = ">>>" if level.side == SignalType.SELL else "   "

            tp_sl_info = ""
            if level.filled and level.take_profit > 0:
                be = " BE" if level.break_even_triggered else ""
                tp_sl_info = f" | TP=${level.take_profit:,.0f} SL=${level.stop_loss:,.0f}{be}"
            if level.pnl != 0:
                tp_sl_info = f" | PnL=${level.pnl:+,.2f}"

            logger.info(f"{marker} ${level.price:>10,.2f} | {side} | {status}{tp_sl_info}")

        logger.info(f"{'='*60}")
