"""
CCXT Live Trader — Standalone ETH-USDT perpetual futures grid trading on Binance Testnet.

Uses GridManager from strategies/AIGridStrategy/grid_logic.py (pure Python, no Jesse dep).
Uses SafetyManager from strategies/AIGridStrategy/safety.py for risk checks.

Trial 2861 optimized parameters for ETH-USDT 1h.
"""

import json
import logging
import os
import sys
import time
import traceback
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import ccxt
import numpy as np
import requests
from dotenv import load_dotenv

# Add strategies dir to path so we can import grid_logic
sys.path.insert(0, str(Path(__file__).parent / "strategies" / "AIGridStrategy"))
from grid_logic import GridConfig, GridManager, TrailingStopManager, calculate_sl, calculate_tp, detect_trend
from safety import SafetyManager

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("live_trader")

# ── Trial 2861 Parameters ───────────────────────────────────────────────────

PARAMS = {
    "symbol": "ETH/USDT:USDT",
    "timeframe": "1h",
    "grid_levels_count": 4,
    "grid_spacing_pct": 3.697,
    "amount_pct": 9.988,
    "atr_period": 25,
    "tp_atr_mult": 3.465,
    "sl_atr_mult": 2.744,
    "trailing_activation_pct": 3.904,
    "trailing_distance_pct": 0.765,
    "trend_sma_fast": 28,
    "trend_sma_slow": 63,
    "max_total_levels": 21,
    "leverage": 5,
}

# ── Safety Limits ────────────────────────────────────────────────────────────

MAX_POSITION_PCT = 10.0  # Max position value as % of balance
DAILY_LOSS_LIMIT_PCT = 5.0  # Stop trading if daily loss exceeds this
LOOP_INTERVAL_SECONDS = 3600  # 1 hour
STALE_ORDER_GRID_SPACINGS = 2  # Cancel orders > 2 grid spacings away

# ── Helpers ──────────────────────────────────────────────────────────────────


def calculate_atr(candles: list[list], period: int = 14) -> float:
    """Calculate Average True Range from OHLCV candles.

    Args:
        candles: List of [timestamp, open, high, low, close, volume].
        period: ATR lookback period.

    Returns:
        ATR value.
    """
    if len(candles) < period + 1:
        raise ValueError(f"Need at least {period + 1} candles for ATR, got {len(candles)}")

    true_ranges = []
    for i in range(1, len(candles)):
        high = candles[i][2]
        low = candles[i][3]
        prev_close = candles[i - 1][4]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(tr)

    # Use simple moving average of true ranges for the last `period` values
    return float(np.mean(true_ranges[-period:]))


def calculate_sma(closes: list[float], period: int) -> float | None:
    """Calculate Simple Moving Average."""
    if len(closes) < period:
        return None
    return float(np.mean(closes[-period:]))


