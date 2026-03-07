"""Multi-timeframe analysis for indicators."""

import pandas as pd

from shared.indicators import momentum, trend, volatility


class MultiTimeframe:
    """Analyze indicators across multiple timeframes."""

    TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]

    TIMEFRAME_WEIGHTS = {
        "1m": 0.25,
        "5m": 0.5,
        "15m": 1.0,
        "1h": 1.5,
        "4h": 2.0,
        "1d": 3.0,
    }

    def __init__(self, exchange=None, symbol: str = "BTC/USDT"):
        self.exchange = exchange
        self.symbol = symbol

    async def fetch_all_timeframes(self) -> dict[str, pd.DataFrame]:
        """Fetch candles for all timeframes via exchange.

        Returns dict mapping timeframe string to OHLCV DataFrame.
        """
        if self.exchange is None:
            raise ValueError("Exchange not configured")

        result = {}
        for tf in self.TIMEFRAMES:
            candles = await self.exchange.fetch_ohlcv(self.symbol, tf, limit=100)
            df = pd.DataFrame(
                candles, columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("datetime", inplace=True)
            result[tf] = df
        return result

    def analyze(self, candles_by_tf: dict[str, pd.DataFrame]) -> dict[str, dict]:
        """Run indicators on each timeframe.

        Returns:
            Dict mapping timeframe to analysis results, e.g.:
            {
                '1h': {'trend': 'bullish', 'rsi': 45.2, 'macd': 'bullish_cross'},
                '4h': {'trend': 'bearish', 'rsi': 65.1, 'macd': 'bearish'},
            }
        """
        analysis = {}
        for tf, df in candles_by_tf.items():
            if len(df) < 30:
                continue

            ema_short = trend.ema(df, period=12)
            ema_long = trend.ema(df, period=26)
            rsi_val = momentum.rsi(df, period=14)
            macd_line, signal_line, _ = momentum.macd(df)
            atr_val = volatility.atr(df, period=14)

            # Trend direction
            if ema_short.iloc[-1] > ema_long.iloc[-1]:
                trend_dir = "bullish"
            else:
                trend_dir = "bearish"

            # MACD state
            if macd_line.iloc[-1] > signal_line.iloc[-1]:
                if macd_line.iloc[-2] <= signal_line.iloc[-2]:
                    macd_state = "bullish_cross"
                else:
                    macd_state = "bullish"
            else:
                if macd_line.iloc[-2] >= signal_line.iloc[-2]:
                    macd_state = "bearish_cross"
                else:
                    macd_state = "bearish"

            analysis[tf] = {
                "trend": trend_dir,
                "rsi": round(float(rsi_val.iloc[-1]), 1),
                "macd": macd_state,
                "atr": round(float(atr_val.iloc[-1]), 4),
            }

        return analysis

    def consensus(self, analysis: dict[str, dict]) -> str:
        """Multi-timeframe consensus.

        Higher timeframes weighted more:
        1d = 3x, 4h = 2x, 1h = 1.5x, 15m = 1x, 5m = 0.5x, 1m = 0.25x

        Returns 'bullish', 'bearish', or 'neutral'.
        """
        if not analysis:
            return "neutral"

        score = 0.0
        total_weight = 0.0

        for tf, data in analysis.items():
            weight = self.TIMEFRAME_WEIGHTS.get(tf, 1.0)
            total_weight += weight

            # Trend component
            if data.get("trend") == "bullish":
                score += weight
            elif data.get("trend") == "bearish":
                score -= weight

            # RSI component (subtle weighting)
            rsi_val = data.get("rsi", 50)
            if rsi_val > 60:
                score += weight * 0.3
            elif rsi_val < 40:
                score -= weight * 0.3

            # MACD component
            macd_state = data.get("macd", "")
            if "bullish" in macd_state:
                score += weight * 0.5
            elif "bearish" in macd_state:
                score -= weight * 0.5

        if total_weight == 0:
            return "neutral"

        normalized = score / total_weight
        if normalized > 0.3:
            return "bullish"
        elif normalized < -0.3:
            return "bearish"
        return "neutral"
