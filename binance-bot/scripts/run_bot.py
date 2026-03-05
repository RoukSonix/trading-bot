#!/usr/bin/env python3
"""Run the trading bot with state management.

Bot states:
- WAITING: Checking for good market conditions
- TRADING: Actively trading with grid strategy  
- PAUSED: AI recommended pause, monitoring for resume
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # monorepo root (for shared.*)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from binance_bot.bot import run_bot

if __name__ == "__main__":
    asyncio.run(run_bot())
