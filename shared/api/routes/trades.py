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
        # Try TradeLog first (has explicit pnl), fallback to Trade table
        logs = session.query(TradeLog).all()
        
        if logs:
            realized_pnl = sum(float(log.pnl or 0) for log in logs)
            winning = [log for log in logs if float(log.pnl or 0) > 0]
            losing = [log for log in logs if float(log.pnl or 0) < 0]
            total_trades = len(logs)
        else:
            # Calculate P&L from Trade table (buy/sell pairs)
            query = session.query(Trade)
            if symbol:
                query = query.filter(Trade.symbol == symbol)
            trades = query.order_by(Trade.timestamp).all()
            
            total_cost_buys = sum(float(t.cost or 0) for t in trades if t.side == "buy")
            total_cost_sells = sum(float(t.cost or 0) for t in trades if t.side == "sell")
            total_amount_buys = sum(float(t.amount or 0) for t in trades if t.side == "buy")
            total_amount_sells = sum(float(t.amount or 0) for t in trades if t.side == "sell")
            
            realized_pnl = total_cost_sells - total_cost_buys
            
            # Approximate winning/losing from paired trades
            buys = [t for t in trades if t.side == "buy"]
            sells = [t for t in trades if t.side == "sell"]
            winning = [s for s in sells if any(float(s.price) > float(b.price) for b in buys)]
            losing = [s for s in sells if all(float(s.price) <= float(b.price) for b in buys)]
            total_trades = len(trades)
        
        # Get unrealized from state
        from shared.core.state import read_state
        state = read_state()
        unrealized_pnl = 0.0
        if state:
            held_btc = getattr(state, "paper_holdings_btc", 0) or 0
            if held_btc > 0 and state.current_price:
                # Unrealized = current value of holdings - avg cost
                avg_buy_price = total_cost_buys / total_amount_buys if total_amount_buys > 0 else 0
                unrealized_pnl = held_btc * (state.current_price - avg_buy_price)
        
        win_rate = len(winning) / total_trades if total_trades > 0 else 0
        
        return PnLSummary(
            realized_pnl=round(realized_pnl, 2),
            unrealized_pnl=round(unrealized_pnl, 2),
            total_pnl=round(realized_pnl + unrealized_pnl, 2),
            total_trades=total_trades,
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate=round(win_rate, 4),
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
        # Try TradeLog first, fallback to Trade
        logs = session.query(TradeLog).order_by(TradeLog.timestamp.asc()).all()
        
        if logs:
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
        
        # Fallback: build history from Trade table
        query = session.query(Trade)
        if symbol:
            query = query.filter(Trade.symbol == symbol)
        trades = query.order_by(Trade.timestamp.asc()).all()
        
        cumulative = 0
        history = []
        for t in trades:
            cost = float(t.cost or 0)
            pnl = -cost if t.side == "buy" else cost
            cumulative += pnl
            history.append({
                "timestamp": t.created_at.isoformat() if t.created_at else "",
                "pnl": round(pnl, 4),
                "cumulative_pnl": round(cumulative, 4),
                "symbol": t.symbol,
            })
        
        return {"history": history}
    finally:
        session.close()
