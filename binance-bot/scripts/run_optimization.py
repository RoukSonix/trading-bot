#!/usr/bin/env python3
"""Run Optuna hyperparameter optimization for the grid strategy.

Usage:
    python run_optimization.py --symbol BTC/USDT --timeframe 1h --trials 100 --timeout 3600
"""

import argparse
import json
import sys
from pathlib import Path

# Add src paths
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # monorepo root
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from loguru import logger

from binance_bot.core.exchange import exchange_client
from shared.core.indicators import Indicators
from shared.optimization.optimizer import GridOptimizer
from shared.optimization.walk_forward import WalkForwardOptimizer


def setup_logging():
    """Configure logging."""
    logger.remove()
    logger.add(
        sys.stdout,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | <cyan>{message}</cyan>",
    )


def parse_args():
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Optimize grid strategy hyperparameters")
    parser.add_argument("--symbol", default="BTC/USDT", help="Trading pair (default: BTC/USDT)")
    parser.add_argument("--timeframe", default="1h", help="Candle timeframe (default: 1h)")
    parser.add_argument("--candles", type=int, default=1000, help="Number of candles to fetch (default: 1000)")
    parser.add_argument("--trials", type=int, default=100, help="Number of Optuna trials (default: 100)")
    parser.add_argument("--timeout", type=int, default=3600, help="Timeout in seconds (default: 3600)")
    parser.add_argument("--walk-forward", action="store_true", help="Run walk-forward optimization")
    parser.add_argument("--wf-windows", type=int, default=5, help="Walk-forward windows (default: 5)")
    parser.add_argument("--output", default=None, help="Output JSON path (default: data/optimized_params.json)")
    return parser.parse_args()


def main():
    """Run optimization."""
    args = parse_args()
    setup_logging()

    output_path = args.output or str(
        Path(__file__).resolve().parent.parent.parent / "data" / "optimized_params.json"
    )

    logger.info("=" * 60)
    logger.info("GRID STRATEGY HYPERPARAMETER OPTIMIZATION")
    logger.info("=" * 60)
    logger.info(f"Symbol: {args.symbol}")
    logger.info(f"Timeframe: {args.timeframe}")
    logger.info(f"Candles: {args.candles}")
    logger.info(f"Trials: {args.trials}")
    logger.info(f"Timeout: {args.timeout}s")
    logger.info(f"Walk-forward: {args.walk_forward}")
    logger.info("")

    # Fetch data
    logger.info("Connecting to exchange...")
    exchange_client.connect()

    logger.info(f"Fetching {args.candles} candles...")
    ohlcv = exchange_client.get_ohlcv(args.symbol, timeframe=args.timeframe, limit=args.candles)
    df = Indicators.to_dataframe(ohlcv)
    df = Indicators.add_all_indicators(df)

    logger.info(f"Loaded {len(df)} candles")
    logger.info(f"Date range: {df.index[0]} to {df.index[-1]}")
    logger.info(f"Price range: ${df['low'].min():,.2f} - ${df['high'].max():,.2f}")
    logger.info("")

    optimizer = GridOptimizer(symbol=args.symbol)

    if args.walk_forward:
        # Walk-forward optimization
        wf = WalkForwardOptimizer(optimizer)
        results = wf.run(
            data=df,
            n_windows=args.wf_windows,
            n_trials=args.trials,
            timeout=args.timeout,
        )

        # Save all window results
        wf_path = output_path.replace(".json", "_walk_forward.json")
        Path(wf_path).parent.mkdir(parents=True, exist_ok=True)
        with open(wf_path, "w") as f:
            json.dump(results, f, indent=2)
        logger.info(f"Walk-forward results saved to {wf_path}")

        # Use the last window's best params as the final recommendation
        if results:
            best_params = results[-1]["best_params"]
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                json.dump({"symbol": args.symbol, **best_params}, f, indent=2)
            logger.info(f"Best params saved to {output_path}")
    else:
        # Standard optimization
        best_params, best_sharpe = optimizer.optimize(
            data=df,
            n_trials=args.trials,
            timeout=args.timeout,
        )
        optimizer.save_best_params(output_path)

        # Print history
        history = optimizer.get_optimization_history()
        if history:
            logger.info("")
            logger.info(f"Top 5 trials by Sharpe ratio:")
            sorted_hist = sorted(history, key=lambda h: h["sharpe_ratio"], reverse=True)[:5]
            for h in sorted_hist:
                logger.info(
                    f"  Trial {h['trial']:>3}: "
                    f"Sharpe={h['sharpe_ratio']:.4f}  "
                    f"Return={h.get('total_return', 0):+.2f}%  "
                    f"MaxDD={h.get('max_drawdown', 0):.2f}%  "
                    f"Trades={h.get('total_trades', 0)}"
                )

    logger.info("")
    logger.info("Optimization complete!")


if __name__ == "__main__":
    main()
