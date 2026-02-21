"""Trading Bot Main Runner.

24/7 operation with state management:
- WAITING: Bot running, waiting for good market conditions
- TRADING: Actively trading with grid strategy
- PAUSED: AI recommended pause, monitoring for resume
"""

import asyncio
import signal
import sys
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from loguru import logger

from trading_bot.config import settings
from trading_bot.core.exchange import exchange_client
from trading_bot.core.indicators import Indicators
from trading_bot.strategies import AIGridStrategy, AIGridConfig


class BotState(str, Enum):
    """Bot operational state."""
    WAITING = "waiting"   # Waiting for good market conditions
    TRADING = "trading"   # Actively trading
    PAUSED = "paused"     # AI recommended pause


class TradingBot:
    """Main trading bot orchestrator with state management."""
    
    def __init__(
        self,
        symbol: str = "BTC/USDT",
        config: Optional[AIGridConfig] = None,
    ):
        """Initialize trading bot."""
        self.symbol = symbol
        self.config = config or AIGridConfig(
            grid_levels=5,
            grid_spacing_pct=1.0,
            amount_per_level=0.0001,
            ai_enabled=True,
            ai_confirm_signals=False,
            ai_auto_optimize=True,
            ai_periodic_review=True,
            review_interval_minutes=15,
            min_confidence=50,
            risk_tolerance="medium",
        )
        
        self.strategy: Optional[AIGridStrategy] = None
        self.running = False
        self.state = BotState.WAITING
        self.last_review: Optional[datetime] = None
        self.last_entry_check: Optional[datetime] = None
        
        # Entry check interval (how often to check if we can enter market)
        self.entry_check_interval = timedelta(minutes=5)
        
        # Stats
        self.start_time: Optional[datetime] = None
        self.ticks = 0
        self.errors = 0
    
    def setup_logging(self):
        """Configure logging."""
        logger.remove()
        
        # Console
        logger.add(
            sys.stdout,
            level=settings.log_level,
            format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | <cyan>{message}</cyan>",
        )
        
        # File
        logger.add(
            "logs/bot_{time:YYYY-MM-DD}.log",
            rotation="1 day",
            retention="7 days",
            level="DEBUG",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {message}",
        )
    
    async def start(self):
        """Start the trading bot."""
        self.setup_logging()
        
        logger.info("=" * 60)
        logger.info("🤖 TRADING BOT STARTING")
        logger.info("=" * 60)
        logger.info(f"Symbol: {self.symbol}")
        logger.info(f"Environment: {settings.binance_env.value}")
        logger.info(f"AI Model: {settings.openrouter_model}")
        logger.info("")
        
        # Connect to exchange
        logger.info("📡 Connecting to exchange...")
        exchange_client.connect()
        
        # Initialize strategy
        self.strategy = AIGridStrategy(symbol=self.symbol, config=self.config)
        
        # Initial market check
        await self._check_entry_conditions()
        
        # Start main loop
        self.running = True
        self.start_time = datetime.now()
        
        logger.info("")
        logger.info(f"🚀 Bot started in {self.state.value.upper()} mode. Press Ctrl+C to stop.")
        logger.info("")
        
        await self._main_loop()
    
    async def stop(self):
        """Stop the trading bot gracefully."""
        logger.info("")
        logger.info("🛑 Stopping bot...")
        self.running = False
        self._print_stats()
    
    async def _check_entry_conditions(self):
        """Check if market conditions are good for trading."""
        logger.info("🔍 Checking market entry conditions...")
        
        data = await self._fetch_market_data()
        
        should_trade, reason = await self.strategy.analyze_and_setup(
            current_price=data["price"],
            high_24h=data["high_24h"],
            low_24h=data["low_24h"],
            change_24h=data["change_24h"],
            indicators=data["indicators"],
            best_bid=data["best_bid"],
            best_ask=data["best_ask"],
            price_action=f"Entry check at ${data['price']:,.2f}",
        )
        
        self.last_entry_check = datetime.now()
        
        if should_trade:
            if self.state != BotState.TRADING:
                logger.info(f"✅ Market conditions good: {reason}")
                logger.info("📈 Switching to TRADING mode")
                self.state = BotState.TRADING
                self.strategy.print_grid()
                await self._send_alert("🟢 Started trading", reason)
        else:
            if self.state == BotState.TRADING:
                logger.warning(f"⚠️ Market conditions changed: {reason}")
                logger.info("⏸️ Switching to WAITING mode")
                self.state = BotState.WAITING
                await self._send_alert("🟡 Paused trading", reason)
            else:
                logger.info(f"⏳ Still waiting: {reason[:80]}...")
        
        self.last_review = datetime.now()
    
    async def _fetch_market_data(self) -> dict:
        """Fetch current market data."""
        ticker = exchange_client.get_ticker(self.symbol)
        
        order_book = exchange_client.get_order_book(self.symbol)
        best_bid = order_book["bids"][0][0] if order_book["bids"] else ticker["last"] * 0.999
        best_ask = order_book["asks"][0][0] if order_book["asks"] else ticker["last"] * 1.001
        
        ohlcv = exchange_client.get_ohlcv(self.symbol, timeframe="1h", limit=100)
        ohlcv_df = Indicators.to_dataframe(ohlcv)
        indicators_df = Indicators.add_all_indicators(ohlcv_df)
        
        latest = indicators_df.iloc[-1]
        
        return {
            "price": ticker["last"],
            "high_24h": ticker["high"],
            "low_24h": ticker["low"],
            "change_24h": ticker.get("percentage", 0) or 0,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "indicators": {
                "RSI (14)": latest.get("rsi", 50),
                "SMA (20)": latest.get("sma_20", ticker["last"]),
                "EMA (20)": latest.get("ema_20", ticker["last"]),
                "MACD": latest.get("macd", 0),
                "BB Upper": latest.get("bb_upper", ticker["last"] * 1.02),
                "BB Lower": latest.get("bb_lower", ticker["last"] * 0.98),
                "ATR (14)": latest.get("atr", ticker["last"] * 0.01),
            },
            "indicators_df": indicators_df,
        }
    
    async def _main_loop(self):
        """Main trading loop with state management."""
        tick_interval = 5  # seconds between price checks
        
        while self.running:
            try:
                self.ticks += 1
                
                # Fetch current price
                ticker = exchange_client.get_ticker(self.symbol)
                current_price = ticker["last"]
                
                # State-dependent behavior
                if self.state == BotState.WAITING:
                    # Check if we should enter market
                    await self._maybe_check_entry(current_price)
                    
                elif self.state == BotState.TRADING:
                    # Execute grid trading
                    await self._execute_trading(current_price)
                    
                    # Periodic AI review
                    await self._maybe_ai_review(current_price)
                    
                elif self.state == BotState.PAUSED:
                    # Check if we should resume
                    await self._maybe_check_entry(current_price)
                
                # Status update every 60 ticks (~5 min)
                if self.ticks % 60 == 0:
                    self._print_status(current_price)
                
                await asyncio.sleep(tick_interval)
                
            except KeyboardInterrupt:
                await self.stop()
                break
            except Exception as e:
                self.errors += 1
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(tick_interval * 2)
    
    async def _maybe_check_entry(self, current_price: float):
        """Check entry conditions if interval has passed."""
        if self.last_entry_check is None:
            await self._check_entry_conditions()
            return
        
        if datetime.now() - self.last_entry_check >= self.entry_check_interval:
            await self._check_entry_conditions()
    
    async def _execute_trading(self, current_price: float):
        """Execute grid trading logic."""
        data = await self._fetch_market_data()
        
        signals = self.strategy.calculate_signals(
            data["indicators_df"],
            current_price,
        )
        
        for signal in signals:
            trade = self.strategy.execute_paper_trade(signal)
            if trade["status"] == "filled":
                logger.info(
                    f"⚡ {signal.type.value.upper()} "
                    f"{signal.amount:.6f} @ ${signal.price:,.2f}"
                )
                await self._send_alert(
                    f"Trade: {signal.type.value.upper()} "
                    f"{signal.amount:.6f} @ ${signal.price:,.2f}"
                )
    
    async def _maybe_ai_review(self, current_price: float):
        """Run AI review if interval has passed."""
        if not self.config.ai_periodic_review:
            return
        
        if self.last_review is None:
            return
        
        interval = timedelta(minutes=self.config.review_interval_minutes)
        if datetime.now() - self.last_review < interval:
            return
        
        data = await self._fetch_market_data()
        
        review = await self.strategy.periodic_review(
            current_price=current_price,
            indicators=data["indicators"],
            position_value=self.strategy.paper_holdings * current_price,
            unrealized_pnl=0,
        )
        
        self.last_review = datetime.now()
        
        # Handle AI decision
        if review["action"] == "STOP":
            logger.warning(f"🛑 AI says STOP: {review['reason']}")
            self.state = BotState.WAITING
            await self._send_alert("🔴 AI stopped trading", review["reason"])
            
        elif review["action"] == "PAUSE":
            logger.warning(f"⏸️ AI says PAUSE: {review['reason']}")
            self.state = BotState.PAUSED
            await self._send_alert("🟡 AI paused trading", review["reason"])
            
        elif review["action"] == "ADJUST":
            logger.info(f"🔧 AI adjusted grid: {review['reason']}")
    
    async def _send_alert(self, title: str, message: str = ""):
        """Send alert (placeholder for Telegram)."""
        logger.info(f"📢 Alert: {title} - {message[:50]}...")
    
    def _print_status(self, current_price: float):
        """Print current status."""
        status = self.strategy.get_status() if self.strategy else {}
        paper = status.get("paper_trading", {})
        
        runtime = datetime.now() - self.start_time if self.start_time else timedelta()
        
        state_emoji = {
            BotState.WAITING: "⏳",
            BotState.TRADING: "📈",
            BotState.PAUSED: "⏸️",
        }.get(self.state, "❓")
        
        logger.info(
            f"📊 Status | {state_emoji} {self.state.value.upper()} | "
            f"Price: ${current_price:,.2f} | "
            f"Trades: {paper.get('trades_count', 0)} | "
            f"Value: ${paper.get('total_value', 10000):,.2f} | "
            f"Runtime: {runtime}"
        )
    
    def _print_stats(self):
        """Print final statistics."""
        if not self.strategy:
            return
        
        status = self.strategy.get_status()
        paper = status["paper_trading"]
        
        runtime = datetime.now() - self.start_time if self.start_time else timedelta()
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("📈 FINAL STATISTICS")
        logger.info("=" * 60)
        logger.info(f"Final State: {self.state.value}")
        logger.info(f"Runtime: {runtime}")
        logger.info(f"Ticks: {self.ticks}")
        logger.info(f"Errors: {self.errors}")
        logger.info(f"Trades: {paper['trades_count']}")
        logger.info(f"Final Holdings: {paper['holdings_btc']:.6f} BTC")
        logger.info(f"Final USDT: ${paper['balance_usdt']:,.2f}")
        logger.info(f"Total Value: ${paper['total_value']:,.2f}")
        
        profit = paper["total_value"] - 10000
        profit_pct = (profit / 10000) * 100
        logger.info(f"Profit: ${profit:+,.2f} ({profit_pct:+.2f}%)")
        logger.info("=" * 60)


async def run_bot():
    """Run the trading bot."""
    bot = TradingBot(
        symbol="BTC/USDT",
        config=AIGridConfig(
            grid_levels=5,
            grid_spacing_pct=1.5,
            amount_per_level=0.0001,
            ai_enabled=True,
            ai_confirm_signals=False,
            ai_auto_optimize=True,
            ai_periodic_review=True,
            review_interval_minutes=5,
            min_confidence=50,
            risk_tolerance="medium",
        ),
    )
    
    loop = asyncio.get_event_loop()
    
    def signal_handler():
        asyncio.create_task(bot.stop())
    
    loop.add_signal_handler(signal.SIGINT, signal_handler)
    loop.add_signal_handler(signal.SIGTERM, signal_handler)
    
    await bot.start()


if __name__ == "__main__":
    asyncio.run(run_bot())
