"""Trading Bot Main Runner.

24/7 operation with state management:
- WAITING: Bot running, waiting for good market conditions
- TRADING: Actively trading with grid strategy
- PAUSED: AI recommended pause, monitoring for resume
"""

import asyncio
import json
import signal
import sys
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from loguru import logger

from shared.config import settings
from shared.constants import (
    TICK_INTERVAL_SEC,
    RULES_CHECK_INTERVAL,
    STATUS_UPDATE_INTERVAL,
    BID_FALLBACK_FACTOR,
    ASK_FALLBACK_FACTOR,
    CANDLE_FETCH_LIMIT,
)
from binance_bot.core.exchange import exchange_client
from shared.core.indicators import Indicators
from binance_bot.strategies import AIGridStrategy, AIGridConfig, SignalType
from shared.risk import PositionSizer, SizingMethod, RiskLimits, RiskMetrics, StopLossManager
from binance_bot.core.emergency import EmergencyStop
from shared.core.state import BotState as SharedBotState, write_state, read_command
from shared.vector_db.news_fetcher import NewsFetcher
from shared.vector_db.sentiment import SentimentAnalyzer
from shared.monitoring.metrics import get_metrics as get_trading_metrics
from shared.alerts import (
    AlertManager,
    AlertConfig,
    AlertLevel,
    get_alert_manager,
    get_rules_engine,
)
from shared.strategies import StrategyEngine, StrategyRegistry


class BotState(str, Enum):
    """Bot operational state."""
    WAITING = "waiting"   # Waiting for good market conditions
    TRADING = "trading"   # Actively trading
    PAUSED = "paused"     # AI recommended pause


