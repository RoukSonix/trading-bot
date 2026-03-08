"""Database models and connection management."""

from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine, Column, Integer, Float, Numeric, String, DateTime, BigInteger, Index
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from loguru import logger

# Database setup
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
DATABASE_URL = f"sqlite:///{DATA_DIR}/trading.db"

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={
        "timeout": 30,           # Wait up to 30s for lock
        "check_same_thread": False,
    },
    pool_pre_ping=True,
)

# Enable WAL mode for concurrent reads/writes
from sqlalchemy import event

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class OHLCV(Base):
    """OHLCV (candlestick) data model."""
    
    __tablename__ = "ohlcv"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    timeframe = Column(String(10), nullable=False, index=True)
    timestamp = Column(BigInteger, nullable=False)  # Unix timestamp in ms
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Composite index for efficient queries
    __table_args__ = (
        Index("idx_symbol_timeframe_timestamp", "symbol", "timeframe", "timestamp", unique=True),
    )
    
    def __repr__(self):
        return f"<OHLCV {self.symbol} {self.timeframe} {self.timestamp}>"
    
    @property
    def datetime(self) -> datetime:
        """Convert timestamp to datetime."""
        return datetime.fromtimestamp(self.timestamp / 1000, tz=timezone.utc)


class Trade(Base):
    """Trade history model."""
    
    __tablename__ = "trades"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    side = Column(String(4), nullable=False)  # buy/sell
    price = Column(Numeric(precision=18, scale=8), nullable=False)
    amount = Column(Numeric(precision=18, scale=8), nullable=False)
    cost = Column(Numeric(precision=18, scale=8), nullable=False)  # price * amount
    fee = Column(Numeric(precision=18, scale=8), default=0)
    order_id = Column(String(50), nullable=True)
    timestamp = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Trade {self.side} {self.amount} {self.symbol} @ {self.price}>"


class Position(Base):
    """Current position tracking."""

    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, unique=True)
    side = Column(String(5), nullable=False)  # long/short/flat
    entry_price = Column(Numeric(precision=18, scale=8), nullable=False)
    amount = Column(Numeric(precision=18, scale=8), nullable=False)
    unrealized_pnl = Column(Numeric(precision=18, scale=8), default=0)
    realized_pnl = Column(Numeric(precision=18, scale=8), default=0)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Bi-directional fields (Sprint 20)
    direction = Column(String(5), default="long")  # "long", "short", "both"
    long_amount = Column(Numeric(precision=18, scale=8), default=0)
    short_amount = Column(Numeric(precision=18, scale=8), default=0)
    long_entry = Column(Numeric(precision=18, scale=8), default=0)
    short_entry = Column(Numeric(precision=18, scale=8), default=0)

    def __repr__(self):
        return f"<Position {self.side} {self.amount} {self.symbol}>"


def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(engine)
    logger.info(f"Database initialized: {DATABASE_URL}")


def get_session() -> Session:
    """Get database session."""
    return SessionLocal()


class TradeLog(Base):
    """Trade logging for PnL tracking and reporting."""
    
    __tablename__ = "trade_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(BigInteger, nullable=False, index=True)  # Unix timestamp in ms
    symbol = Column(String(20), nullable=False, index=True)
    side = Column(String(4), nullable=False)  # buy/sell
    price = Column(Numeric(precision=18, scale=8), nullable=False)
    amount = Column(Numeric(precision=18, scale=8), nullable=False)
    pnl = Column(Numeric(precision=18, scale=8), default=0)  # Realized PnL for this trade
    fees = Column(Numeric(precision=18, scale=8), default=0)
    order_id = Column(String(50), nullable=True)
    strategy = Column(String(50), nullable=True)  # Strategy that generated trade
    notes = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        Index("idx_trade_logs_timestamp", "timestamp"),
        Index("idx_trade_logs_symbol_timestamp", "symbol", "timestamp"),
    )
    
    def __repr__(self):
        return f"<TradeLog {self.side} {self.amount} {self.symbol} @ {self.price} PnL={self.pnl}>"
    
    @property
    def datetime_utc(self) -> datetime:
        """Convert timestamp to datetime."""
        return datetime.fromtimestamp(self.timestamp / 1000, tz=timezone.utc)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "datetime": self.datetime_utc.isoformat(),
            "symbol": self.symbol,
            "side": self.side,
            "price": self.price,
            "amount": self.amount,
            "pnl": self.pnl,
            "fees": self.fees,
            "order_id": self.order_id,
            "strategy": self.strategy,
            "notes": self.notes,
        }


