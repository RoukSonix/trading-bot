#!/usr/bin/env python3
"""Run paper trading with optimized config and risk management."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # monorepo root (for shared.*)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from binance_bot.bot import TradingBot
from binance_bot.strategies import AIGridConfig


async def main():
    """Run paper trading with best config from backtests."""
    
    # Best config: levels_10_sp2.5 (2.5% spacing, 10 levels)
    bot = TradingBot(
        symbol="BTC/USDT",
        config=AIGridConfig(
            grid_levels=10,
            grid_spacing_pct=2.5,  # Best from backtest
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
    
    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
