"""Streamlit dashboard for trading bot monitoring."""

import streamlit as st
import requests
from datetime import datetime
import time

from trading_bot.dashboard.components import GridVisualization, PnLChart, TradeTable

# Configuration
API_BASE_URL = "http://localhost:8000"


def fetch_api(endpoint: str, method: str = "GET", **kwargs):
    """Fetch data from API.
    
    Args:
        endpoint: API endpoint (e.g., "/api/status")
        method: HTTP method
        **kwargs: Additional request arguments
        
    Returns:
        JSON response or None on error
    """
    try:
        url = f"{API_BASE_URL}{endpoint}"
        if method == "GET":
            response = requests.get(url, timeout=5, **kwargs)
        elif method == "POST":
            response = requests.post(url, timeout=5, **kwargs)
        else:
            return None
        
        if response.ok:
            return response.json()
        return None
    except requests.exceptions.RequestException:
        return None


def main():
    """Main dashboard application."""
    st.set_page_config(
        page_title="Trading Bot Dashboard",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    
    # Custom CSS
    st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        color: #2196F3;
        text-align: center;
        margin-bottom: 1rem;
    }
    .status-running { color: #26A69A; }
    .status-paused { color: #FFA726; }
    .status-stopped { color: #EF5350; }
    .metric-card {
        background-color: #1E1E1E;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #2196F3;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Header
    st.markdown('<h1 class="main-header">🤖 Trading Bot Dashboard</h1>', unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Controls")
        
        # Refresh settings
        auto_refresh = st.checkbox("Auto Refresh", value=True)
        refresh_interval = st.slider("Refresh Interval (sec)", 5, 60, 10)
        
        if st.button("🔄 Refresh Now"):
            st.rerun()
        
        st.divider()
        
        # Bot controls
        st.subheader("🎮 Bot Control")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("⏸️ Pause", use_container_width=True):
                result = fetch_api("/api/bot/pause", method="POST")
                if result and result.get("success"):
                    st.success("Bot paused")
                else:
                    st.error(result.get("message", "Failed") if result else "API error")
        
        with col2:
            if st.button("▶️ Resume", use_container_width=True):
                result = fetch_api("/api/bot/resume", method="POST")
                if result and result.get("success"):
                    st.success("Bot resumed")
                else:
                    st.error(result.get("message", "Failed") if result else "API error")
        
        if st.button("🛑 Stop Bot", type="secondary", use_container_width=True):
            if st.button("⚠️ Confirm Stop"):
                result = fetch_api("/api/bot/stop", method="POST")
                if result and result.get("success"):
                    st.warning("Bot stopped")
                else:
                    st.error("Failed to stop")
        
        st.divider()
        
        # API status
        st.subheader("🔌 API Status")
        status = fetch_api("/api/status")
        if status:
            st.success("Connected")
            st.json({
                "state": status.get("state"),
                "symbol": status.get("symbol"),
                "ticks": status.get("ticks"),
            })
        else:
            st.error("Disconnected")
            st.info("Start the API server with:\n`uvicorn trading_bot.api.main:app`")
    
    # Main content
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Overview",
        "📈 Grid Trading",
        "💰 PnL Analysis",
        "📋 Trade History",
    ])
    
    # Initialize components
    grid_viz = GridVisualization()
    pnl_chart = PnLChart()
    trade_table = TradeTable()
    
    with tab1:
        _render_overview(status)
    
    with tab2:
        _render_grid_tab(grid_viz)
    
    with tab3:
        _render_pnl_tab(pnl_chart)
    
    with tab4:
        _render_trades_tab(trade_table)
    
    # Auto refresh
    if auto_refresh:
        time.sleep(refresh_interval)
        st.rerun()


def _render_overview(status: dict | None):
    """Render overview tab."""
    st.header("📊 Bot Overview")
    
    if not status:
        st.warning("⚠️ Unable to connect to trading bot API")
        st.info("""
        **To start the dashboard:**
        1. Run the FastAPI server: `uvicorn trading_bot.api.main:app --reload`
        2. Or use the dashboard script: `python scripts/run_dashboard.py`
        """)
        return
    
    # Status metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        state = status.get("state", "unknown")
        state_emoji = {"trading": "🟢", "waiting": "🟡", "paused": "⏸️"}.get(state, "❓")
        st.metric("Status", f"{state_emoji} {state.upper()}")
    
    with col2:
        st.metric("Symbol", status.get("symbol", "N/A"))
    
    with col3:
        price = status.get("current_price")
        st.metric("Current Price", f"${price:,.2f}" if price else "N/A")
    
    with col4:
        uptime = status.get("uptime_seconds")
        if uptime:
            hours = int(uptime // 3600)
            minutes = int((uptime % 3600) // 60)
            st.metric("Uptime", f"{hours}h {minutes}m")
        else:
            st.metric("Uptime", "N/A")
    
    st.divider()
    
    # Current position
    st.subheader("💼 Current Position")
    positions = fetch_api("/api/positions")
    
    if positions and positions.get("positions"):
        for pos in positions["positions"]:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                side = pos.get("side", "flat")
                side_emoji = "🟢" if side == "long" else "🔴" if side == "short" else "⚪"
                st.metric("Side", f"{side_emoji} {side.upper()}")
            with col2:
                st.metric("Amount", f"{pos.get('amount', 0):.6f}")
            with col3:
                st.metric("Entry Price", f"${pos.get('entry_price', 0):,.2f}")
            with col4:
                pnl = pos.get("unrealized_pnl", 0)
                st.metric("Unrealized PnL", f"${pnl:,.2f}", delta=f"{pnl:+,.2f}")
    else:
        st.info("No open positions")
    
    st.divider()
    
    # Quick stats
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📈 Quick Stats")
        st.metric("Ticks", status.get("ticks", 0))
        st.metric("Errors", status.get("errors", 0))
    
    with col2:
        st.subheader("⚙️ Configuration")
        config = fetch_api("/api/bot/config")
        if config:
            st.text(f"Grid Levels: {config.get('grid_levels', 'N/A')}")
            st.text(f"Grid Spacing: {config.get('grid_spacing_pct', 'N/A')}%")
            st.text(f"Amount/Level: {config.get('amount_per_level', 'N/A')}")
            st.text(f"AI Enabled: {'Yes' if config.get('ai_enabled') else 'No'}")


def _render_grid_tab(grid_viz: GridVisualization):
    """Render grid trading tab."""
    st.header("📈 Grid Trading")
    
    grid_data = fetch_api("/api/grid")
    status = fetch_api("/api/status")
    current_price = status.get("current_price") if status else None
    
    if grid_data:
        grid_viz.render(grid_data, current_price=current_price)
        
        st.divider()
        
        # Compact view
        st.subheader("📋 Grid Levels Detail")
        grid_viz.render_compact(grid_data, current_price=current_price)
    else:
        st.info("No grid data available. The bot may not be running.")


def _render_pnl_tab(pnl_chart: PnLChart):
    """Render PnL analysis tab."""
    st.header("💰 PnL Analysis")
    
    # PnL Summary
    pnl_summary = fetch_api("/api/trades/pnl")
    if pnl_summary:
        pnl_chart.render_summary(pnl_summary)
    
    st.divider()
    
    # PnL History
    pnl_history = fetch_api("/api/trades/history")
    if pnl_history and pnl_history.get("history"):
        col1, col2 = st.columns(2)
        with col1:
            pnl_chart.render_cumulative(pnl_history["history"])
        with col2:
            pnl_chart.render_daily(pnl_history["history"])
    else:
        st.info("No PnL history available yet. Start trading to see charts!")


def _render_trades_tab(trade_table: TradeTable):
    """Render trade history tab."""
    st.header("📋 Trade History")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        symbol_filter = st.selectbox("Symbol", ["All", "BTC/USDT", "ETH/USDT"])
    with col2:
        side_filter = st.selectbox("Side", ["All", "buy", "sell"])
    with col3:
        per_page = st.selectbox("Per Page", [10, 25, 50, 100], index=2)
    
    # Build query params
    params = {"per_page": per_page}
    if symbol_filter != "All":
        params["symbol"] = symbol_filter
    if side_filter != "All":
        params["side"] = side_filter
    
    # Fetch trades
    trades_data = fetch_api("/api/trades", params=params)
    
    if trades_data:
        trade_table.render_summary(trades_data.get("trades", []))
        st.divider()
        trade_table.render(
            trades_data.get("trades", []),
            page=trades_data.get("page", 1),
            total=trades_data.get("total", 0),
            per_page=trades_data.get("per_page", 50),
        )
    else:
        st.info("No trades recorded yet.")


if __name__ == "__main__":
    main()
