#!/usr/bin/env python3
"""Run bot with AI analysis but no optimization (uses default grid)."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from trading_bot.bot import TradingBot
from trading_bot.strategies import AIGridConfig

async def main():
    bot = TradingBot(
        symbol='BTC/USDT',
        config=AIGridConfig(
            grid_levels=5,
            grid_spacing_pct=1.5,
            amount_per_level=0.0001,
            ai_enabled=True,
            ai_confirm_signals=False,
            ai_auto_optimize=False,  # Use default grid, skip AI optimization
            ai_periodic_review=True,
            review_interval_minutes=15,
            min_confidence=30,
        ),
    )
    await bot.start()

if __name__ == "__main__":
    asyncio.run(main())
