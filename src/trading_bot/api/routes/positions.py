"""Position API endpoints."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from trading_bot.core.database import get_session, Position

router = APIRouter()


class PositionResponse(BaseModel):
    """Position response."""
    id: int
    symbol: str
    side: str
    entry_price: float
    amount: float
    unrealized_pnl: float
    realized_pnl: float
    updated_at: datetime
    current_value: Optional[float] = None


class PositionListResponse(BaseModel):
    """Position list response."""
    positions: list[PositionResponse]
    total_value: float
    total_unrealized_pnl: float
    total_realized_pnl: float


@router.get("", response_model=PositionListResponse)
async def get_positions(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
):
    """Get current positions."""
    session = get_session()
    try:
        query = session.query(Position)
        if symbol:
            query = query.filter(Position.symbol == symbol)
        
        positions = query.all()
        
        total_value = sum(p.entry_price * p.amount for p in positions)
        total_unrealized = sum(p.unrealized_pnl for p in positions)
        total_realized = sum(p.realized_pnl for p in positions)
        
        return PositionListResponse(
            positions=[
                PositionResponse(
                    id=p.id,
                    symbol=p.symbol,
                    side=p.side,
                    entry_price=p.entry_price,
                    amount=p.amount,
                    unrealized_pnl=p.unrealized_pnl,
                    realized_pnl=p.realized_pnl,
                    updated_at=p.updated_at,
                    current_value=p.entry_price * p.amount,
                )
                for p in positions
            ],
            total_value=total_value,
            total_unrealized_pnl=total_unrealized,
            total_realized_pnl=total_realized,
        )
    finally:
        session.close()


@router.get("/{symbol}", response_model=PositionResponse)
async def get_position(symbol: str):
    """Get position for specific symbol."""
    session = get_session()
    try:
        position = session.query(Position).filter(Position.symbol == symbol).first()
        
        if not position:
            return PositionResponse(
                id=0,
                symbol=symbol,
                side="flat",
                entry_price=0,
                amount=0,
                unrealized_pnl=0,
                realized_pnl=0,
                updated_at=datetime.now(),
            )
        
        return PositionResponse(
            id=position.id,
            symbol=position.symbol,
            side=position.side,
            entry_price=position.entry_price,
            amount=position.amount,
            unrealized_pnl=position.unrealized_pnl,
            realized_pnl=position.realized_pnl,
            updated_at=position.updated_at,
            current_value=position.entry_price * position.amount,
        )
    finally:
        session.close()
