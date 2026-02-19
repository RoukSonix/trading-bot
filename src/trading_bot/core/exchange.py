"""Exchange client for Binance using CCXT."""

import ccxt
from loguru import logger
from typing import Optional
from decimal import Decimal

from trading_bot.config import settings


class ExchangeClient:
    """Binance exchange client wrapper."""
    
    def __init__(self):
        """Initialize exchange client."""
        self._exchange: Optional[ccxt.binance] = None
    
    def connect(self) -> None:
        """Connect to exchange."""
        logger.info(f"Connecting to Binance ({settings.binance_env.value})...")
        
        self._exchange = ccxt.binance(settings.exchange_config)
        
        # Load markets
        self._exchange.load_markets()
        logger.info(f"Connected. Loaded {len(self._exchange.markets)} markets.")
    
    @property
    def exchange(self) -> ccxt.binance:
        """Get exchange instance."""
        if self._exchange is None:
            raise RuntimeError("Exchange not connected. Call connect() first.")
        return self._exchange
    
    def get_balance(self, currency: str = "USDT") -> dict:
        """Get account balance.
        
        Args:
            currency: Currency to get balance for (default: USDT)
            
        Returns:
            Dict with free, used, total balances
        """
        balance = self.exchange.fetch_balance()
        
        if currency in balance:
            return {
                "currency": currency,
                "free": float(balance[currency]["free"] or 0),
                "used": float(balance[currency]["used"] or 0),
                "total": float(balance[currency]["total"] or 0),
            }
        
        return {"currency": currency, "free": 0, "used": 0, "total": 0}
    
    def get_all_balances(self, min_value: float = 0.0) -> list[dict]:
        """Get all non-zero balances.
        
        Args:
            min_value: Minimum total value to include
            
        Returns:
            List of balance dicts
        """
        balance = self.exchange.fetch_balance()
        balances = []
        
        for currency, amounts in balance.items():
            if isinstance(amounts, dict) and "total" in amounts:
                total = float(amounts["total"] or 0)
                if total > min_value:
                    balances.append({
                        "currency": currency,
                        "free": float(amounts["free"] or 0),
                        "used": float(amounts["used"] or 0),
                        "total": total,
                    })
        
        return sorted(balances, key=lambda x: x["total"], reverse=True)
    
    def get_ticker(self, symbol: str = "BTC/USDT") -> dict:
        """Get current ticker for a symbol.
        
        Args:
            symbol: Trading pair (e.g., BTC/USDT)
            
        Returns:
            Ticker data with last price, bid, ask, volume
        """
        ticker = self.exchange.fetch_ticker(symbol)
        
        return {
            "symbol": symbol,
            "last": ticker["last"],
            "bid": ticker["bid"],
            "ask": ticker["ask"],
            "high": ticker["high"],
            "low": ticker["low"],
            "volume": ticker["baseVolume"],
            "change_percent": ticker["percentage"],
        }
    
    def get_order_book(self, symbol: str = "BTC/USDT", limit: int = 10) -> dict:
        """Get order book for a symbol.
        
        Args:
            symbol: Trading pair
            limit: Number of levels to fetch
            
        Returns:
            Order book with bids and asks
        """
        book = self.exchange.fetch_order_book(symbol, limit)
        
        return {
            "symbol": symbol,
            "bids": book["bids"][:limit],  # [[price, amount], ...]
            "asks": book["asks"][:limit],
            "spread": book["asks"][0][0] - book["bids"][0][0] if book["asks"] and book["bids"] else 0,
        }
    
    def get_ohlcv(
        self, 
        symbol: str = "BTC/USDT", 
        timeframe: str = "1h",
        limit: int = 100
    ) -> list[dict]:
        """Get OHLCV (candlestick) data.
        
        Args:
            symbol: Trading pair
            timeframe: Candle timeframe (1m, 5m, 15m, 1h, 4h, 1d)
            limit: Number of candles
            
        Returns:
            List of OHLCV dicts
        """
        ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        
        return [
            {
                "timestamp": candle[0],
                "open": candle[1],
                "high": candle[2],
                "low": candle[3],
                "close": candle[4],
                "volume": candle[5],
            }
            for candle in ohlcv
        ]


# Global client instance
exchange_client = ExchangeClient()
