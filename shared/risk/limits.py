"""Risk limits - daily loss, max drawdown, etc."""
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import List, Optional
from loguru import logger


class LimitStatus(Enum):
    """Status of risk limits."""
    OK = "ok"                    # All limits OK
    WARNING = "warning"          # Approaching limits
    BREACHED = "breached"        # Limit breached - stop trading


@dataclass
class DailyStats:
    """Daily trading statistics."""
    date: date
    starting_balance: float
    current_balance: float
    high_water_mark: float      # Highest balance today
    trades_count: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    max_drawdown: float = 0.0   # Max drawdown from HWM
    
    @property
    def win_rate(self) -> float:
        """Calculate win rate."""
        if self.trades_count == 0:
            return 0.0
        return self.winning_trades / self.trades_count
    
    @property
    def daily_return(self) -> float:
        """Calculate daily return percentage."""
        if self.starting_balance == 0:
            return 0.0
        return (self.current_balance - self.starting_balance) / self.starting_balance
    
    @property
    def current_drawdown(self) -> float:
        """Calculate current drawdown from HWM."""
        if self.high_water_mark == 0:
            return 0.0
        return (self.high_water_mark - self.current_balance) / self.high_water_mark


@dataclass
class RiskLimits:
    """
    Risk limits manager.
    
    Tracks:
    - Daily loss limit
    - Max drawdown limit
    - Max consecutive losses
    - Trade frequency limits
    """
    
    # Limits
    daily_loss_limit: float = 0.05       # 5% max daily loss
    max_drawdown_limit: float = 0.10     # 10% max drawdown
    max_consecutive_losses: int = 5       # Max losing streak
    max_trades_per_day: int = 50          # Max trades per day
    warning_threshold: float = 0.7        # Warn at 70% of limit
    
    # State
    initial_balance: float = 0.0
    high_water_mark: float = 0.0
    daily_stats: Optional[DailyStats] = None
    consecutive_losses: int = 0
    trading_halted: bool = False
    halt_reason: str = ""
    
    # History
    trade_history: List[dict] = field(default_factory=list)
    
    def __post_init__(self):
        """Initialize daily stats."""
        self._reset_daily_stats()
        logger.info(
            f"RiskLimits initialized: "
            f"daily_loss={self.daily_loss_limit*100}%, "
            f"max_dd={self.max_drawdown_limit*100}%"
        )
    
    def _reset_daily_stats(self):
        """Reset daily statistics."""
        today = date.today()
        balance = self.daily_stats.current_balance if self.daily_stats else self.initial_balance
        
        self.daily_stats = DailyStats(
            date=today,
            starting_balance=balance,
            current_balance=balance,
            high_water_mark=max(balance, self.high_water_mark),
        )
    
    def set_initial_balance(self, balance: float):
        """Set initial balance (call at startup)."""
        self.initial_balance = balance
        self.high_water_mark = balance
        self._reset_daily_stats()
        self.daily_stats.starting_balance = balance
        self.daily_stats.current_balance = balance
        self.daily_stats.high_water_mark = balance
        logger.info(f"Initial balance set: ${balance:,.2f}")
    
    def update_balance(self, new_balance: float):
        """Update current balance and check limits."""
        if self.daily_stats is None:
            self._reset_daily_stats()
        
        # Check if new day
        if self.daily_stats.date != date.today():
            self._reset_daily_stats()
            self.consecutive_losses = 0  # Reset streak on new day

            # Only auto-resume if halt was daily-scoped (not max drawdown)
            if self.trading_halted and "drawdown" not in self.halt_reason.lower():
                self.trading_halted = False
                self.halt_reason = ""
        
        old_balance = self.daily_stats.current_balance
        self.daily_stats.current_balance = new_balance
        
        # Update high water mark
        if new_balance > self.high_water_mark:
            self.high_water_mark = new_balance
        if new_balance > self.daily_stats.high_water_mark:
            self.daily_stats.high_water_mark = new_balance
        
        # Calculate max drawdown
        dd = (self.high_water_mark - new_balance) / self.high_water_mark if self.high_water_mark > 0 else 0
        if dd > self.daily_stats.max_drawdown:
            self.daily_stats.max_drawdown = dd
    
    def record_trade(self, pnl: float, trade_info: dict = None):
        """Record a trade and update statistics."""
        if self.daily_stats is None:
            self._reset_daily_stats()
        
        self.daily_stats.trades_count += 1
        self.daily_stats.realized_pnl += pnl
        self.daily_stats.total_pnl = (
            self.daily_stats.current_balance - self.daily_stats.starting_balance
        )
        
        if pnl >= 0:
            self.daily_stats.winning_trades += 1
            self.consecutive_losses = 0
        else:
            self.daily_stats.losing_trades += 1
            self.consecutive_losses += 1
        
        # Record to history
        if trade_info:
            trade_info["pnl"] = pnl
            trade_info["timestamp"] = datetime.now()
            self.trade_history.append(trade_info)
        
        # Check limits after trade
        self.check_limits()
    
    def check_limits(self) -> LimitStatus:
        """
        Check all risk limits.
        
        Returns:
            LimitStatus indicating current state
        """
        if self.daily_stats is None:
            return LimitStatus.OK
        
        # Check daily loss limit
        daily_loss = -self.daily_stats.daily_return if self.daily_stats.daily_return < 0 else 0
        if daily_loss >= self.daily_loss_limit:
            self._halt_trading(f"Daily loss limit breached: {daily_loss*100:.1f}%")
            return LimitStatus.BREACHED
        
        # Check max drawdown (from overall HWM, not daily)
        current_dd = (
            (self.high_water_mark - self.daily_stats.current_balance) / self.high_water_mark
            if self.high_water_mark > 0 else 0.0
        )
        if current_dd >= self.max_drawdown_limit:
            self._halt_trading(f"Max drawdown breached: {current_dd*100:.1f}%")
            return LimitStatus.BREACHED
        
        # Check consecutive losses
        if self.consecutive_losses >= self.max_consecutive_losses:
            self._halt_trading(f"Max consecutive losses: {self.consecutive_losses}")
            return LimitStatus.BREACHED
        
        # Check max trades per day
        if self.daily_stats.trades_count >= self.max_trades_per_day:
            self._halt_trading(f"Max daily trades reached: {self.daily_stats.trades_count}")
            return LimitStatus.BREACHED
        
        # Check warning thresholds
        if (daily_loss >= self.daily_loss_limit * self.warning_threshold or
            current_dd >= self.max_drawdown_limit * self.warning_threshold or
            self.consecutive_losses >= self.max_consecutive_losses - 2):
            logger.warning(
                f"⚠️ Approaching limits: "
                f"daily_loss={daily_loss*100:.1f}%, "
                f"drawdown={current_dd*100:.1f}%, "
                f"losses={self.consecutive_losses}"
            )
            return LimitStatus.WARNING
        
        return LimitStatus.OK
    
    def _halt_trading(self, reason: str):
        """Halt trading due to limit breach."""
        self.trading_halted = True
        self.halt_reason = reason
        logger.error(f"🛑 TRADING HALTED: {reason}")
    
    def can_trade(self) -> tuple[bool, str]:
        """
        Check if trading is allowed.
        
        Returns:
            Tuple of (allowed, reason)
        """
        if self.trading_halted:
            return False, self.halt_reason
        
        status = self.check_limits()
        if status == LimitStatus.BREACHED:
            return False, self.halt_reason
        
        return True, "OK"
    
    def get_remaining_risk(self) -> dict:
        """Get remaining risk budget."""
        if self.daily_stats is None:
            return {}
        
        daily_loss = -self.daily_stats.daily_return if self.daily_stats.daily_return < 0 else 0
        current_dd = self.daily_stats.current_drawdown
        
        return {
            "daily_loss_used": daily_loss,
            "daily_loss_remaining": max(0, self.daily_loss_limit - daily_loss),
            "drawdown_used": current_dd,
            "drawdown_remaining": max(0, self.max_drawdown_limit - current_dd),
            "consecutive_losses": self.consecutive_losses,
            "trades_remaining": self.max_trades_per_day - self.daily_stats.trades_count,
        }
    
    def force_resume(self):
        """Force resume trading (manual override)."""
        self.trading_halted = False
        self.halt_reason = ""
        logger.warning("⚠️ Trading manually resumed - use with caution!")
    
    def get_daily_summary(self) -> dict:
        """Get daily trading summary."""
        if self.daily_stats is None:
            return {}
        
        return {
            "date": self.daily_stats.date.isoformat(),
            "starting_balance": self.daily_stats.starting_balance,
            "current_balance": self.daily_stats.current_balance,
            "total_pnl": self.daily_stats.total_pnl,
            "daily_return": f"{self.daily_stats.daily_return*100:.2f}%",
            "trades": self.daily_stats.trades_count,
            "win_rate": f"{self.daily_stats.win_rate*100:.1f}%",
            "max_drawdown": f"{self.daily_stats.max_drawdown*100:.2f}%",
            "consecutive_losses": self.consecutive_losses,
            "trading_halted": self.trading_halted,
            "halt_reason": self.halt_reason,
        }
