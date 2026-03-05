"""Trade history table component."""

import streamlit as st
import pandas as pd
from datetime import datetime
from typing import Optional


class TradeTable:
    """Component for displaying trade history."""
    
    def __init__(self):
        self.side_colors = {
            "buy": "#26A69A",
            "sell": "#EF5350",
        }
    
    def render(
        self,
        trades: list[dict],
        title: str = "Trade History",
        show_pagination: bool = True,
        page: int = 1,
        total: int = 0,
        per_page: int = 50,
    ):
        """Render trade history table.
        
        Args:
            trades: List of trade records
            title: Table title
            show_pagination: Whether to show pagination controls
            page: Current page
            total: Total records
            per_page: Items per page
        """
        st.subheader(f"📋 {title}")
        
        if not trades:
            st.info("No trades recorded yet.")
            return
        
        # Convert to DataFrame
        df = pd.DataFrame(trades)
        
        # Format columns
        if "timestamp" in df.columns:
            df["time"] = pd.to_datetime(df["timestamp"], unit="ms").dt.strftime("%Y-%m-%d %H:%M")
        
        if "price" in df.columns:
            df["price_fmt"] = df["price"].apply(lambda x: f"${x:,.2f}")
        
        if "amount" in df.columns:
            df["amount_fmt"] = df["amount"].apply(lambda x: f"{x:.6f}")
        
        if "cost" in df.columns:
            df["cost_fmt"] = df["cost"].apply(lambda x: f"${x:,.2f}")
        
        if "fee" in df.columns:
            df["fee_fmt"] = df["fee"].apply(lambda x: f"${x:.4f}")
        
        # Side styling
        if "side" in df.columns:
            df["side_styled"] = df["side"].apply(
                lambda x: f"🟢 {x.upper()}" if x == "buy" else f"🔴 {x.upper()}"
            )
        
        # Select columns for display
        display_cols = ["time", "symbol", "side_styled", "price_fmt", "amount_fmt", "cost_fmt", "fee_fmt"]
        display_cols = [c for c in display_cols if c in df.columns]
        
        # Rename for display
        rename_map = {
            "time": "Time",
            "symbol": "Symbol",
            "side_styled": "Side",
            "price_fmt": "Price",
            "amount_fmt": "Amount",
            "cost_fmt": "Total",
            "fee_fmt": "Fee",
        }
        
        display_df = df[display_cols].rename(columns=rename_map)
        
        # Display table
        st.dataframe(
            display_df,
            width="stretch",
            hide_index=True,
        )
        
        # Pagination info
        if show_pagination and total > per_page:
            total_pages = (total + per_page - 1) // per_page
            st.caption(f"Page {page} of {total_pages} ({total} total trades)")
    
    def render_compact(self, trades: list[dict], limit: int = 5):
        """Render compact recent trades list.
        
        Args:
            trades: List of trade records
            limit: Maximum trades to show
        """
        st.subheader("🔄 Recent Trades")
        
        if not trades:
            st.info("No recent trades.")
            return
        
        for trade in trades[:limit]:
            timestamp = datetime.fromtimestamp(trade["timestamp"] / 1000)
            time_str = timestamp.strftime("%H:%M:%S")
            
            side = trade.get("side", "unknown")
            side_emoji = "🟢" if side == "buy" else "🔴"
            
            price = trade.get("price", 0)
            amount = trade.get("amount", 0)
            
            st.text(f"{time_str} {side_emoji} {side.upper()} {amount:.6f} @ ${price:,.2f}")
    
    def render_summary(self, trades: list[dict]):
        """Render trade summary statistics.
        
        Args:
            trades: List of trade records
        """
        if not trades:
            return
        
        df = pd.DataFrame(trades)
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Trades", len(df))
        
        with col2:
            buy_count = len(df[df["side"] == "buy"]) if "side" in df.columns else 0
            st.metric("Buy Orders", buy_count)
        
        with col3:
            sell_count = len(df[df["side"] == "sell"]) if "side" in df.columns else 0
            st.metric("Sell Orders", sell_count)
        
        with col4:
            total_volume = df["cost"].sum() if "cost" in df.columns else 0
            st.metric("Total Volume", f"${total_volume:,.2f}")
