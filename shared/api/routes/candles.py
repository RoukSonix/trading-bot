"""Candlestick data API endpoints."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter()


class CandleResponse(BaseModel):
    """OHLCV candle response."""
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class CandleListResponse(BaseModel):
    """Candle list response."""
    candles: list[CandleResponse]
    symbol: str
    timeframe: str
    count: int


def _get_bot():
    """Get bot instance."""
    from shared.api.main import get_bot_instance
    return get_bot_instance()


@router.get("", response_model=CandleListResponse)
async def get_candles(
    symbol: str = Query("BTC/USDT", description="Trading pair"),
    timeframe: str = Query("1h", description="Candle timeframe (1m, 5m, 15m, 1h, 4h, 1d)"),
    limit: int = Query(100, ge=1, le=500, description="Number of candles to fetch"),
):
    """Get OHLCV candlestick data."""
    bot = _get_bot()
    
    candles = []
    
    # Try to fetch from exchange
    if bot and hasattr(bot, "exchange") and bot.exchange:
        try:
            ohlcv = await bot.exchange.fetch_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
            )
            
            for candle in ohlcv:
                candles.append(CandleResponse(
                    timestamp=int(candle[0]),
                    open=float(candle[1]),
                    high=float(candle[2]),
                    low=float(candle[3]),
                    close=float(candle[4]),
                    volume=float(candle[5]),
                ))
            
            return CandleListResponse(
                candles=candles,
                symbol=symbol,
                timeframe=timeframe,
                count=len(candles),
            )
        except Exception:
            pass
    
    # Fallback: try ccxt directly
    try:
        import ccxt.async_support as ccxt
        
        exchange = ccxt.binance({
            'enableRateLimit': True,
        })
        
        try:
            ohlcv = await exchange.fetch_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
            )
            
            for candle in ohlcv:
                candles.append(CandleResponse(
                    timestamp=int(candle[0]),
                    open=float(candle[1]),
                    high=float(candle[2]),
                    low=float(candle[3]),
                    close=float(candle[4]),
                    volume=float(candle[5]),
                ))
        finally:
            await exchange.close()
        
        return CandleListResponse(
            candles=candles,
            symbol=symbol,
            timeframe=timeframe,
            count=len(candles),
        )
    except ImportError:
        pass
    except Exception:
        pass
    
    # Generate mock data if no exchange available
    base_price = 85000.0
    now = datetime.now(timezone.utc)
    
    for i in range(limit):
        # Generate somewhat realistic looking data
        offset = (limit - i) * 3600 * 1000  # 1h in ms
        timestamp = int((now - timedelta(hours=limit-i)).timestamp() * 1000)
        
        # Simple random walk
        import random
        change = random.uniform(-0.02, 0.02)
        open_price = base_price * (1 + change * 0.5)
        close_price = base_price * (1 + change)
        high_price = max(open_price, close_price) * (1 + random.uniform(0, 0.005))
        low_price = min(open_price, close_price) * (1 - random.uniform(0, 0.005))
        volume = random.uniform(100, 1000)
        
        base_price = close_price
        
        candles.append(CandleResponse(
            timestamp=timestamp,
            open=round(open_price, 2),
            high=round(high_price, 2),
            low=round(low_price, 2),
            close=round(close_price, 2),
            volume=round(volume, 2),
        ))
    
    return CandleListResponse(
        candles=candles,
        symbol=symbol,
        timeframe=timeframe,
        count=len(candles),
    )


@router.get("/current-price")
async def get_current_price(
    symbol: str = Query("BTC/USDT", description="Trading pair"),
):
    """Get current price for a symbol."""
    from shared.core.state import read_state
    
    # Check shared state first
    state = read_state()
    if state and state.current_price:
        return {
            "symbol": symbol,
            "price": state.current_price,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "state",
        }
    
    # Try bot instance
    bot = _get_bot()
    if bot and bot.strategy and bot.strategy.center_price:
        return {
            "symbol": symbol,
            "price": bot.strategy.center_price,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "bot",
        }
    
    # Try fetching from exchange
    try:
        import ccxt.async_support as ccxt
        
        exchange = ccxt.binance({'enableRateLimit': True})
        try:
            ticker = await exchange.fetch_ticker(symbol)
            return {
                "symbol": symbol,
                "price": ticker.get("last", 0),
                "change_24h": ticker.get("percentage", 0),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "exchange",
            }
        finally:
            await exchange.close()
    except Exception:
        pass
    
    # Mock fallback
    return {
        "symbol": symbol,
        "price": 85000.0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "mock",
    }
