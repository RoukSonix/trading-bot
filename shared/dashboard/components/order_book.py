"""Order book component for displaying open orders."""

import streamlit as st
import pandas as pd
from datetime import datetime
from typing import Callable, Optional


class OrderBook:
    """Component for displaying and managing open orders."""
    
    def __init__(self):
        self.side_colors = {
            "buy": "#26A69A",
            "sell": "#EF5350",
        }
    
    def render(
        self,
        orders: list[dict],
        on_cancel: Optional[Callable[[str], None]] = None,
        title: str = "Open Orders",
    ):
        """Render order book table with cancel buttons.
        
        Args:
            orders: List of order records
            on_cancel: Callback for cancel button
            title: Section title
        """
        st.subheader(f"📋 {title}")
        
        if not orders:
            st.info("No open orders")
            return
        
        # Summary metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Orders", len(orders))
        with col2:
            buy_orders = [o for o in orders if o.get("side") == "buy"]
            st.metric("Buy Orders", len(buy_orders))
        with col3:
            sell_orders = [o for o in orders if o.get("side") == "sell"]
            st.metric("Sell Orders", len(sell_orders))
        
        st.divider()
        
        # Orders table
        for i, order in enumerate(orders):
            with st.container():
                col1, col2, col3, col4, col5, col6 = st.columns([1, 1.5, 1.5, 1, 1.5, 1])
                
                side = order.get("side", "buy")
                side_emoji = "🟢" if side == "buy" else "🔴"
                
                with col1:
                    st.write(f"{side_emoji} **{side.upper()}**")
                
                with col2:
                    price = order.get("price", 0)
                    st.write(f"${price:,.2f}")
                
                with col3:
                    amount = order.get("amount", 0)
                    st.write(f"{amount:.6f}")
                
                with col4:
                    status = order.get("status", "open")
                    status_emoji = "⏳" if status == "open" else "✅"
                    st.write(f"{status_emoji} {status}")
                
                with col5:
                    timestamp = order.get("timestamp")
                    if timestamp:
                        if isinstance(timestamp, str):
                            time_str = timestamp[:19]
                        else:
                            time_str = timestamp.strftime("%H:%M:%S")
                        st.write(time_str)
                    else:
                        st.write("--")
                
                with col6:
                    order_id = order.get("id", f"order_{i}")
                    if st.button("❌", key=f"cancel_{order_id}_{i}", help="Cancel order"):
                        if on_cancel:
                            on_cancel(order_id)
                        else:
                            st.session_state[f"cancel_order_{order_id}"] = True
                
                st.divider()
    
    def render_compact(self, orders: list[dict], limit: int = 5):
        """Render compact order list.
        
        Args:
            orders: List of order records
            limit: Maximum orders to show
        """
        st.subheader("📋 Recent Orders")
        
        if not orders:
            st.info("No open orders")
            return
        
        for order in orders[:limit]:
            side = order.get("side", "buy")
            side_emoji = "🟢" if side == "buy" else "🔴"
            price = order.get("price", 0)
            amount = order.get("amount", 0)
            status = "⏳" if order.get("status") == "open" else "✅"
            
            st.text(f"{status} {side_emoji} {side.upper()} {amount:.6f} @ ${price:,.2f}")
        
        if len(orders) > limit:
            st.caption(f"... and {len(orders) - limit} more orders")
    
    def render_grouped(self, orders: list[dict]):
        """Render orders grouped by side.
        
        Args:
            orders: List of order records
        """
        buy_orders = sorted(
            [o for o in orders if o.get("side") == "buy"],
            key=lambda x: x.get("price", 0),
            reverse=True
        )
        sell_orders = sorted(
            [o for o in orders if o.get("side") == "sell"],
            key=lambda x: x.get("price", 0)
        )
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 🟢 Buy Orders")
            if buy_orders:
                for order in buy_orders[:10]:
                    st.text(f"${order['price']:,.2f} | {order['amount']:.6f}")
            else:
                st.info("No buy orders")
        
        with col2:
            st.markdown("### 🔴 Sell Orders")
            if sell_orders:
                for order in sell_orders[:10]:
                    st.text(f"${order['price']:,.2f} | {order['amount']:.6f}")
            else:
                st.info("No sell orders")