def log_trade(
    symbol: str,
    side: str,
    price: float,
    amount: float,
    pnl: float = 0,
    fees: float = 0,
    order_id: str = None,
    strategy: str = None,
    notes: str = None,
    timestamp: int = None,
) -> TradeLog:
    """Log a trade to the database.
    
    Args:
        symbol: Trading pair (e.g., BTC/USDT)
        side: Trade side (buy/sell)
        price: Execution price
        amount: Trade amount
        pnl: Realized PnL (default 0)
        fees: Trading fees (default 0)
        order_id: Exchange order ID
        strategy: Strategy name
        notes: Additional notes
        timestamp: Unix timestamp in ms (default: now)
        
    Returns:
        Created TradeLog record
    """
    if timestamp is None:
        timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    
    session = get_session()
    try:
        trade = TradeLog(
            timestamp=timestamp,
            symbol=symbol,
            side=side,
            price=price,
            amount=amount,
            pnl=pnl,
            fees=fees,
            order_id=order_id,
            strategy=strategy,
            notes=notes,
        )
        session.add(trade)
        session.commit()
        session.refresh(trade)
        logger.debug(f"Logged trade: {trade}")
        return trade
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to log trade: {e}")
        raise
    finally:
        session.close()


def get_trades(
    symbol: str = None,
    start_timestamp: int = None,
    end_timestamp: int = None,
    side: str = None,
    strategy: str = None,
    limit: int = None,
) -> list[TradeLog]:
    """Get trades from the database with optional filters.
    
    Args:
        symbol: Filter by trading pair
        start_timestamp: Filter by start time (Unix ms)
        end_timestamp: Filter by end time (Unix ms)
        side: Filter by side (buy/sell)
        strategy: Filter by strategy name
        limit: Maximum number of trades to return
        
    Returns:
        List of TradeLog records
    """
    session = get_session()
    try:
        query = session.query(TradeLog)
        
        if symbol:
            query = query.filter(TradeLog.symbol == symbol)
        if start_timestamp:
            query = query.filter(TradeLog.timestamp >= start_timestamp)
        if end_timestamp:
            query = query.filter(TradeLog.timestamp <= end_timestamp)
        if side:
            query = query.filter(TradeLog.side == side)
        if strategy:
            query = query.filter(TradeLog.strategy == strategy)
        
        query = query.order_by(TradeLog.timestamp.desc())
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    finally:
        session.close()


def get_trades_summary(
    symbol: str = None,
    start_timestamp: int = None,
    end_timestamp: int = None,
    strategy: str = None,
) -> dict:
    """Get summary statistics for trades.
    
    Args:
        symbol: Filter by trading pair
        start_timestamp: Filter by start time (Unix ms)
        end_timestamp: Filter by end time (Unix ms)
        strategy: Filter by strategy name
        
    Returns:
        Dict with summary statistics
    """
    trades = get_trades(
        symbol=symbol,
        start_timestamp=start_timestamp,
        end_timestamp=end_timestamp,
        strategy=strategy,
    )
    
    if not trades:
        return {
            "total_trades": 0,
            "buy_trades": 0,
            "sell_trades": 0,
            "total_pnl": 0,
            "total_fees": 0,
            "net_pnl": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0,
            "avg_pnl": 0,
            "avg_win": 0,
            "avg_loss": 0,
            "largest_win": 0,
            "largest_loss": 0,
            "total_volume": 0,
        }
    
    pnls = [t.pnl for t in trades]
    fees = [t.fees for t in trades]
    winning = [p for p in pnls if p > 0]
    losing = [p for p in pnls if p < 0]
    
    total_pnl = sum(pnls)
    total_fees = sum(fees)
    
    return {
        "total_trades": len(trades),
        "buy_trades": sum(1 for t in trades if t.side == "buy"),
        "sell_trades": sum(1 for t in trades if t.side == "sell"),
        "total_pnl": round(total_pnl, 4),
        "total_fees": round(total_fees, 4),
        "net_pnl": round(total_pnl - total_fees, 4),
        "winning_trades": len(winning),
        "losing_trades": len(losing),
        "win_rate": round(len(winning) / len(trades) * 100, 2) if trades else 0,
        "avg_pnl": round(total_pnl / len(trades), 4) if trades else 0,
        "avg_win": round(sum(winning) / len(winning), 4) if winning else 0,
        "avg_loss": round(sum(losing) / len(losing), 4) if losing else 0,
        "largest_win": round(max(winning), 4) if winning else 0,
        "largest_loss": round(min(losing), 4) if losing else 0,
        "total_volume": round(sum(t.price * t.amount for t in trades), 4),
        "symbols": list(set(t.symbol for t in trades)),
        "strategies": list(set(t.strategy for t in trades if t.strategy)),
        "period_start": min(t.datetime_utc for t in trades).isoformat() if trades else None,
        "period_end": max(t.datetime_utc for t in trades).isoformat() if trades else None,
    }
