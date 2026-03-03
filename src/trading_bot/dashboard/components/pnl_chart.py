"""PnL chart component."""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from typing import Optional
import pandas as pd
from datetime import datetime, timedelta


class PnLChart:
    """Component for PnL visualization."""
    
    def __init__(self):
        self.colors = {
            "profit": "#26A69A",
            "loss": "#EF5350",
            "neutral": "#9E9E9E",
            "line": "#2196F3",
        }
    
    def render_cumulative(
        self,
        pnl_history: list[dict],
        title: str = "Cumulative PnL",
    ):
        """Render cumulative PnL line chart.
        
        Args:
            pnl_history: List of PnL records with timestamp and cumulative_pnl
            title: Chart title
        """
        st.subheader(f"📈 {title}")
        
        if not pnl_history:
            st.info("No PnL history available yet.")
            return
        
        # Convert to DataFrame
        df = pd.DataFrame(pnl_history)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        
        # Create figure
        fig = go.Figure()
        
        # Add cumulative PnL line
        fig.add_trace(go.Scatter(
            x=df["timestamp"],
            y=df["cumulative_pnl"],
            mode="lines+markers",
            name="Cumulative PnL",
            line=dict(color=self.colors["line"], width=2),
            marker=dict(size=6),
            fill="tozeroy",
            fillcolor="rgba(33, 150, 243, 0.1)",
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Cumulative PnL: $%{y:,.2f}<br>"
                "<extra></extra>"
            ),
        ))
        
        # Add zero line
        fig.add_hline(y=0, line_dash="dash", line_color=self.colors["neutral"])
        
        # Layout
        fig.update_layout(
            title="",
            xaxis_title="Date",
            yaxis_title="PnL ($)",
            template="plotly_dark",
            height=350,
            margin=dict(l=50, r=50, t=30, b=50),
            showlegend=False,
        )
        
        st.plotly_chart(fig, width="stretch")
    
    def render_daily(
        self,
        pnl_history: list[dict],
        title: str = "Daily PnL",
    ):
        """Render daily PnL bar chart.
        
        Args:
            pnl_history: List of PnL records with timestamp and pnl
            title: Chart title
        """
        st.subheader(f"📊 {title}")
        
        if not pnl_history:
            st.info("No PnL history available yet.")
            return
        
        # Convert to DataFrame and group by day
        df = pd.DataFrame(pnl_history)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["date"] = df["timestamp"].dt.date
        
        daily_pnl = df.groupby("date")["pnl"].sum().reset_index()
        daily_pnl["color"] = daily_pnl["pnl"].apply(
            lambda x: self.colors["profit"] if x >= 0 else self.colors["loss"]
        )
        
        # Create figure
        fig = go.Figure()
        
        fig.add_trace(go.Bar(
            x=daily_pnl["date"],
            y=daily_pnl["pnl"],
            marker_color=daily_pnl["color"],
            hovertemplate=(
                "<b>%{x}</b><br>"
                "PnL: $%{y:,.2f}<br>"
                "<extra></extra>"
            ),
        ))
        
        # Layout
        fig.update_layout(
            title="",
            xaxis_title="Date",
            yaxis_title="Daily PnL ($)",
            template="plotly_dark",
            height=300,
            margin=dict(l=50, r=50, t=30, b=50),
        )
        
        st.plotly_chart(fig, width="stretch")
    
    def render_summary(self, pnl_summary: dict):
        """Render PnL summary metrics.
        
        Args:
            pnl_summary: PnL summary from API
        """
        st.subheader("💰 PnL Summary")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            total_pnl = pnl_summary.get("total_pnl", 0)
            delta_color = "normal" if total_pnl >= 0 else "inverse"
            st.metric(
                "Total PnL",
                f"${total_pnl:,.2f}",
                delta=f"${pnl_summary.get('realized_pnl', 0):,.2f} realized",
                delta_color=delta_color,
            )
        
        with col2:
            win_rate = pnl_summary.get("win_rate", 0) * 100
            st.metric(
                "Win Rate",
                f"{win_rate:.1f}%",
                delta=f"{pnl_summary.get('winning_trades', 0)}/{pnl_summary.get('total_trades', 0)} trades",
            )
        
        with col3:
            st.metric(
                "Total Trades",
                pnl_summary.get("total_trades", 0),
                delta=f"W: {pnl_summary.get('winning_trades', 0)} / L: {pnl_summary.get('losing_trades', 0)}",
            )
