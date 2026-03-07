"""Multi-strategy engine with regime-based selection (Sprint 22)."""

from loguru import logger

from shared.strategies.base import StrategyInterface
from shared.strategies.regime import MarketRegime, MarketRegimeDetector


# Default mapping from regime to strategy name
DEFAULT_REGIME_MAP: dict[MarketRegime, str] = {
    MarketRegime.TRENDING_UP: "MomentumStrategy",
    MarketRegime.TRENDING_DOWN: "MomentumStrategy",
    MarketRegime.RANGING: "GridStrategyAdapter",
    MarketRegime.HIGH_VOLATILITY: "MomentumStrategy",
    MarketRegime.LOW_VOLATILITY: "GridStrategyAdapter",
    MarketRegime.BREAKOUT: "BreakoutStrategy",
}


class StrategyEngine:
    """Multi-strategy engine with regime-based selection."""

    def __init__(self, regime_map: dict[MarketRegime, str] | None = None):
        self.strategies: dict[str, StrategyInterface] = {}
        self.active_strategy_name: str | None = None
        self.regime_detector = MarketRegimeDetector()
        self.current_regime: MarketRegime | None = None
        self.regime_map = regime_map or dict(DEFAULT_REGIME_MAP)
        self._strategy_history: list[dict] = []

    def register(self, strategy: StrategyInterface):
        """Register a strategy."""
        self.strategies[strategy.name] = strategy
        logger.debug(f"Strategy registered: {strategy.name}")

    def unregister(self, name: str):
        """Remove a strategy from the engine."""
        if name in self.strategies:
            del self.strategies[name]
            if self.active_strategy_name == name:
                self.active_strategy_name = None

    @property
    def active_strategy(self) -> StrategyInterface | None:
        """Currently active strategy instance."""
        if self.active_strategy_name and self.active_strategy_name in self.strategies:
            return self.strategies[self.active_strategy_name]
        return None

    def select_strategy(self, candles, indicators) -> StrategyInterface | None:
        """Select best strategy based on market regime.

        high_volatility + trending -> MomentumStrategy
        low_volatility + ranging  -> GridStrategyAdapter
        oversold/overbought       -> MeanReversionStrategy
        breakout detected         -> BreakoutStrategy
        """
        regime = self.regime_detector.detect(candles, indicators)
        self.current_regime = regime

        # Check for mean reversion override based on RSI
        rsi = indicators.get("rsi_14", 50)
        if rsi < 30 or rsi > 70:
            target_name = "MeanReversionStrategy"
        else:
            target_name = self.regime_map.get(regime, "GridStrategyAdapter")

        # Resolve to registered strategy
        strategy = self.strategies.get(target_name)

        # Fallback: try any registered strategy
        if strategy is None and self.strategies:
            strategy = next(iter(self.strategies.values()))
            target_name = strategy.name

        if strategy is None:
            logger.warning("No strategies registered in engine")
            return None

        # Log regime change / strategy switch (with cooldown)
        if target_name != self.active_strategy_name:
            import time
            now = time.time()
            cooldown = getattr(self, '_switch_cooldown', 1800)  # 30 min default
            last_switch = getattr(self, '_last_switch_time', 0)
            
            if now - last_switch >= cooldown:
                old = self.active_strategy_name or "none"
                logger.info(
                    f"Strategy switch: {old} -> {target_name} "
                    f"(regime={regime.value}, RSI={rsi:.1f})"
                )
                self._strategy_history.append({
                    "from": old,
                    "to": target_name,
                    "regime": regime.value,
                    "rsi": rsi,
                })
                self.active_strategy_name = target_name
                self._last_switch_time = now
            else:
                # Keep current strategy during cooldown
                target_name = self.active_strategy_name
                strategy = self.strategies.get(target_name)

        return strategy

    def hot_swap(self, new_strategy_name: str) -> bool:
        """Switch active strategy without restart.

        Args:
            new_strategy_name: Name of the registered strategy to switch to.

        Returns:
            True if swap succeeded, False if strategy not found.
        """
        if new_strategy_name not in self.strategies:
            logger.warning(f"Hot-swap failed: strategy '{new_strategy_name}' not registered")
            return False

        old = self.active_strategy_name or "none"
        self.active_strategy_name = new_strategy_name
        logger.info(f"Hot-swap: {old} -> {new_strategy_name}")
        self._strategy_history.append({
            "from": old,
            "to": new_strategy_name,
            "regime": self.current_regime.value if self.current_regime else "manual",
            "rsi": 0,
        })
        return True

    def get_signal(self, candles, indicators, price: float) -> dict | None:
        """Get trading signal from active strategy.

        Args:
            candles: OHLCV candle data.
            indicators: Dict of precomputed indicators.
            price: Current market price.

        Returns:
            Signal dict from strategy, or None.
        """
        strategy = self.select_strategy(candles, indicators)
        if strategy is None:
            return None

        strategy.set_price(price)

        if strategy.should_cancel_entry():
            return None

        if strategy.should_long(candles, indicators):
            signal = strategy.go_long()
            signal["strategy"] = strategy.name
            signal["regime"] = self.current_regime.value if self.current_regime else "unknown"
            return signal
        elif strategy.should_short(candles, indicators):
            signal = strategy.go_short()
            signal["strategy"] = strategy.name
            signal["regime"] = self.current_regime.value if self.current_regime else "unknown"
            return signal

        return None

    def get_status(self) -> dict:
        """Get engine status for monitoring/dashboard."""
        return {
            "active_strategy": self.active_strategy_name,
            "current_regime": self.current_regime.value if self.current_regime else None,
            "registered_strategies": list(self.strategies.keys()),
            "strategy_switches": len(self._strategy_history),
            "switch_history": self._strategy_history[-10:],  # Last 10
        }

    def list_strategies(self) -> list[str]:
        """List all registered strategy names."""
        return list(self.strategies.keys())
