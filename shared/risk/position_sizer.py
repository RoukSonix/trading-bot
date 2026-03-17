"""Position sizing strategies for risk management."""
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from loguru import logger


class SizingMethod(Enum):
    """Position sizing method."""
    FIXED_AMOUNT = "fixed_amount"      # Fixed $ amount per trade
    FIXED_PERCENT = "fixed_percent"    # Fixed % of portfolio per trade
    KELLY = "kelly"                    # Kelly criterion (optimal sizing)
    HALF_KELLY = "half_kelly"          # Conservative Kelly (50%)
    ATR_BASED = "atr_based"            # Size based on ATR (volatility)


@dataclass
class PositionSize:
    """Calculated position size."""
    amount: float           # Amount in base currency (e.g., BTC)
    value: float            # Value in quote currency (e.g., USDT)
    risk_amount: float      # Max risk in quote currency
    method: SizingMethod
    reasoning: str


class PositionSizer:
    """Calculate optimal position sizes based on risk parameters."""
    
    def __init__(
        self,
        method: SizingMethod = SizingMethod.FIXED_PERCENT,
        risk_per_trade: float = 0.02,      # 2% risk per trade
        max_position_pct: float = 0.10,    # Max 10% of portfolio in one position
        kelly_win_rate: float = 0.55,      # Expected win rate for Kelly
        kelly_win_loss_ratio: float = 1.5, # Avg win / avg loss for Kelly
    ):
        self.method = method
        self.risk_per_trade = risk_per_trade
        self.max_position_pct = max_position_pct
        self.kelly_win_rate = kelly_win_rate
        self.kelly_win_loss_ratio = kelly_win_loss_ratio
        
        logger.info(f"PositionSizer initialized: {method.value}, risk={risk_per_trade*100}%")
    
    def calculate(
        self,
        portfolio_value: float,
        entry_price: float,
        stop_loss_price: Optional[float] = None,
        atr: Optional[float] = None,
        fixed_amount: Optional[float] = None,
    ) -> PositionSize:
        """
        Calculate position size based on configured method.
        
        Args:
            portfolio_value: Total portfolio value in quote currency
            entry_price: Entry price for the trade
            stop_loss_price: Stop-loss price (required for risk-based sizing)
            atr: Average True Range (for ATR-based sizing)
            fixed_amount: Fixed amount for FIXED_AMOUNT method
            
        Returns:
            PositionSize with calculated amount and reasoning
        """
        if entry_price <= 0:
            raise ValueError(f"entry_price must be positive, got {entry_price}")
        if portfolio_value <= 0:
            raise ValueError(f"portfolio_value must be positive, got {portfolio_value}")

        if self.method == SizingMethod.FIXED_AMOUNT:
            return self._fixed_amount(portfolio_value, entry_price, fixed_amount)
        elif self.method == SizingMethod.FIXED_PERCENT:
            return self._fixed_percent(portfolio_value, entry_price)
        elif self.method == SizingMethod.KELLY:
            return self._kelly(portfolio_value, entry_price, full=True)
        elif self.method == SizingMethod.HALF_KELLY:
            return self._kelly(portfolio_value, entry_price, full=False)
        elif self.method == SizingMethod.ATR_BASED:
            return self._atr_based(portfolio_value, entry_price, stop_loss_price, atr)
        else:
            raise ValueError(f"Unknown sizing method: {self.method}")
    
    def _fixed_amount(
        self,
        portfolio_value: float,
        entry_price: float,
        fixed_amount: Optional[float],
    ) -> PositionSize:
        """Fixed dollar amount per trade."""
        amount_usd = fixed_amount or (portfolio_value * self.risk_per_trade)
        amount_base = amount_usd / entry_price
        
        # Cap at max position
        max_value = portfolio_value * self.max_position_pct
        if amount_usd > max_value:
            amount_usd = max_value
            amount_base = amount_usd / entry_price
        
        return PositionSize(
            amount=amount_base,
            value=amount_usd,
            risk_amount=amount_usd,  # Full position at risk
            method=SizingMethod.FIXED_AMOUNT,
            reasoning=f"Fixed ${amount_usd:.2f} ({amount_usd/portfolio_value*100:.1f}% of portfolio)",
        )
    
    def _fixed_percent(
        self,
        portfolio_value: float,
        entry_price: float,
    ) -> PositionSize:
        """Fixed percentage of portfolio per trade."""
        amount_usd = portfolio_value * self.risk_per_trade
        amount_base = amount_usd / entry_price
        
        # Cap at max position
        max_value = portfolio_value * self.max_position_pct
        if amount_usd > max_value:
            amount_usd = max_value
            amount_base = amount_usd / entry_price
        
        return PositionSize(
            amount=amount_base,
            value=amount_usd,
            risk_amount=amount_usd,
            method=SizingMethod.FIXED_PERCENT,
            reasoning=f"{self.risk_per_trade*100:.1f}% of portfolio = ${amount_usd:.2f}",
        )
    
    def _kelly(
        self,
        portfolio_value: float,
        entry_price: float,
        full: bool = True,
    ) -> PositionSize:
        """
        Kelly criterion for optimal position sizing.
        
        Kelly % = W - [(1-W) / R]
        Where:
            W = Win rate (probability of winning)
            R = Win/Loss ratio (avg win / avg loss)
        """
        w = self.kelly_win_rate
        r = self.kelly_win_loss_ratio
        
        # Kelly formula
        kelly_pct = w - ((1 - w) / r)
        
        # Use half Kelly for more conservative sizing
        if not full:
            kelly_pct *= 0.5
        
        # Ensure positive and capped
        kelly_pct = max(0, min(kelly_pct, self.max_position_pct))
        
        amount_usd = portfolio_value * kelly_pct
        amount_base = amount_usd / entry_price
        
        method_name = "Kelly" if full else "Half-Kelly"
        
        return PositionSize(
            amount=amount_base,
            value=amount_usd,
            risk_amount=amount_usd,
            method=SizingMethod.KELLY if full else SizingMethod.HALF_KELLY,
            reasoning=f"{method_name}: {kelly_pct*100:.1f}% (W={w:.0%}, R={r:.1f})",
        )
    
    def _atr_based(
        self,
        portfolio_value: float,
        entry_price: float,
        stop_loss_price: Optional[float],
        atr: Optional[float],
    ) -> PositionSize:
        """
        ATR-based position sizing.
        
        Position size = (Risk Amount) / (ATR * multiplier)
        This ensures consistent risk across different volatility levels.
        """
        if atr is None:
            # Fallback to fixed percent
            return self._fixed_percent(portfolio_value, entry_price)
        
        risk_amount = portfolio_value * self.risk_per_trade
        
        # Use 2x ATR as default stop distance
        atr_multiplier = 2.0
        stop_distance = atr * atr_multiplier
        
        # If explicit stop-loss provided, use that
        if stop_loss_price:
            stop_distance = abs(entry_price - stop_loss_price)
        
        # Position size = risk / stop distance
        if stop_distance > 0:
            amount_base = risk_amount / stop_distance
            amount_usd = amount_base * entry_price
        else:
            amount_usd = portfolio_value * self.risk_per_trade
            amount_base = amount_usd / entry_price
        
        # Cap at max position
        max_value = portfolio_value * self.max_position_pct
        if amount_usd > max_value:
            amount_usd = max_value
            amount_base = amount_usd / entry_price
        
        return PositionSize(
            amount=amount_base,
            value=amount_usd,
            risk_amount=risk_amount,
            method=SizingMethod.ATR_BASED,
            reasoning=f"ATR-based: ${amount_usd:.2f} (ATR=${atr:.2f}, stop=${stop_distance:.2f})",
        )
    
    def update_kelly_params(self, win_rate: float, win_loss_ratio: float):
        """Update Kelly parameters based on trading history."""
        self.kelly_win_rate = win_rate
        self.kelly_win_loss_ratio = win_loss_ratio
        logger.info(f"Kelly params updated: W={win_rate:.1%}, R={win_loss_ratio:.2f}")
