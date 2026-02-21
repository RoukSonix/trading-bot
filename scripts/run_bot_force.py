#!/usr/bin/env python3
"""Run bot ignoring AI startup recommendation (but keeping periodic review).

Use this to test the bot even when AI doesn't approve market conditions.
AI will still monitor and can stop the bot during periodic reviews.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from trading_bot.bot import TradingBot
from trading_bot.strategies import AIGridConfig


async def main():
    bot = TradingBot(
        symbol="BTC/USDT",
        config=AIGridConfig(
            grid_levels=5,
            grid_spacing_pct=1.5,
            amount_per_level=0.0001,
            # AI settings
            ai_enabled=True,
            ai_required_for_start=False,  # Start even if AI says no
            ai_confirm_signals=False,
            ai_auto_optimize=False,       # Use default grid (AI didn't approve)
            ai_periodic_review=True,      # But keep monitoring
            review_interval_minutes=5,    # Review every 5 min for testing
            min_confidence=30,
            risk_tolerance="medium",
        ),
    )
    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
