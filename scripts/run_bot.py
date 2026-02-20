#!/usr/bin/env python3
"""Run the trading bot."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import asyncio
from trading_bot.bot import run_bot

if __name__ == "__main__":
    asyncio.run(run_bot())
