"""Data collection and storage."""

from typing import Optional
from sqlalchemy import select
from loguru import logger

from shared.core.database import get_session, OHLCV, init_db
from binance_bot.core.exchange import exchange_client


class DataCollector:
    """Collects and stores market data."""
    
    def __init__(self):
        """Initialize data collector."""
        init_db()
    
    def fetch_and_store_ohlcv(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "1h",
        limit: int = 100,
    ) -> int:
        """Fetch OHLCV data from exchange and store in database.
        
        Args:
            symbol: Trading pair
            timeframe: Candle timeframe (1m, 5m, 15m, 1h, 4h, 1d)
            limit: Number of candles to fetch
            
        Returns:
            Number of new candles stored
        """
        # Fetch from exchange
        candles = exchange_client.get_ohlcv(symbol, timeframe, limit)
        logger.info(f"Fetched {len(candles)} candles for {symbol} {timeframe}")
        
        # Store in database
        session = get_session()
        new_count = 0
        
        try:
            for candle in candles:
                # Check if already exists
                existing = session.execute(
                    select(OHLCV).where(
                        OHLCV.symbol == symbol,
                        OHLCV.timeframe == timeframe,
                        OHLCV.timestamp == candle["timestamp"],
                    )
                ).scalar_one_or_none()
                
                if existing is None:
                    ohlcv = OHLCV(
                        symbol=symbol,
                        timeframe=timeframe,
                        timestamp=candle["timestamp"],
                        open=candle["open"],
                        high=candle["high"],
                        low=candle["low"],
                        close=candle["close"],
                        volume=candle["volume"],
                    )
                    session.add(ohlcv)
                    new_count += 1
            
            session.commit()
            logger.info(f"Stored {new_count} new candles")
            
        finally:
            session.close()
        
        return new_count
    
    def get_ohlcv(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "1h",
        limit: int = 100,
    ) -> list[dict]:
        """Get OHLCV data from database.
        
        Args:
            symbol: Trading pair
            timeframe: Candle timeframe
            limit: Maximum candles to return
            
        Returns:
            List of OHLCV dicts sorted by timestamp ascending
        """
        session = get_session()
        
        try:
            result = session.execute(
                select(OHLCV)
                .where(OHLCV.symbol == symbol, OHLCV.timeframe == timeframe)
                .order_by(OHLCV.timestamp.desc())
                .limit(limit)
            ).scalars().all()
            
            # Return in chronological order
            candles = [
                {
                    "timestamp": r.timestamp,
                    "datetime": r.datetime,
                    "open": r.open,
                    "high": r.high,
                    "low": r.low,
                    "close": r.close,
                    "volume": r.volume,
                }
                for r in reversed(result)
            ]
            
            return candles
            
        finally:
            session.close()
    
    def get_latest_price(self, symbol: str = "BTC/USDT", timeframe: str = "1h") -> Optional[float]:
        """Get latest close price from database."""
        session = get_session()
        
        try:
            result = session.execute(
                select(OHLCV.close)
                .where(OHLCV.symbol == symbol, OHLCV.timeframe == timeframe)
                .order_by(OHLCV.timestamp.desc())
                .limit(1)
            ).scalar_one_or_none()
            
            return result
            
        finally:
            session.close()
    
    def count_candles(self, symbol: str = "BTC/USDT", timeframe: str = "1h") -> int:
        """Count stored candles."""
        session = get_session()
        
        try:
            from sqlalchemy import func
            result = session.execute(
                select(func.count(OHLCV.id))
                .where(OHLCV.symbol == symbol, OHLCV.timeframe == timeframe)
            ).scalar()
            
            return result or 0
            
        finally:
            session.close()


# Global instance
data_collector = DataCollector()