def send_discord(webhook_url: str, content: str = "", embeds: list[dict] | None = None) -> None:
    """Send a Discord webhook message. Silently fails if no URL configured."""
    if not webhook_url:
        return
    payload: dict = {}
    if content:
        payload["content"] = content[:2000]
    if embeds:
        payload["embeds"] = embeds
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code == 429:
            retry_after = resp.json().get("retry_after", 1)
            log.warning(f"Discord rate limited, waiting {retry_after}s")
            time.sleep(min(retry_after, 5))
            requests.post(webhook_url, json=payload, timeout=10)
        elif resp.status_code >= 400:
            log.warning(f"Discord webhook returned {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        log.warning(f"Discord webhook failed: {e}")


def discord_embed(
    title: str,
    description: str = "",
    color: int = 0x00FF00,
    fields: list[dict] | None = None,
) -> dict:
    """Build a Discord embed dict."""
    embed: dict = {
        "title": title,
        "description": description,
        "color": color,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if fields:
        embed["fields"] = fields
    return embed


# ── Exchange ─────────────────────────────────────────────────────────────────


def create_exchange() -> ccxt.binanceusdm:
    """Create and configure CCXT Binance USDM Futures (testnet) client."""
    api_key = os.environ.get("BINANCE_FUTURES_API_KEY") or os.environ.get("BINANCE_API_KEY", "")
    api_secret = os.environ.get("BINANCE_FUTURES_API_SECRET") or os.environ.get("BINANCE_API_SECRET", "")

    if not api_key or not api_secret:
        raise RuntimeError("Missing BINANCE_FUTURES_API_KEY / BINANCE_FUTURES_API_SECRET in environment")

    exchange = ccxt.binanceusdm({
        "apiKey": api_key,
        "secret": api_secret,
        "options": {"defaultType": "future"},
    })

    # ccxt 4.x dropped set_sandbox_mode for binanceusdm futures.
    # Override API URLs directly to point at Binance Futures Testnet.
    exchange.urls["api"]["public"] = "https://testnet.binancefuture.com"
    exchange.urls["api"]["private"] = "https://testnet.binancefuture.com"

    exchange.load_markets()
    log.info("Exchange connected: Binance USDM Futures (testnet)")
    return exchange


# ── Live Trader ──────────────────────────────────────────────────────────────


class LiveTrader:
    """Grid trading bot using CCXT on Binance Futures Testnet."""

    def __init__(self, exchange: ccxt.binanceusdm, webhook_url: str = ""):
        self.exchange = exchange
        self.webhook_url = webhook_url
        self.symbol = PARAMS["symbol"]
        self.safety = SafetyManager()

        # Grid setup
        self.grid = GridManager(GridConfig(
            grid_levels_count=PARAMS["grid_levels_count"],
            grid_spacing_pct=PARAMS["grid_spacing_pct"],
            amount_pct=PARAMS["amount_pct"],
            atr_period=PARAMS["atr_period"],
            tp_atr_mult=PARAMS["tp_atr_mult"],
            sl_atr_mult=PARAMS["sl_atr_mult"],
            max_total_levels=PARAMS["max_total_levels"],
            trailing_activation_pct=PARAMS["trailing_activation_pct"],
            trailing_distance_pct=PARAMS["trailing_distance_pct"],
            trend_sma_fast=PARAMS["trend_sma_fast"],
            trend_sma_slow=PARAMS["trend_sma_slow"],
        ))

        self.trailing = TrailingStopManager(
            activation_pct=PARAMS["trailing_activation_pct"],
            distance_pct=PARAMS["trailing_distance_pct"],
        )

        # State tracking
        self.starting_balance: float = 0.0
        self.peak_equity: float = 0.0
        self.daily_pnl: float = 0.0
        self.day_start: datetime = datetime.now(timezone.utc)
        self.trades_today: int = 0
        self.total_trades: int = 0
        self.total_pnl: float = 0.0
        self.filled_order_ids: set[str] = set()
        self._filled_order_ids_deque: deque[str] = deque(maxlen=500)
        self.stopped: bool = False

        # Map grid level id -> exchange order id
        self.level_order_map: dict[str, str] = {}

    # ── Setup ────────────────────────────────────────────────────────────

    def set_leverage(self) -> None:
        """Set leverage on the exchange for our symbol."""
        try:
            self.exchange.set_leverage(PARAMS["leverage"], self.symbol)
            log.info(f"Leverage set to {PARAMS['leverage']}x for {self.symbol}")
        except Exception as e:
            log.warning(f"Could not set leverage (may already be set): {e}")

    def get_balance(self) -> float:
        """Get USDT futures balance."""
        balance = self.exchange.fetch_balance()
        usdt = balance.get("USDT", {})
        return float(usdt.get("total", 0) or 0)

    def get_position(self) -> dict | None:
        """Get current open position for our symbol, or None."""
        positions = self.exchange.fetch_positions([self.symbol])
        for pos in positions:
            contracts = float(pos.get("contracts", 0) or 0)
            if contracts > 0:
                return pos
        return None

    def get_position_value(self) -> float:
        """Get current position notional value."""
        pos = self.get_position()
        if pos is None:
            return 0.0
        return abs(float(pos.get("notional", 0) or 0))

    # ── Market Data ──────────────────────────────────────────────────────

    def fetch_candles(self, limit: int = 100) -> list[list]:
        """Fetch OHLCV candles."""
        candles = self.exchange.fetch_ohlcv(
            self.symbol,
            timeframe=PARAMS["timeframe"],
            limit=limit,
        )
        log.info(f"Fetched {len(candles)} candles ({PARAMS['timeframe']})")
        return candles

    def get_current_price(self) -> float:
        """Get current mark/last price."""
        ticker = self.exchange.fetch_ticker(self.symbol)
        return float(ticker["last"])

    # ── Grid Management ──────────────────────────────────────────────────

    def setup_grid(self, price: float, atr: float, closes: list[float]) -> list[dict]:
        """Calculate grid levels based on current price and trend."""
        trend = detect_trend(
            closes,
            fast_period=PARAMS["trend_sma_fast"],
            slow_period=PARAMS["trend_sma_slow"],
        )

        if trend == "uptrend":
            direction = "long_only"
        elif trend == "downtrend":
            direction = "short_only"
        else:
            direction = "both"

        levels = self.grid.setup_grid(price, direction=direction)
        log.info(
            f"Grid setup: center={price:.2f}, direction={direction}, "
            f"levels={len(levels)}, spacing={PARAMS['grid_spacing_pct']:.3f}%"
        )
        for lvl in levels:
            log.info(f"  {lvl['id']}: {lvl['side']} @ {lvl['price']:.2f}")

        return levels

    def calculate_order_qty(self, price: float, balance: float) -> float:
        """Calculate order quantity based on amount_pct of balance.

        Returns quantity in base asset (ETH).
        """
        notional = balance * (PARAMS["amount_pct"] / 100.0)
        # Account for leverage
        notional_with_leverage = notional * PARAMS["leverage"]
        qty = notional_with_leverage / price

        # Round to exchange precision
        market = self.exchange.market(self.symbol)
        precision = market.get("precision", {}).get("amount", 3)
        qty = round(qty, precision)

        return qty

    def sync_orders(self, levels: list[dict], price: float, balance: float, atr: float) -> None:
        """Sync exchange orders with grid levels.

        - Cancel orders far from grid
        - Place new orders where grid levels have no order
        """
        # Fetch current open orders
        open_orders = self.exchange.fetch_open_orders(self.symbol)
        open_order_ids = {o["id"] for o in open_orders}

        # Clean up level_order_map: remove orders that no longer exist
        stale_levels = [
            lvl_id for lvl_id, oid in self.level_order_map.items()
            if oid not in open_order_ids
        ]
        for lvl_id in stale_levels:
            del self.level_order_map[lvl_id]

        # Cancel orders that are too far from current grid
        spacing_distance = price * (PARAMS["grid_spacing_pct"] / 100.0) * STALE_ORDER_GRID_SPACINGS
        for order in open_orders:
            order_price = float(order["price"])
            if abs(order_price - price) > spacing_distance:
                # Check if this order belongs to one of our grid levels
                is_ours = order["id"] in self.level_order_map.values()
                if is_ours:
                    try:
                        self.exchange.cancel_order(order["id"], self.symbol)
                        log.info(f"Cancelled stale order {order['id']} @ {order_price:.2f}")
                    except Exception as e:
                        log.warning(f"Failed to cancel order {order['id']}: {e}")

        # Place orders for unfilled levels that have no active order
        qty = self.calculate_order_qty(price, balance)

        for level in levels:
            if level["filled"]:
                continue
            if level["id"] in self.level_order_map:
                continue  # Already has an order

            # Safety check: position size
            current_pos_value = self.get_position_value()
            new_order_value = qty * level["price"]
            total_value = current_pos_value + new_order_value
            if not self.safety.check_max_position_size(
                qty, level["price"], balance, MAX_POSITION_PCT
            ):
                log.warning(
                    f"Skipping {level['id']}: position would exceed {MAX_POSITION_PCT}% "
                    f"(current={current_pos_value:.2f}, new={new_order_value:.2f}, "
                    f"balance={balance:.2f})"
                )
                continue

            try:
                side = "buy" if level["side"] == "buy" else "sell"
                order = self.exchange.create_limit_order(
                    self.symbol, side, qty, level["price"],
                )
                self.level_order_map[level["id"]] = order["id"]
                log.info(
                    f"Placed {side} limit order {order['id']} "
                    f"@ {level['price']:.2f} qty={qty}"
                )
            except Exception as e:
                log.error(f"Failed to place order for {level['id']} @ {level['price']:.2f}: {e}")

    # ── Fill Detection ───────────────────────────────────────────────────

    def check_fills(self, balance: float) -> None:
        """Check for recently filled orders and send Discord notifications."""
        try:
            # Fetch recent trades (last 24h)
            trades = self.exchange.fetch_my_trades(self.symbol, limit=50)
        except Exception as e:
            log.warning(f"Could not fetch trades: {e}")
            return

        for trade in trades:
            trade_id = trade["id"]
            if trade_id in self.filled_order_ids:
                continue  # Already processed

            self.filled_order_ids.add(trade_id)
            self._filled_order_ids_deque.append(trade_id)

            side = trade["side"]
            fill_price = float(trade["price"])
            fill_qty = float(trade["amount"])
            cost = float(trade.get("cost", fill_price * fill_qty))
            fee = float(trade.get("fee", {}).get("cost", 0))
            pnl = float(trade.get("info", {}).get("realizedPnl", 0))

            self.total_trades += 1
            self.trades_today += 1
            self.daily_pnl += pnl
            self.total_pnl += pnl

            log.info(
                f"FILL: {side} {fill_qty} @ {fill_price:.2f} | "
                f"PnL={pnl:+.4f} | Fee={fee:.4f}"
            )

            # Remove from level_order_map if this was our order
            order_id = trade.get("order")
            if order_id:
                levels_to_remove = [
                    k for k, v in self.level_order_map.items() if v == order_id
                ]
                for lvl_id in levels_to_remove:
                    del self.level_order_map[lvl_id]
                    # Mark level as filled in grid
                    for lvl in self.grid.levels:
                        if lvl["id"] == lvl_id:
                            lvl["filled"] = True
                            self.grid.filled_levels.add(lvl_id)

            # Log trade to file
            self.safety.log_trade({
                "symbol": self.symbol,
                "side": side,
                "price": fill_price,
                "qty": fill_qty,
                "cost": cost,
                "fee": fee,
                "pnl": pnl,
                "balance": balance,
            })

            # Discord notification
            color = 0x00FF00 if pnl >= 0 else 0xFF0000
            win_loss = "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "NEUTRAL")
            send_discord(self.webhook_url, embeds=[discord_embed(
                title=f"Order Filled — {win_loss}",
                color=color,
                fields=[
                    {"name": "Side", "value": side.upper(), "inline": True},
                    {"name": "Price", "value": f"${fill_price:,.2f}", "inline": True},
                    {"name": "Qty", "value": f"{fill_qty}", "inline": True},
                    {"name": "PnL", "value": f"${pnl:+.4f}", "inline": True},
                    {"name": "Daily PnL", "value": f"${self.daily_pnl:+.4f}", "inline": True},
                    {"name": "Trades Today", "value": str(self.trades_today), "inline": True},
                ],
            )])

        self._prune_filled_order_ids()

    def _prune_filled_order_ids(self) -> None:
        """Keep filled_order_ids bounded to last 500 trades."""
        if len(self.filled_order_ids) > 500:
            self.filled_order_ids = set(self._filled_order_ids_deque)

    # ── Daily Reset ──────────────────────────────────────────────────────

    def check_daily_reset(self) -> None:
        """Reset daily counters at UTC midnight."""
        now = datetime.now(timezone.utc)
        if now.date() > self.day_start.date():
            # Send daily summary before reset
            self.send_daily_summary()
            self.daily_pnl = 0.0
            self.trades_today = 0
            self.day_start = now
            self.starting_balance = self.get_balance()
            self.peak_equity = self.starting_balance
            log.info(f"Daily reset. Starting balance: {self.starting_balance:.2f}")

    def send_daily_summary(self) -> None:
        """Send daily summary to Discord."""
        balance = self.get_balance()
        send_discord(self.webhook_url, embeds=[discord_embed(
            title="Daily Summary",
            color=0x0099FF,
            fields=[
                {"name": "Date", "value": self.day_start.strftime("%Y-%m-%d"), "inline": True},
                {"name": "Trades", "value": str(self.trades_today), "inline": True},
                {"name": "Daily PnL", "value": f"${self.daily_pnl:+.4f}", "inline": True},
                {"name": "Total PnL", "value": f"${self.total_pnl:+.4f}", "inline": True},
                {"name": "Balance", "value": f"${balance:,.2f}", "inline": True},
                {"name": "Total Trades", "value": str(self.total_trades), "inline": True},
            ],
        )])

    # ── Main Loop ────────────────────────────────────────────────────────

    def run(self) -> None:
        """Main trading loop. Runs every hour."""
        # Initial setup
        self.set_leverage()
        self.starting_balance = self.get_balance()
        self.peak_equity = self.starting_balance
        price = self.get_current_price()

        log.info(f"Starting LiveTrader: {self.symbol}")
        log.info(f"Balance: {self.starting_balance:.2f} USDT")
        log.info(f"Price: {price:.2f}")
        log.info(f"Leverage: {PARAMS['leverage']}x")
        log.info(f"Grid levels: {PARAMS['grid_levels_count']} | Spacing: {PARAMS['grid_spacing_pct']:.3f}%")

        # Startup Discord notification
        send_discord(self.webhook_url, embeds=[discord_embed(
            title="Bot Started",
            description=f"CCXT Grid Trader — {self.symbol}",
            color=0x00FF00,
            fields=[
                {"name": "Balance", "value": f"${self.starting_balance:,.2f}", "inline": True},
                {"name": "ETH Price", "value": f"${price:,.2f}", "inline": True},
                {"name": "Leverage", "value": f"{PARAMS['leverage']}x", "inline": True},
                {"name": "Grid Levels", "value": str(PARAMS["grid_levels_count"]), "inline": True},
                {"name": "Spacing", "value": f"{PARAMS['grid_spacing_pct']:.3f}%", "inline": True},
                {"name": "Mode", "value": "Testnet", "inline": True},
            ],
        )])

        while not self.stopped:
            try:
                self._loop_iteration()
            except KeyboardInterrupt:
                log.info("Shutting down (KeyboardInterrupt)")
                self.stopped = True
            except Exception as e:
                log.error(f"Loop error: {e}\n{traceback.format_exc()}")
                send_discord(self.webhook_url, embeds=[discord_embed(
                    title="Error",
                    description=f"```{str(e)[:500]}```",
                    color=0xFF0000,
                )])
                # Wait before retrying on error
                time.sleep(60)

        # Shutdown
        log.info("Bot stopped.")
        send_discord(self.webhook_url, embeds=[discord_embed(
            title="Bot Stopped",
            color=0xFF9900,
            fields=[
                {"name": "Total Trades", "value": str(self.total_trades), "inline": True},
                {"name": "Total PnL", "value": f"${self.total_pnl:+.4f}", "inline": True},
            ],
        )])

    def _loop_iteration(self) -> None:
        """Single iteration of the main trading loop."""
        # Emergency stop check
        if self.safety.emergency_stop_check():
            log.warning("EMERGENCY STOP triggered! Halting.")
            send_discord(self.webhook_url, embeds=[discord_embed(
                title="EMERGENCY STOP",
                description="Emergency stop file detected. Bot halted.",
                color=0xFF0000,
            )])
            self.stopped = True
            return

        # Daily reset check
        self.check_daily_reset()

        # Fetch market data
        candles = self.fetch_candles(limit=100)
        closes = [c[4] for c in candles]
        price = closes[-1]
        atr = calculate_atr(candles, period=PARAMS["atr_period"])
        sma_fast = calculate_sma(closes, PARAMS["trend_sma_fast"])
        sma_slow = calculate_sma(closes, PARAMS["trend_sma_slow"])

        log.info(
            f"Price={price:.2f} | ATR={atr:.2f} | "
            f"SMA{PARAMS['trend_sma_fast']}={sma_fast:.2f if sma_fast else 'N/A'} | "
            f"SMA{PARAMS['trend_sma_slow']}={sma_slow:.2f if sma_slow else 'N/A'}"
        )

        # Get balance and check daily loss limit
        balance = self.get_balance()
        self.peak_equity = max(self.peak_equity, balance)

        if not self.safety.check_daily_loss_limit(
            self.daily_pnl, DAILY_LOSS_LIMIT_PCT, self.starting_balance
        ):
            log.warning(
                f"Daily loss limit hit! PnL={self.daily_pnl:+.4f} "
                f"(limit={DAILY_LOSS_LIMIT_PCT}% of {self.starting_balance:.2f})"
            )
            send_discord(self.webhook_url, embeds=[discord_embed(
                title="Daily Loss Limit Hit",
                description="Trading paused until next day.",
                color=0xFF0000,
                fields=[
                    {"name": "Daily PnL", "value": f"${self.daily_pnl:+.4f}", "inline": True},
                    {"name": "Limit", "value": f"{DAILY_LOSS_LIMIT_PCT}%", "inline": True},
                ],
            )])
            time.sleep(LOOP_INTERVAL_SECONDS)
            return

        # Drawdown check
        if not self.safety.check_max_drawdown(
            self.peak_equity, balance, max_dd_pct=10.0
        ):
            log.warning(
                f"Max drawdown breached! Peak={self.peak_equity:.2f} "
                f"Current={balance:.2f}"
            )
            send_discord(self.webhook_url, embeds=[discord_embed(
                title="Max Drawdown Breached",
                description="Trading paused.",
                color=0xFF0000,
            )])
            time.sleep(LOOP_INTERVAL_SECONDS)
            return

        # Only rebuild grid when: (1) no grid exists, or (2) trend direction changed
        trend = detect_trend(
            closes,
            fast_period=PARAMS["trend_sma_fast"],
            slow_period=PARAMS["trend_sma_slow"],
        )
        if trend == "uptrend":
            new_direction = "long_only"
        elif trend == "downtrend":
            new_direction = "short_only"
        else:
            new_direction = "both"

        if not self.grid.levels or new_direction != self.grid.direction:
            log.info(f"Grid rebuild: direction changed {self.grid.direction} → {new_direction}")
            self.level_order_map = {}
            levels = self.setup_grid(price, atr, closes)
        else:
            levels = self.grid.levels
            log.info(
                f"Grid preserved: direction={self.grid.direction}, "
                f"filled={self.grid.filled_count}/{len(levels)}"
            )

        # Sync orders with grid
        self.sync_orders(levels, price, balance, atr)

        # Check for filled orders
        self.check_fills(balance)

        log.info(
            f"Loop done | Balance={balance:.2f} | DailyPnL={self.daily_pnl:+.4f} | "
            f"Trades today={self.trades_today} | Open levels={self.grid.unfilled_count}"
        )

        # Wait for next interval
        time.sleep(LOOP_INTERVAL_SECONDS)


# ── Entry Point ──────────────────────────────────────────────────────────────

def main() -> None:
    # Load .env from jesse-bot directory
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        log.info(f"Loaded env from {env_path}")
    else:
        log.warning(f"No .env file found at {env_path}, using environment variables")

    # Validate API keys
    api_key = os.environ.get("BINANCE_FUTURES_API_KEY") or os.environ.get("BINANCE_API_KEY", "")
    api_secret = os.environ.get("BINANCE_FUTURES_API_SECRET") or os.environ.get("BINANCE_API_SECRET", "")

    if not api_key or api_key == "your_api_key_here":
        log.error("BINANCE_FUTURES_API_KEY is not set. Add it to jesse-bot/.env")
        sys.exit(1)
    if not api_secret or api_secret == "your_api_secret_here":
        log.error("BINANCE_FUTURES_API_SECRET is not set. Add it to jesse-bot/.env")
        sys.exit(1)

    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not webhook_url:
        log.warning("DISCORD_WEBHOOK_URL not set — Discord notifications disabled")

    # Create exchange connection
    exchange = create_exchange()

    # Create and run trader
    trader = LiveTrader(exchange, webhook_url=webhook_url)
    trader.run()


if __name__ == "__main__":
    main()
