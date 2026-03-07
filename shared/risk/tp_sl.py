"""Take-Profit / Stop-Loss calculator for grid levels."""

from loguru import logger


class TPSLCalculator:
    """Calculate Take-Profit and Stop-Loss levels for grid positions."""

    @staticmethod
    def fixed_percentage(
        entry_price: float,
        side: str,
        tp_pct: float = 2.0,
        sl_pct: float = 1.0,
    ) -> tuple[float, float]:
        """Fixed percentage TP/SL.

        Args:
            entry_price: Entry/fill price.
            side: "long" or "short".
            tp_pct: Take-profit percentage.
            sl_pct: Stop-loss percentage.

        Returns:
            (take_profit_price, stop_loss_price)
        """
        if side == "long":
            tp = entry_price * (1 + tp_pct / 100)
            sl = entry_price * (1 - sl_pct / 100)
        else:  # short
            tp = entry_price * (1 - tp_pct / 100)
            sl = entry_price * (1 + sl_pct / 100)
        return tp, sl

    @staticmethod
    def atr_based(
        entry_price: float,
        side: str,
        atr: float,
        tp_multiplier: float = 2.0,
        sl_multiplier: float = 1.0,
    ) -> tuple[float, float]:
        """ATR-based dynamic TP/SL — adapts to volatility.

        Args:
            entry_price: Entry/fill price.
            side: "long" or "short".
            atr: Current ATR value.
            tp_multiplier: ATR multiplier for take-profit distance.
            sl_multiplier: ATR multiplier for stop-loss distance.

        Returns:
            (take_profit_price, stop_loss_price)
        """
        if side == "long":
            tp = entry_price + atr * tp_multiplier
            sl = entry_price - atr * sl_multiplier
        else:  # short
            tp = entry_price - atr * tp_multiplier
            sl = entry_price + atr * sl_multiplier
        return tp, sl

    @staticmethod
    def risk_reward_ratio(
        entry_price: float,
        side: str,
        sl_price: float,
        rr_ratio: float = 2.0,
    ) -> float:
        """Calculate TP based on risk-reward ratio.

        Args:
            entry_price: Entry/fill price.
            side: "long" or "short".
            sl_price: Stop-loss price.
            rr_ratio: Risk-reward ratio (e.g. 2.0 = 2:1 reward:risk).

        Returns:
            Take-profit price.
        """
        risk = abs(entry_price - sl_price)
        if side == "long":
            return entry_price + risk * rr_ratio
        return entry_price - risk * rr_ratio