class TradingBot:
    """Main trading bot orchestrator with state management."""
    
    # Default path for optimized parameters
    OPTIMIZED_PARAMS_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "optimized_params.json"

    def __init__(
        self,
        symbol: str = "BTC/USDT",
        config: Optional[AIGridConfig] = None,
        use_optimized: bool = False,
        strategy_mode: str = "auto",
    ):
        """Initialize trading bot.

        Args:
            symbol: Trading pair.
            config: AI grid configuration. If None, uses defaults.
            use_optimized: If True, load params from data/optimized_params.json.
            strategy_mode: Strategy selection mode.
                "auto" = regime-based multi-strategy engine (default).
                "grid", "momentum", "mean_reversion", "breakout" = fixed strategy.
        """
        self.symbol = symbol
        self.strategy_mode = strategy_mode

        base_config = config or AIGridConfig(
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

        if use_optimized:
            base_config = self._apply_optimized_params(base_config)

        self.config = base_config
        
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
        
        # Risk Management
        self.position_sizer = PositionSizer(
            method=SizingMethod.FIXED_PERCENT,
            risk_per_trade=settings.risk_per_trade,
            max_position_pct=settings.risk_max_position_pct,
        )
        self.risk_limits = RiskLimits(
            daily_loss_limit=settings.risk_daily_loss_limit,
            max_drawdown_limit=settings.risk_max_drawdown_limit,
            max_consecutive_losses=settings.risk_max_consecutive_losses,
        )
        self.risk_metrics = RiskMetrics()
        self.stop_loss_manager = StopLossManager(
            default_stop_pct=settings.risk_stop_loss_pct,
            default_tp_pct=settings.risk_take_profit_pct,
        )
        self.trading_metrics = get_trading_metrics()

        # News Sentiment
        self.news_fetcher = NewsFetcher()
        self.sentiment_analyzer = SentimentAnalyzer()
        self._news_sentiment_context: str = ""
        self._last_news_fetch: Optional[datetime] = None
        self._news_fetch_interval = timedelta(minutes=15)

        # Emergency Stop
        self.emergency_stop = EmergencyStop()
        
        # Alert Manager
        alert_config = AlertConfig(
            alerts_enabled=settings.alerts_enabled,
            discord_enabled=settings.discord_enabled,
            email_enabled=settings.email_enabled,
            alert_on_trade=settings.alert_on_trade,
            alert_on_error=settings.alert_on_error,
            daily_summary_enabled=settings.daily_summary_enabled,
            daily_summary_time=settings.daily_summary_time,
        )
        self.alert_manager = get_alert_manager(alert_config)
        
        # Alert Rules Engine
        self.rules_engine = get_rules_engine()
        self.rules_engine.set_alert_callback(self._handle_rule_alert)

        # Multi-Strategy Engine (Sprint 22)
        self.strategy_engine = StrategyEngine()
        for name in StrategyRegistry.list_all():
            self.strategy_engine.register(StrategyRegistry.get(name))

        # If a specific strategy is requested, force it
        if self.strategy_mode != "auto" and self.strategy_mode in StrategyRegistry.list_all():
            strategy_class_name = StrategyRegistry.get(self.strategy_mode).name
            self.strategy_engine.hot_swap(strategy_class_name)
    
    @staticmethod
    def _apply_optimized_params(config: AIGridConfig) -> AIGridConfig:
        """Load optimized params from JSON and apply to config.

        Falls back to the original config if the file doesn't exist.
        """
        path = TradingBot.OPTIMIZED_PARAMS_PATH
        if not path.exists():
            logger.warning(f"Optimized params not found at {path}, using defaults")
            return config

        try:
            with open(path) as f:
                params = json.load(f)

            if "grid_levels" in params:
                config.grid_levels = int(params["grid_levels"])
            if "grid_spacing_pct" in params:
                config.grid_spacing_pct = float(params["grid_spacing_pct"])
            if "amount_per_level" in params:
                config.amount_per_level = float(params["amount_per_level"])

            logger.info(
                f"Loaded optimized params: levels={config.grid_levels}, "
                f"spacing={config.grid_spacing_pct}%, amount={config.amount_per_level}"
            )
        except Exception as e:
            logger.warning(f"Failed to load optimized params: {e}")

        return config

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
    
    async def _handle_rule_alert(self, title: str, message: str, level: str):
        """Handle alerts from rules engine."""
        alert_level = AlertLevel(level) if level in [l.value for l in AlertLevel] else AlertLevel.INFO
        await self.alert_manager.send_custom_alert(
            title=title,
            message=message,
            level=alert_level,
        )
    
    async def _get_daily_summary_data(self) -> dict:
        """Get data for daily summary callback."""
        if not self.strategy:
            return {}
        
        status = self.strategy.get_status()
        paper = status.get("paper_trading", {})
        
        # Calculate stats
        start_balance = settings.paper_initial_balance
        end_balance = paper.get("total_value", settings.paper_initial_balance)
        total_trades = paper.get("trades_count", 0)
        
        # Get from risk metrics if available
        winning_trades_raw = getattr(self.risk_metrics, 'winning_trades', [])
        losing_trades_raw = getattr(self.risk_metrics, 'losing_trades', [])
        winning_trades = len(winning_trades_raw) if isinstance(winning_trades_raw, list) else int(winning_trades_raw)
        losing_trades = len(losing_trades_raw) if isinstance(losing_trades_raw, list) else int(losing_trades_raw)
        total_pnl = end_balance - start_balance
        max_drawdown = getattr(self.risk_metrics, 'max_drawdown', 0) * 100
        
        return {
            "symbol": self.symbol,
            "start_balance": start_balance,
            "end_balance": end_balance,
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "total_pnl": total_pnl,
            "max_drawdown": max_drawdown,
        }
    
    async def start(self):
        """Start the trading bot."""
        self.setup_logging()
        
        logger.info("=" * 60)
        logger.info("🤖 TRADING BOT STARTING")
        logger.info("=" * 60)
        logger.info(f"Symbol: {self.symbol}")
        logger.info(f"Environment: {settings.binance_env.value}")
        logger.info(f"AI Model: {settings.openrouter_model}")
        logger.info(f"Alerts: Discord={settings.discord_enabled}, Email={settings.email_enabled}")
        logger.info(f"Strategy Mode: {self.strategy_mode}")
        logger.info(f"Registered Strategies: {self.strategy_engine.list_strategies()}")
        logger.info("")
        
        # Validate API keys before connecting
        settings.validate_trading_config()

        # Connect to exchange
        logger.info("📡 Connecting to exchange...")
        exchange_client.connect()
        
        # Initialize strategy
        initial_balance = settings.paper_initial_balance
        self.risk_limits.set_initial_balance(initial_balance)
        self.risk_metrics.initial_balance = initial_balance
        self.risk_metrics.update_equity(initial_balance)
        
        # Initialize rules engine
        self.rules_engine.reset_daily_stats(initial_balance)
        
        self.strategy = AIGridStrategy(symbol=self.symbol, config=self.config)
        
        # Start daily summary scheduler
        if settings.daily_summary_enabled:
            self.alert_manager.start_daily_summary_scheduler(self._get_daily_summary_data)
        
        # Initial market check
        try:
            await self._check_entry_conditions()
        except Exception as e:
            logger.warning(f"Initial entry check failed (will retry in main loop): {e}")
        
        # Start main loop
        self.running = True
        self.start_time = datetime.now(timezone.utc)
        
        # Send startup alert
        ticker = exchange_client.get_ticker(self.symbol)
        await self.alert_manager.send_status_alert(
            status="started",
            symbol=self.symbol,
            current_price=ticker.get("last", 0),
            total_value=initial_balance,
            trades_count=0,
            reason=f"Environment: {settings.binance_env.value}",
        )
        
        logger.info("")
        logger.info(f"🚀 Bot started in {self.state.value.upper()} mode. Press Ctrl+C to stop.")
        logger.info("")
        
        await self._main_loop()
    
    async def stop(self):
        """Stop the trading bot gracefully."""
        logger.info("")
        logger.info("🛑 Stopping bot...")
        self.running = False
        
        # Get final stats
        status = self.strategy.get_status() if self.strategy else {}
        paper = status.get("paper_trading", {})
        
        # Send stop alert
        await self.alert_manager.send_status_alert(
            status="stopped",
            symbol=self.symbol,
            total_value=paper.get("total_value", settings.paper_initial_balance),
            trades_count=paper.get("trades_count", 0),
            reason="Graceful shutdown",
        )
        
        # Stop daily summary scheduler
        self.alert_manager.stop_daily_summary_scheduler()
        
        # Close alert manager
        await self.alert_manager.close()
        
        # Write stopped state
        self._write_shared_state()
        
        self._print_stats()
    
    async def _check_entry_conditions(self):
        """Check if market conditions are good for trading."""
        logger.info("🔍 Checking market entry conditions...")
        
        data = await self._fetch_market_data()
        
        # Update rules engine with price
        self.rules_engine.update_price(data["price"])
        self.rules_engine.update_connection()
        
        should_trade, reason = await self.strategy.analyze_and_setup(
            current_price=data["price"],
            high_24h=data["high_24h"],
            low_24h=data["low_24h"],
            change_24h=data["change_24h"],
            indicators=data["indicators"],
            best_bid=data["best_bid"],
            best_ask=data["best_ask"],
            price_action=f"Entry check at ${data['price']:,.2f}",
            ohlcv_df=data["ohlcv_df"],
            news_sentiment_context=self._news_sentiment_context,
        )
        
        self.last_entry_check = datetime.now(timezone.utc)
        
        if should_trade:
            if self.state != BotState.TRADING:
                logger.info(f"✅ Market conditions good: {reason}")
                logger.info("📈 Switching to TRADING mode")
                self.state = BotState.TRADING
                self.strategy.print_grid()
                
                await self.alert_manager.send_status_alert(
                    status="trading",
                    symbol=self.symbol,
                    current_price=data["price"],
                    reason=reason,
                )
        else:
            if self.state == BotState.TRADING:
                logger.warning(f"⚠️ Market conditions changed: {reason}")
                logger.info("⏸️ Switching to WAITING mode")
                self.state = BotState.WAITING
                
                await self.alert_manager.send_status_alert(
                    status="waiting",
                    symbol=self.symbol,
                    current_price=data["price"],
                    reason=reason,
                )
            else:
                logger.info(f"⏳ Still waiting: {reason[:80]}...")
        
        self.last_review = datetime.now(timezone.utc)
    
    async def _fetch_market_data(self, ticker: Optional[dict] = None) -> dict:
        """Fetch current market data."""
        if ticker is None:
            ticker = exchange_client.get_ticker(self.symbol)
        
        order_book = exchange_client.get_order_book(self.symbol)
        best_bid = order_book["bids"][0][0] if order_book["bids"] else ticker["last"] * BID_FALLBACK_FACTOR
        best_ask = order_book["asks"][0][0] if order_book["asks"] else ticker["last"] * ASK_FALLBACK_FACTOR

        ohlcv = exchange_client.get_ohlcv(self.symbol, timeframe="1h", limit=CANDLE_FETCH_LIMIT)
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
            "ohlcv_df": ohlcv_df,
        }
    
    async def _main_loop(self):
        """Main trading loop with state management."""
        tick_interval = TICK_INTERVAL_SEC
        rules_check_counter = 0
        
        while self.running:
            try:
                self.ticks += 1
                rules_check_counter += 1
                
                # Check file-based commands from API/dashboard
                cmd = read_command()
                if cmd == "pause":
                    logger.info("Received PAUSE command from dashboard")
                    self.state = BotState.PAUSED
                elif cmd == "resume":
                    can_trade, reason = self.risk_limits.can_trade()
                    if can_trade:
                        logger.info("Received RESUME command from dashboard")
                        self.state = BotState.TRADING
                    else:
                        logger.warning(f"Dashboard resume blocked by risk limits: {reason}")
                elif cmd == "stop":
                    logger.info("Received STOP command from dashboard")
                    self.running = False
                    break
                
                # Check emergency stop
                if self.emergency_stop.is_triggered:
                    logger.critical("🚨 Emergency stop detected - initiating shutdown")
                    await self._handle_emergency_stop()
                    break
                
                # Fetch current price
                ticker = exchange_client.get_ticker(self.symbol)
                current_price = ticker.get("last") or ticker.get("close") or 0.0
                if current_price <= 0:
                    logger.warning(f"Invalid price from ticker: {ticker}")
                    await asyncio.sleep(tick_interval)
                    continue
                
                # Update rules engine with price
                self.rules_engine.update_price(current_price)
                self.rules_engine.update_connection()
                
                # Update shared state with current price
                self._write_shared_state(current_price)
                
                # Evaluate alert rules periodically
                if rules_check_counter >= RULES_CHECK_INTERVAL:
                    rules_check_counter = 0
                    triggered = await self.rules_engine.evaluate_all()
                    if triggered:
                        logger.info(f"📢 {len(triggered)} alert rule(s) triggered")
                
                # State-dependent behavior
                if self.state == BotState.WAITING:
                    # Check if we should enter market
                    await self._maybe_check_entry(current_price)
                    
                elif self.state == BotState.TRADING:
                    # Execute grid trading
                    await self._execute_trading(current_price, ticker=ticker)
                    
                    # Periodic AI review
                    await self._maybe_ai_review(current_price)
                    
                elif self.state == BotState.PAUSED:
                    # Auto-resume: re-check entry conditions
                    await self._maybe_check_entry(current_price)
                    
                    # Also run AI review to override previous PAUSE decision
                    # AI review has its own interval (~6 min), so this won't spam
                    if self.state == BotState.PAUSED:
                        await self._maybe_ai_review(current_price)
                
                # Periodic news sentiment fetch (~15 min)
                await self._maybe_fetch_news()

                # Periodic status update
                if self.ticks % STATUS_UPDATE_INTERVAL == 0:
                    self._print_status(current_price)
                
                await asyncio.sleep(tick_interval)
                
            except Exception as e:
                self.errors += 1
                logger.error(f"Error in main loop: {e}")
                
                # Send error alert
                await self.alert_manager.send_error_alert(
                    error=str(e),
                    context="Main trading loop",
                    exc=e,
                    level=AlertLevel.ERROR,
                )
                
                await asyncio.sleep(tick_interval * 2)
    
    async def _maybe_check_entry(self, current_price: float):
        """Check entry conditions if interval has passed."""
        if self.last_entry_check is None:
            await self._check_entry_conditions()
            return
        
        if datetime.now(timezone.utc) - self.last_entry_check >= self.entry_check_interval:
            await self._check_entry_conditions()
    
    async def _execute_trading(self, current_price: float, ticker: Optional[dict] = None):
        """Execute grid trading logic with risk management."""
        if not await self._check_risk_limits(current_price):
            return

        data = await self._fetch_market_data(ticker=ticker)
        await self._run_strategy_engine(data, current_price)
        await self._check_stop_loss(current_price)
        await self._process_signals(data, current_price)

    async def _check_risk_limits(self, current_price: float) -> bool:
        """Check if trading is allowed. Returns False if halted."""
        can_trade, reason = self.risk_limits.can_trade()
        if not can_trade:
            if self.state == BotState.TRADING:
                logger.warning(f"🛑 Trading halted: {reason}")
                self.state = BotState.PAUSED
                await self.alert_manager.send_status_alert(
                    status="paused",
                    symbol=self.symbol,
                    current_price=current_price,
                    reason=f"Risk limit: {reason}",
                )
            return False
        return True

    async def _run_strategy_engine(self, data: dict, current_price: float):
        """Evaluate regime and get signal from multi-strategy engine."""
        if self.strategy_mode != "auto" and self.strategy_mode not in StrategyRegistry.list_all():
            return

        prev_strategy = self.strategy_engine.active_strategy_name
        candles = data["indicators_df"].reset_index().to_dict("records")
        latest = data["indicators_df"].iloc[-1]
        engine_indicators = {
            "ema_8": float(data["indicators_df"]["close"].ewm(span=8, adjust=False).mean().iloc[-1]),
            "ema_21": float(data["indicators_df"]["close"].ewm(span=21, adjust=False).mean().iloc[-1]),
            "rsi_14": float(latest.get("rsi", 50)),
            "bb_upper": float(latest.get("bb_upper", current_price * 1.02)),
            "bb_lower": float(latest.get("bb_lower", current_price * 0.98)),
            "bb_middle": float(latest.get("bb_middle", current_price)),
            "atr": float(latest.get("atr", current_price * 0.01)),
            "adx": 0,
            "highest_20": float(data["indicators_df"]["high"].rolling(20).max().iloc[-1]) if len(data["indicators_df"]) >= 20 else current_price,
            "lowest_20": float(data["indicators_df"]["low"].rolling(20).min().iloc[-1]) if len(data["indicators_df"]) >= 20 else current_price,
            "volume_sma": float(data["indicators_df"]["volume"].rolling(20).mean().iloc[-1]) if len(data["indicators_df"]) >= 20 else 0,
        }
        engine_signal = self.strategy_engine.get_signal(candles, engine_indicators, current_price)

        if self.strategy_engine.active_strategy_name != prev_strategy and prev_strategy is not None:
            await self.alert_manager.send_custom_alert(
                title="Strategy Switch",
                message=(
                    f"Regime: {self.strategy_engine.current_regime.value if self.strategy_engine.current_regime else 'N/A'}\n"
                    f"{prev_strategy} -> {self.strategy_engine.active_strategy_name}"
                ),
                level=AlertLevel.INFO,
            )

        if engine_signal:
            logger.info(
                f"Engine signal: {engine_signal.get('side', 'N/A')} from "
                f"{engine_signal.get('strategy', 'N/A')} "
                f"(regime={engine_signal.get('regime', 'N/A')})"
            )

    async def _check_stop_loss(self, current_price: float):
        """Check stop-loss / take-profit for tracked positions."""
        sl_result = self.stop_loss_manager.check_position(self.symbol, current_price)
        if sl_result["action"] not in ("stop_loss", "take_profit"):
            return

        logger.warning(
            f"{'🛑 Stop-loss' if sl_result['action'] == 'stop_loss' else '🎯 Take-profit'} "
            f"triggered @ ${current_price:,.2f}, PnL: ${sl_result['pnl']:,.2f}"
        )
        self.risk_limits.record_trade(sl_result["pnl"], {
            "symbol": self.symbol,
            "side": "sell",
            "price": current_price,
            "reason": sl_result["action"],
        })
        self.stop_loss_manager.remove_position(self.symbol)

        await self.alert_manager.send_trade_alert(
            symbol=self.symbol,
            side="sell",
            price=current_price,
            amount=sl_result["position"].amount,
            pnl=sl_result["pnl"],
        )

    async def _process_signals(self, data: dict, current_price: float):
        """Calculate and execute grid trading signals."""
        signals = self.strategy.calculate_signals(
            data["indicators_df"],
            current_price,
        )

        for signal in signals:
            trade = self.strategy.execute_paper_trade(signal)
            if trade["status"] != "filled":
                continue

            pnl = self._calculate_signal_pnl(signal)

            self.risk_limits.record_trade(pnl, {
                "symbol": self.symbol,
                "side": signal.type.value,
                "price": signal.price,
                "amount": signal.amount,
            })
            self.rules_engine.record_trade(pnl)
            self.trading_metrics.record_trade(signal.type.value, self.symbol)
            self.trading_metrics.set_pnl(pnl)

            paper_status = self.strategy.get_status().get("paper_trading", {})
            total_value = paper_status.get("total_value", settings.paper_initial_balance)
            self.risk_limits.update_balance(total_value)
            self.risk_metrics.update_equity(total_value)
            self.rules_engine.set_pnl(total_value - settings.paper_initial_balance)

            logger.info(
                f"⚡ {signal.type.value.upper()} "
                f"{signal.amount:.6f} @ ${signal.price:,.2f}"
            )

            if signal.type == SignalType.BUY:
                self.stop_loss_manager.add_position(
                    symbol=self.symbol,
                    entry_price=signal.price,
                    amount=signal.amount,
                    is_long=True,
                )

            await self.alert_manager.send_trade_alert(
                symbol=self.symbol,
                side=signal.type.value,
                price=signal.price,
                amount=signal.amount,
                pnl=pnl if pnl != 0 else None,
            )

    def _calculate_signal_pnl(self, signal) -> float:
        """Calculate PnL for a closing trade signal."""
        if signal.type == SignalType.SELL and hasattr(self.strategy, 'long_entry_price'):
            if signal.amount > 0 and self.strategy.long_entry_price > 0:
                return (signal.price - self.strategy.long_entry_price) * signal.amount
        elif signal.type == SignalType.BUY and signal.amount < 0:
            if hasattr(self.strategy, 'short_entry_price') and self.strategy.short_entry_price > 0:
                return (self.strategy.short_entry_price - signal.price) * abs(signal.amount)
        return 0.0
    
    async def _maybe_ai_review(self, current_price: float):
        """Run AI review if interval has passed."""
        if not self.config.ai_periodic_review:
            return
        
        if self.last_review is not None:
            interval = timedelta(minutes=self.config.review_interval_minutes)
            if datetime.now(timezone.utc) - self.last_review < interval:
                return
        
        data = await self._fetch_market_data()
        
        review = await self.strategy.periodic_review(
            current_price=current_price,
            indicators=data["indicators"],
            position_value=self.strategy.paper_holdings * current_price,
            unrealized_pnl=0,
        )
        
        self.last_review = datetime.now(timezone.utc)
        
        # Handle AI decision
        if review["action"] == "STOP":
            logger.warning(f"🛑 AI says STOP: {review['reason']}")
            self.state = BotState.WAITING
            
            await self.alert_manager.send_status_alert(
                status="stopped",
                symbol=self.symbol,
                current_price=current_price,
                reason=f"AI decision: {review['reason']}",
            )
            
        elif review["action"] == "PAUSE":
            logger.warning(f"⏸️ AI says PAUSE: {review['reason']}")
            self.state = BotState.PAUSED
            
            await self.alert_manager.send_status_alert(
                status="paused",
                symbol=self.symbol,
                current_price=current_price,
                reason=f"AI decision: {review['reason']}",
            )
            
        elif review["action"] in ("CONTINUE", "HOLD"):
            # If we were paused by AI, resume trading
            if self.state == BotState.PAUSED:
                logger.info(f"▶️ AI says {review['action']}: resuming from PAUSE")
                self.state = BotState.TRADING
                
                await self.alert_manager.send_status_alert(
                    status="trading",
                    symbol=self.symbol,
                    current_price=current_price,
                    reason=f"AI resumed: {review['reason']}",
                )
            
        elif review["action"] == "ADJUST":
            logger.info(f"🔧 AI adjusted grid: {review['reason']}")

    async def _maybe_fetch_news(self):
        """Fetch news and update sentiment context periodically (~15 min)."""
        now = datetime.now(timezone.utc)
        if self._last_news_fetch is not None:
            if now - self._last_news_fetch < self._news_fetch_interval:
                return

        try:
            articles = await self.news_fetcher.fetch_all()
            if articles:
                # Convert NewsArticle objects to dicts for sentiment analyzer
                article_dicts = [
                    {"text": a.full_text, "metadata": a.to_metadata()}
                    for a in articles
                ]
                sentiment = self.sentiment_analyzer.analyze_articles(article_dicts)
                self._news_sentiment_context = self.sentiment_analyzer.to_ai_context(sentiment)
                logger.info(
                    f"📰 News sentiment updated: {sentiment.level.value} "
                    f"(score: {sentiment.score:+.2f}, {sentiment.article_count} articles)"
                )
            else:
                logger.debug("No news articles fetched")
        except Exception as e:
            logger.warning(f"News fetch failed: {e}")

        self._last_news_fetch = now

    def _print_status(self, current_price: float):
        """Print current status."""
        status = self.strategy.get_status() if self.strategy else {}
        paper = status.get("paper_trading", {})
        
        runtime = datetime.now(timezone.utc) - self.start_time if self.start_time else timedelta()
        
        state_emoji = {
            BotState.WAITING: "⏳",
            BotState.TRADING: "📈",
            BotState.PAUSED: "⏸️",
        }.get(self.state, "❓")
        
        engine_info = self.strategy_engine.get_status()
        active_strat = engine_info.get("active_strategy", "N/A")
        regime = engine_info.get("current_regime", "N/A")

        logger.info(
            f"📊 Status | {state_emoji} {self.state.value.upper()} | "
            f"Price: ${current_price:,.2f} | "
            f"Trades: {paper.get('trades_count', 0)} | "
            f"Value: ${paper.get('total_value', settings.paper_initial_balance):,.2f} | "
            f"Strategy: {active_strat} | Regime: {regime} | "
            f"Runtime: {runtime}"
        )
    
    def _print_stats(self):
        """Print final statistics."""
        if not self.strategy:
            return
        
        status = self.strategy.get_status()
        paper = status.get("paper_trading", {})

        runtime = datetime.now(timezone.utc) - self.start_time if self.start_time else timedelta()
        
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
        
        profit = paper["total_value"] - settings.paper_initial_balance
        profit_pct = (profit / settings.paper_initial_balance) * 100
        logger.info(f"Profit: ${profit:+,.2f} ({profit_pct:+.2f}%)")
        logger.info("=" * 60)
        
        # Risk metrics summary
        if self.risk_metrics.total_trades > 0:
            logger.info("")
            self.risk_metrics.print_dashboard()
        
        # Daily risk summary
        daily = self.risk_limits.get_daily_summary()
        if daily:
            logger.info("")
            logger.info("📊 DAILY RISK SUMMARY")
            logger.info(f"  Daily Return: {daily.get('daily_return', 'N/A')}")
            logger.info(f"  Max Drawdown: {daily.get('max_drawdown', 'N/A')}")
            logger.info(f"  Win Rate: {daily.get('win_rate', 'N/A')}")
            logger.info(f"  Consecutive Losses: {daily.get('consecutive_losses', 0)}")
            if daily.get('trading_halted'):
                logger.warning(f"  ⚠️ Trading was halted: {daily.get('halt_reason', '')}")
        
        # Alert stats
        alert_stats = self.alert_manager.get_stats()
        logger.info("")
        logger.info("📢 ALERT STATISTICS")
        logger.info(f"  Alerts Sent: {alert_stats['alerts_sent']}")
        logger.info(f"  Alerts Blocked (rate limit): {alert_stats['alerts_blocked']}")

    def _write_shared_state(self, current_price: Optional[float] = None):
        """Write bot state to shared file for API access."""
        try:
            uptime = None
            if self.start_time:
                uptime = (datetime.now(timezone.utc) - self.start_time).total_seconds()

            grid_levels, center_price = self._collect_grid_levels()
            paper_balance, paper_holdings, paper_total, paper_trades = self._collect_paper_stats()

            state = SharedBotState(
                status="running" if self.running else "stopped",
                state=self.state.value,
                symbol=self.symbol,
                uptime_seconds=uptime,
                ticks=self.ticks,
                errors=self.errors,
                current_price=current_price,
                center_price=center_price,
                grid_levels=grid_levels,
                positions=[],
                paper_balance_usdt=paper_balance,
                paper_holdings_btc=paper_holdings,
                paper_total_value=paper_total,
                paper_trades_count=paper_trades,
            )
            state.strategy_engine = self.strategy_engine.get_status()
            write_state(state)
        except Exception as e:
            logger.debug(f"Failed to write shared state: {e}")

    def _collect_grid_levels(self) -> tuple[list, Optional[float]]:
        """Collect grid levels for state export."""
        if not self.strategy:
            return [], None
        return [
            {
                "price": level.price,
                "side": level.side.value,
                "amount": level.amount,
                "filled": level.filled,
                "order_id": level.order_id,
            }
            for level in self.strategy.levels
        ], self.strategy.center_price

    def _collect_paper_stats(self) -> tuple[float, float, float, int]:
        """Collect paper trading stats for state export."""
        _ib = settings.paper_initial_balance
        if not self.strategy:
            return _ib, 0.0, _ib, 0
        paper = self.strategy.get_status().get("paper_trading", {})
        return (
            paper.get("balance_usdt", _ib),
            paper.get("holdings_btc", 0.0),
            paper.get("total_value", _ib),
            paper.get("trades_count", 0),
        )


    async def _handle_emergency_stop(self):
        """Handle emergency stop - close positions and save state."""
        logger.critical("🚨 EMERGENCY STOP HANDLER ACTIVATED")
        
        # Send emergency alert
        await self.alert_manager.send_status_alert(
            status="emergency",
            symbol=self.symbol,
            reason="Emergency stop triggered",
        )
        
        # Update emergency stop with current state
        self.emergency_stop.exchange_client = exchange_client
        self.emergency_stop.strategy = self.strategy
        
        # Close all positions
        results = await self.emergency_stop.close_all_positions()
        
        if results["positions_closed"]:
            logger.warning(f"Closed {len(results['positions_closed'])} positions")
        if results["errors"]:
            logger.error(f"Errors during position close: {results['errors']}")
            
            # Send error alert
            await self.alert_manager.send_error_alert(
                error=f"Emergency stop errors: {results['errors']}",
                context="Emergency position close",
                level=AlertLevel.CRITICAL,
            )
        
        # Save state for recovery
        self.emergency_stop.save_state({
            "bot_state": self.state.value,
            "ticks": self.ticks,
            "errors": self.errors,
            "close_results": results,
        })
        
        # Set running to false
        self.running = False
        
        # Stop daily summary scheduler
        self.alert_manager.stop_daily_summary_scheduler()
        
        # Close alert manager
        await self.alert_manager.close()
        
        # Print final stats
        self._print_stats()
        
        logger.critical("🛑 Emergency stop complete - bot terminated")


async def run_bot():
    """Run the trading bot."""
    use_optimized = "--optimize" in sys.argv

    # Parse --strategy flag (default: "auto" for regime-based multi-strategy)
    strategy_mode = "auto"
    for arg in sys.argv:
        if arg.startswith("--strategy="):
            strategy_mode = arg.split("=", 1)[1]
        elif arg == "--strategy" and sys.argv.index(arg) + 1 < len(sys.argv):
            strategy_mode = sys.argv[sys.argv.index(arg) + 1]

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
        use_optimized=use_optimized,
        strategy_mode=strategy_mode,
    )
    
    loop = asyncio.get_running_loop()

    def signal_handler():
        asyncio.create_task(bot.stop())

    loop.add_signal_handler(signal.SIGINT, signal_handler)
    loop.add_signal_handler(signal.SIGTERM, signal_handler)

    await bot.start()


if __name__ == "__main__":
    asyncio.run(run_bot())
