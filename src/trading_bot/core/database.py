"""Database models and connection management."""

from datetime import datetime
from pathlib import Path
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, BigInteger, Index
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from loguru import logger

# Database setup
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
DATABASE_URL = f"sqlite:///{DATA_DIR}/trading.db"

engine = create_engine(DATABASE_URL, echo=False)
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
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Composite index for efficient queries
    __table_args__ = (
        Index("idx_symbol_timeframe_timestamp", "symbol", "timeframe", "timestamp", unique=True),
    )
    
    def __repr__(self):
        return f"<OHLCV {self.symbol} {self.timeframe} {self.timestamp}>"
    
    @property
    def datetime(self) -> datetime:
        """Convert timestamp to datetime."""
        return datetime.utcfromtimestamp(self.timestamp / 1000)


class Trade(Base):
    """Trade history model."""
    
    __tablename__ = "trades"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    side = Column(String(4), nullable=False)  # buy/sell
    price = Column(Float, nullable=False)
    amount = Column(Float, nullable=False)
    cost = Column(Float, nullable=False)  # price * amount
    fee = Column(Float, default=0)
    order_id = Column(String(50), nullable=True)
    timestamp = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<Trade {self.side} {self.amount} {self.symbol} @ {self.price}>"


class Position(Base):
    """Current position tracking."""
    
    __tablename__ = "positions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, unique=True)
    side = Column(String(5), nullable=False)  # long/short/flat
    entry_price = Column(Float, nullable=False)
    amount = Column(Float, nullable=False)
    unrealized_pnl = Column(Float, default=0)
    realized_pnl = Column(Float, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Position {self.side} {self.amount} {self.symbol}>"


def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(engine)
    logger.info(f"Database initialized: {DATABASE_URL}")


def get_session() -> Session:
    """Get database session."""
    return SessionLocal()
