"""Trade history API endpoints."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from shared.core.database import get_session, Trade, TradeLog

router = APIRouter()


class TradeResponse(BaseModel):
    """Trade record response."""
    id: int
    symbol: str
    side: str
    price: float
    amount: float
    cost: float
    fee: float
    order_id: Optional[str]
    timestamp: int
    created_at: datetime


class TradeListResponse(BaseModel):
    """Trade list response."""
    trades: list[TradeResponse]
    total: int
    page: int
    per_page: int


class PnLSummary(BaseModel):
    """PnL summary."""
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float


@router.get("", response_model=TradeListResponse)
async def get_trades(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    side: Optional[str] = Query(None, description="Filter by side (buy/sell)"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Items per page"),
):
    """Get trade history with pagination."""
    session = get_session()
    try:
        query = session.query(Trade)
        
        if symbol:
            query = query.filter(Trade.symbol == symbol)
        if side:
            query = query.filter(Trade.side == side)
        
        total = query.count()
        trades = (
            query
            .order_by(Trade.timestamp.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        
        return TradeListResponse(
            trades=[
                TradeResponse(
                    id=t.id,
                    symbol=t.symbol,
                    side=t.side,
                    price=t.price,
                    amount=t.amount,
                    cost=t.cost,
                    fee=t.fee or 0,
                    order_id=t.order_id,
                    timestamp=t.timestamp,
                    created_at=t.created_at,
                )
                for t in trades
            ],
            total=total,
            page=page,
            per_page=per_page,
        )
    finally:
        session.close()


@router.get("/pnl", response_model=PnLSummary)
async def get_pnl_summary(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
):
    """Get PnL summary."""
    session = get_session()
    try:
        query = session.query(TradeLog)
        if symbol:
            query = query.filter(TradeLog.symbol == symbol)
        
        logs = query.all()
        
        realized_pnl = sum(float(log.pnl or 0) for log in logs)
        unrealized_pnl = 0  # Would need live position data

        winning = [log for log in logs if float(log.pnl or 0) > 0]
        losing = [log for log in logs if float(log.pnl or 0) < 0]
        
        total_trades = len(logs)
        win_rate = len(winning) / total_trades if total_trades > 0 else 0
        
        return PnLSummary(
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            total_pnl=realized_pnl + unrealized_pnl,
            total_trades=total_trades,
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate=win_rate,
        )
    finally:
        session.close()


@router.get("/history")
async def get_pnl_history(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    days: int = Query(30, ge=1, le=365, description="Number of days"),
):
    """Get PnL history for charting."""
    session = get_session()
    try:
        query = session.query(TradeLog)
        if symbol:
            query = query.filter(TradeLog.symbol == symbol)
        
        logs = query.order_by(TradeLog.timestamp.asc()).all()

        # Cumulative PnL
        cumulative = 0
        history = []
        for log in logs:
            if log.pnl is not None:
                cumulative += log.pnl
                history.append({
                    "timestamp": log.datetime_utc.isoformat(),
                    "pnl": float(log.pnl),
                    "cumulative_pnl": cumulative,
                    "symbol": log.symbol,
                })
        
        return {"history": history}
    finally:
        session.close()
