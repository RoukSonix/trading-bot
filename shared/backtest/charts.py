"""Backtest visualization charts using Plotly."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from shared.backtest.engine import BacktestResult


class BacktestCharts:
    """Generate backtest visualization charts."""

    @staticmethod
    def equity_curve(result: BacktestResult) -> go.Figure:
        """Plotly equity curve chart."""
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                y=result.equity_curve,
                mode="lines",
                name="Equity",
                line=dict(color="#26A69A", width=2),
                fill="tozeroy",
                fillcolor="rgba(38,166,154,0.1)",
            )
        )
        fig.update_layout(
            title=f"Equity Curve — {result.config_name}",
            xaxis_title="Candle",
            yaxis_title="Equity ($)",
            template="plotly_dark",
            height=400,
        )
        return fig

    @staticmethod
    def drawdown_chart(result: BacktestResult) -> go.Figure:
        """Drawdown over time."""
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                y=result.drawdown_curve,
                mode="lines",
                name="Drawdown",
                line=dict(color="#EF5350", width=2),
                fill="tozeroy",
                fillcolor="rgba(239,83,80,0.15)",
            )
        )
        fig.update_layout(
            title="Drawdown",
            xaxis_title="Candle",
            yaxis_title="Drawdown (%)",
            template="plotly_dark",
            height=300,
        )
        return fig

    @staticmethod
    def monthly_returns_heatmap(result: BacktestResult) -> go.Figure:
        """Monthly returns heatmap (inspired by Jesse AI)."""
        if not result.equity_curve or len(result.equity_curve) < 2:
            fig = go.Figure()
            fig.update_layout(title="Monthly Returns — insufficient data", template="plotly_dark")
            return fig

        # Build a date-indexed equity series
        # Assume candles are evenly spaced from start_date to end_date
        try:
            dates = pd.date_range(
                start=result.start_date,
                end=result.end_date,
                periods=len(result.equity_curve),
            )
        except Exception:
            fig = go.Figure()
            fig.update_layout(title="Monthly Returns — date error", template="plotly_dark")
            return fig

        equity_series = pd.Series(result.equity_curve, index=dates)
        monthly = equity_series.resample("ME").last()
        monthly_returns = monthly.pct_change().dropna() * 100

        if monthly_returns.empty:
            fig = go.Figure()
            fig.update_layout(title="Monthly Returns — not enough months", template="plotly_dark")
            return fig

        # Build year x month grid
        years = sorted(monthly_returns.index.year.unique())
        months = list(range(1, 13))
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

        z = []
        text_vals = []
        for year in years:
            row = []
            text_row = []
            for month in months:
                mask = (monthly_returns.index.year == year) & (monthly_returns.index.month == month)
                vals = monthly_returns[mask]
                if len(vals) > 0:
                    val = vals.iloc[0]
                    row.append(val)
                    text_row.append(f"{val:+.1f}%")
                else:
                    row.append(None)
                    text_row.append("")
            z.append(row)
            text_vals.append(text_row)

        fig = go.Figure(
            data=go.Heatmap(
                z=z,
                x=month_names,
                y=[str(y) for y in years],
                text=text_vals,
                texttemplate="%{text}",
                colorscale=[[0, "#EF5350"], [0.5, "#424242"], [1, "#26A69A"]],
                zmid=0,
                hovertemplate="Year: %{y}<br>Month: %{x}<br>Return: %{text}<extra></extra>",
            )
        )
        fig.update_layout(
            title="Monthly Returns Heatmap",
            template="plotly_dark",
            height=max(250, len(years) * 60 + 100),
        )
        return fig

    @staticmethod
    def trade_distribution(result: BacktestResult) -> go.Figure:
        """Histogram of trade P&L."""
        pnls = [t.get("pnl", 0.0) for t in result.trades if t.get("type") == "SELL" and "pnl" in t]

        if not pnls:
            fig = go.Figure()
            fig.update_layout(title="Trade P&L Distribution — no completed trades", template="plotly_dark")
            return fig

        fig = go.Figure()
        fig.add_trace(
            go.Histogram(
                x=pnls,
                marker_color="#42A5F5",
                nbinsx=min(30, max(5, len(pnls) // 2)),
                name="Trade P&L",
            )
        )
        fig.update_layout(
            title="Trade P&L Distribution",
            xaxis_title="P&L ($)",
            yaxis_title="Count",
            template="plotly_dark",
            height=350,
        )
        return fig

    @staticmethod
    def comparison_table(results: list[BacktestResult]) -> str:
        """Side-by-side comparison table as formatted string."""
        if not results:
            return "No results to compare."

        header = (
            f"{'Strategy':<20} {'Return':>10} {'Win%':>8} {'MaxDD':>8} "
            f"{'Sharpe':>8} {'Sortino':>8} {'PF':>8} {'Trades':>7}"
        )
        sep = "-" * len(header)
        lines = [sep, header, sep]

        for r in results:
            lines.append(
                f"{r.config_name:<20} "
                f"{r.total_return:>+9.2f}% "
                f"{r.win_rate:>7.1f}% "
                f"{r.max_drawdown:>7.2f}% "
                f"{r.sharpe_ratio:>8.2f} "
                f"{r.sortino_ratio:>8.2f} "
                f"{r.profit_factor:>8.2f} "
                f"{r.total_trades:>7}"
            )
        lines.append(sep)
        return "\n".join(lines)
