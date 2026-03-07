#!/usr/bin/env python3
"""Run backtesting on historical data.

Usage:
    python scripts/run_backtest.py --symbol BTC/USDT --timeframe 5m \
        --start 2025-01-01 --end 2025-12-31 \
        --strategy ai_grid --output results/backtest_2025.json
"""

import argparse
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # monorepo root
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from loguru import logger

from binance_bot.strategies import GridStrategy, GridConfig
from shared.backtest.engine import BacktestEngine
from shared.backtest.benchmark import StrategyBenchmark


def setup_logging():
    """Configure logging."""
    logger.remove()
    logger.add(
        sys.stdout,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | <cyan>{message}</cyan>",
    )


def fetch_data(symbol: str, timeframe: str, start: str, end: str):
    """Fetch historical data from exchange or generate synthetic data."""
    try:
        from binance_bot.core.exchange import exchange_client
        from shared.core.indicators import Indicators

        logger.info("Connecting to exchange...")
        exchange_client.connect()
        ohlcv = exchange_client.get_ohlcv(symbol, timeframe=timeframe, limit=1000)
        df = Indicators.to_dataframe(ohlcv)
        df = Indicators.add_all_indicators(df)
        return df
    except Exception as e:
        logger.warning(f"Exchange unavailable ({e}), using synthetic data")
        import numpy as np
        import pandas as pd

        n = 500
        np.random.seed(42)
        dates = pd.date_range(start, periods=n, freq="1h" if timeframe in ("1h", "5m", "15m") else "1D")
        returns = np.random.normal(0.0005, 0.02, n)
        prices = 50000.0 * np.cumprod(1 + returns)
        df = pd.DataFrame(
            {
                "open": prices * (1 + np.random.uniform(-0.005, 0.005, n)),
                "high": prices * (1 + np.abs(np.random.normal(0, 0.01, n))),
                "low": prices * (1 - np.abs(np.random.normal(0, 0.01, n))),
                "close": prices,
                "volume": np.random.uniform(100, 1000, n),
            },
            index=dates,
        )
        return df


def main():
    """Run backtest from CLI."""
    parser = argparse.ArgumentParser(description="Run strategy backtest")
    parser.add_argument("--symbol", default="BTC/USDT", help="Trading pair")
    parser.add_argument("--timeframe", default="1h", help="Candle timeframe")
    parser.add_argument("--start", default="2025-01-01", help="Start date (ISO)")
    parser.add_argument("--end", default="2025-12-31", help="End date (ISO)")
    parser.add_argument("--strategy", default="grid", choices=["grid", "ai_grid"], help="Strategy type")
    parser.add_argument("--levels", type=int, default=10, help="Grid levels")
    parser.add_argument("--spacing", type=float, default=1.5, help="Grid spacing %%")
    parser.add_argument("--amount", type=float, default=0.001, help="Amount per level")
    parser.add_argument("--balance", type=float, default=10000.0, help="Initial balance")
    parser.add_argument("--output", default=None, help="Output JSON file path")
    parser.add_argument("--compare-bnh", action="store_true", help="Compare with buy-and-hold")

    args = parser.parse_args()
    setup_logging()

    logger.info("=" * 50)
    logger.info("GRID STRATEGY BACKTEST (Sprint 19)")
    logger.info("=" * 50)
    logger.info(f"Symbol: {args.symbol}  Timeframe: {args.timeframe}")
    logger.info(f"Period: {args.start} -> {args.end}")
    logger.info(f"Strategy: {args.strategy}")

    # Fetch data
    df = fetch_data(args.symbol, args.timeframe, args.start, args.end)
    logger.info(f"Loaded {len(df)} candles")
    logger.info(f"Date range: {df.index[0]} to {df.index[-1]}")
    logger.info(f"Price range: ${df['low'].min():,.2f} - ${df['high'].max():,.2f}")

    # Create strategy
    config = GridConfig(
        grid_levels=args.levels,
        grid_spacing_pct=args.spacing,
        amount_per_level=args.amount,
    )

    if args.strategy == "ai_grid":
        try:
            from binance_bot.strategies import AIGridStrategy, AIGridConfig
            ai_config = AIGridConfig(
                grid_levels=args.levels,
                grid_spacing_pct=args.spacing,
                amount_per_level=args.amount,
                ai_enabled=False,  # disable AI during backtest
            )
            strategy = AIGridStrategy(symbol=args.symbol, config=ai_config)
        except ImportError:
            logger.warning("AIGridStrategy not available, falling back to GridStrategy")
            strategy = GridStrategy(symbol=args.symbol, config=config)
    else:
        strategy = GridStrategy(symbol=args.symbol, config=config)

    # Run backtest
    engine = BacktestEngine(
        symbol=args.symbol,
        timeframe=args.timeframe,
        initial_balance=args.balance,
    )

    result = engine.run(
        strategy=strategy,
        data=df,
        start_date=args.start,
        end_date=args.end,
        params={
            "name": f"{args.strategy}_{args.symbol}",
            "grid_levels": args.levels,
            "grid_spacing_pct": args.spacing,
            "amount_per_level": args.amount,
        },
    )

    # Buy-and-hold comparison
    if args.compare_bnh:
        bench = StrategyBenchmark(
            symbol=args.symbol,
            timeframe=args.timeframe,
            initial_balance=args.balance,
        )
        comp = bench.vs_buy_and_hold(result, df)
        logger.info(f"\nOutperformance vs B&H: {comp['outperformance']:+.2f}%")

    # Save output
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(result.to_dict(), f, indent=2, default=str)
        logger.info(f"Results saved to {args.output}")


if __name__ == "__main__":
    main()
