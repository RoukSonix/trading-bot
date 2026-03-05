"""Grid visualization component."""

import streamlit as st
import plotly.graph_objects as go
from typing import Optional


class GridVisualization:
    """Component for visualizing grid trading levels."""
    
    def __init__(self):
        self.colors = {
            "buy": "#26A69A",      # Green
            "sell": "#EF5350",     # Red
            "current": "#2196F3", # Blue
            "filled": "#9E9E9E",  # Gray
        }
    
    def render(
        self,
        grid_data: dict,
        current_price: Optional[float] = None,
        title: str = "Grid Levels",
    ):
        """Render grid visualization.
        
        Args:
            grid_data: Grid data from API
            current_price: Current market price
            title: Chart title
        """
        st.subheader(f"📊 {title}")
        
        levels = grid_data.get("levels", [])
        center_price = grid_data.get("center_price")
        
        if not levels:
            st.info("No grid levels configured yet.")
            return
        
        # Create figure
        fig = go.Figure()
        
        # Separate buy and sell levels
        buy_levels = [l for l in levels if l["side"] == "buy"]
        sell_levels = [l for l in levels if l["side"] == "sell"]
        
        # Add buy levels (green bars)
        for i, level in enumerate(buy_levels):
            color = self.colors["filled"] if level["filled"] else self.colors["buy"]
            fig.add_trace(go.Bar(
                x=[f"Buy {i+1}"],
                y=[level["price"]],
                marker_color=color,
                name=f"Buy @ ${level['price']:,.2f}",
                text=f"${level['price']:,.2f}",
                textposition="outside",
                showlegend=False,
                hovertemplate=(
                    f"<b>Buy Level {i+1}</b><br>"
                    f"Price: ${level['price']:,.2f}<br>"
                    f"Amount: {level['amount']}<br>"
                    f"Status: {'Filled' if level['filled'] else 'Open'}<br>"
                    "<extra></extra>"
                ),
            ))
        
        # Add sell levels (red bars)
        for i, level in enumerate(sell_levels):
            color = self.colors["filled"] if level["filled"] else self.colors["sell"]
            fig.add_trace(go.Bar(
                x=[f"Sell {i+1}"],
                y=[level["price"]],
                marker_color=color,
                name=f"Sell @ ${level['price']:,.2f}",
                text=f"${level['price']:,.2f}",
                textposition="outside",
                showlegend=False,
                hovertemplate=(
                    f"<b>Sell Level {i+1}</b><br>"
                    f"Price: ${level['price']:,.2f}<br>"
                    f"Amount: {level['amount']}<br>"
                    f"Status: {'Filled' if level['filled'] else 'Open'}<br>"
                    "<extra></extra>"
                ),
            ))
        
        # Add current price line
        price = current_price or center_price
        if price:
            fig.add_hline(
                y=price,
                line_dash="dash",
                line_color=self.colors["current"],
                annotation_text=f"Current: ${price:,.2f}",
                annotation_position="right",
            )
        
        # Layout
        fig.update_layout(
            title="",
            xaxis_title="Grid Levels",
            yaxis_title="Price ($)",
            template="plotly_dark",
            height=400,
            margin=dict(l=50, r=50, t=30, b=50),
        )
        
        st.plotly_chart(fig, width="stretch")
        
        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Levels", len(levels))
        with col2:
            filled = sum(1 for l in levels if l["filled"])
            st.metric("Filled", filled)
        with col3:
            st.metric("Buy Levels", len(buy_levels))
        with col4:
            st.metric("Sell Levels", len(sell_levels))
    
    def render_compact(self, grid_data: dict, current_price: Optional[float] = None):
        """Render compact grid view as a table."""
        levels = grid_data.get("levels", [])
        
        if not levels:
            st.info("No grid levels.")
            return
        
        # Sort by price
        sorted_levels = sorted(levels, key=lambda x: x["price"], reverse=True)
        
        price = current_price or grid_data.get("center_price")
        
        for level in sorted_levels:
            is_current = False
            if price:
                is_current = abs(level["price"] - price) < price * 0.001
            
            status = "✅" if level["filled"] else "⏳"
            side_emoji = "🟢" if level["side"] == "buy" else "🔴"
            current_marker = "👈" if is_current else ""
            
            st.text(f"{status} {side_emoji} ${level['price']:,.2f} ({level['amount']}) {current_marker}")
