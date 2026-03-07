"""Streamlit dashboard for trading bot monitoring."""

import os
import streamlit as st
import requests
import time

from shared.dashboard.components import (
    GridVisualization,
    PnLChart,
    TradeTable,
    CandlestickChart,
    OrderBook,
)

# Configuration
API_BASE_URL = os.getenv("API_URL", "http://localhost:8000")


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
        elif method == "DELETE":
            response = requests.delete(url, timeout=5, **kwargs)
        else:
            return None
        
        if response.ok:
            return response.json()
        return None
    except requests.exceptions.RequestException:
        return None


def get_theme_css(dark_mode: bool) -> str:
    """Get CSS for theme."""
    if dark_mode:
        return """
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
        .price-up { color: #26A69A; font-weight: bold; }
        .price-down { color: #EF5350; font-weight: bold; }
        .price-ticker {
            font-size: 1.8rem;
            font-weight: bold;
            text-align: center;
            padding: 0.5rem;
            border-radius: 0.5rem;
            margin-bottom: 1rem;
        }
        </style>
        """
    else:
        return """
        <style>
        .main-header {
            font-size: 2.5rem;
            color: #1976D2;
            text-align: center;
            margin-bottom: 1rem;
        }
        .status-running { color: #00897B; }
        .status-paused { color: #F57C00; }
        .status-stopped { color: #E53935; }
        .metric-card {
            background-color: #F5F5F5;
            padding: 1rem;
            border-radius: 0.5rem;
            border-left: 4px solid #1976D2;
        }
        .price-up { color: #00897B; font-weight: bold; }
        .price-down { color: #E53935; font-weight: bold; }
        .price-ticker {
            font-size: 1.8rem;
            font-weight: bold;
            text-align: center;
            padding: 0.5rem;
            border-radius: 0.5rem;
            background-color: #FAFAFA;
            margin-bottom: 1rem;
        }
        </style>
        """


def render_price_ticker(status: dict | None):
    """Render live price ticker in header."""
    if not status:
        return
    
    current_price = status.get("current_price")
    if not current_price:
        # Try fetching from candles API
        price_data = fetch_api("/api/candles/current-price")
        if price_data:
            current_price = price_data.get("price")
    
    if not current_price:
        return
    
    # Store previous price for comparison
    prev_price = st.session_state.get("prev_price", current_price)
    st.session_state["prev_price"] = current_price
    
    # Determine price direction
    if current_price > prev_price:
        direction = "up"
        arrow = "▲"
        color_class = "price-up"
    elif current_price < prev_price:
        direction = "down"
        arrow = "▼"
        color_class = "price-down"
    else:
        direction = "flat"
        arrow = "●"
        color_class = ""
    
    symbol = status.get("symbol", "BTC/USDT")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(
            f'<div class="price-ticker">'
            f'<span class="{color_class}">{arrow}</span> '
            f'{symbol}: <span class="{color_class}">${current_price:,.2f}</span>'
            f'</div>',
            unsafe_allow_html=True
        )


def main():
    """Main dashboard application."""
    st.set_page_config(
        page_title="Trading Bot Dashboard",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    
    # Initialize session state
    if "dark_mode" not in st.session_state:
        st.session_state["dark_mode"] = True
    if "prev_price" not in st.session_state:
        st.session_state["prev_price"] = 0
    if "last_trade_count" not in st.session_state:
        st.session_state["last_trade_count"] = 0
    if "last_bot_state" not in st.session_state:
        st.session_state["last_bot_state"] = None
    
    # Apply theme CSS
    st.markdown(get_theme_css(st.session_state["dark_mode"]), unsafe_allow_html=True)
    
    # Header
    st.markdown('<h1 class="main-header">🤖 Trading Bot Dashboard</h1>', unsafe_allow_html=True)
    
    # Get status for header
    status = fetch_api("/api/status")
    
    # Live Price Ticker
    render_price_ticker(status)
    
    # Check for notifications
    _check_notifications(status)
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Controls")
        
        # Theme toggle
        st.subheader("🎨 Theme")
        if st.toggle("Dark Mode", value=st.session_state["dark_mode"], key="theme_toggle"):
            st.session_state["dark_mode"] = True
        else:
            st.session_state["dark_mode"] = False
        
        st.divider()
        
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
                    st.toast("✅ Bot paused", icon="⏸️")
                else:
                    st.toast("❌ Failed to pause", icon="⚠️")
        
        with col2:
            if st.button("▶️ Resume", use_container_width=True):
                result = fetch_api("/api/bot/resume", method="POST")
                if result and result.get("success"):
                    st.toast("✅ Bot resumed", icon="▶️")
                else:
                    st.toast("❌ Failed to resume", icon="⚠️")
        
        if st.button("🛑 Stop Bot", type="secondary", use_container_width=True):
            if st.button("⚠️ Confirm Stop"):
                result = fetch_api("/api/bot/stop", method="POST")
                if result and result.get("success"):
                    st.toast("⚠️ Bot stopped", icon="🛑")
                else:
                    st.toast("❌ Failed to stop", icon="⚠️")
        
        st.divider()
        
        # Force Trade Buttons
        st.subheader("⚡ Force Trade")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🟢 Force Buy", use_container_width=True, type="primary"):
                result = fetch_api("/api/orders/force-buy", method="POST")
                if result and result.get("success"):
                    price = result.get("price", 0)
                    st.toast(f"✅ Buy executed @ ${price:,.2f}", icon="🟢")
                else:
                    msg = result.get("message", "Failed") if result else "API error"
                    st.toast(f"❌ {msg}", icon="⚠️")
        
        with col2:
            if st.button("🔴 Force Sell", use_container_width=True, type="secondary"):
                result = fetch_api("/api/orders/force-sell", method="POST")
                if result and result.get("success"):
                    price = result.get("price", 0)
                    st.toast(f"✅ Sell executed @ ${price:,.2f}", icon="🔴")
                else:
                    msg = result.get("message", "Failed") if result else "API error"
                    st.toast(f"❌ {msg}", icon="⚠️")
        
        st.divider()
        
        # API status
        st.subheader("🔌 API Status")
        if status:
            st.success("Connected")
            st.json({
                "state": status.get("state"),
                "symbol": status.get("symbol"),
                "ticks": status.get("ticks"),
            })
        else:
            st.error("Disconnected")
            st.info("Start the API server with:\n`uvicorn shared.api.main:app`")
    
    # Main content
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "📊 Overview",
        "📈 Trading Chart",
        "🔲 Grid Trading",
        "💰 PnL Analysis",
        "📋 Trade History",
        "📑 Orders",
        "🧪 Backtest",
    ])
    
    # Initialize components
    grid_viz = GridVisualization()
    pnl_chart = PnLChart()
    trade_table = TradeTable()
    candle_chart = CandlestickChart()
    order_book = OrderBook()
    
    with tab1:
        _render_overview(status)
    
    with tab2:
        _render_chart_tab(candle_chart, status)
    
    with tab3:
        _render_grid_tab(grid_viz, status)
    
    with tab4:
        _render_pnl_tab(pnl_chart)
    
    with tab5:
        _render_trades_tab(trade_table)
    
    with tab6:
        _render_orders_tab(order_book)

    with tab7:
        _render_backtest_tab()

    # Auto refresh
    if auto_refresh:
        time.sleep(refresh_interval)
        st.rerun()


def _check_notifications(status: dict | None):
    """Check for changes and show toast notifications."""
    if not status:
        return
    
    # Check for state change
    current_state = status.get("state")
    if st.session_state["last_bot_state"] is not None:
        if current_state != st.session_state["last_bot_state"]:
            st.toast(f"🔔 Bot state changed: {current_state.upper()}", icon="🤖")
    st.session_state["last_bot_state"] = current_state
    
    # Check for new trades
    trades_data = fetch_api("/api/trades", params={"per_page": 1})
    if trades_data:
        current_count = trades_data.get("total", 0)
        if st.session_state["last_trade_count"] > 0:
            if current_count > st.session_state["last_trade_count"]:
                new_trades = current_count - st.session_state["last_trade_count"]
                st.toast(f"📈 {new_trades} new trade(s) executed!", icon="💰")
        st.session_state["last_trade_count"] = current_count
    
    # Check for errors
    errors = status.get("errors", 0)
    if errors > 0:
        prev_errors = st.session_state.get("last_errors", 0)
        if errors > prev_errors:
            st.toast(f"⚠️ {errors - prev_errors} new error(s)", icon="🚨")
        st.session_state["last_errors"] = errors


def _render_overview(status: dict | None):
    """Render overview tab."""
    st.header("📊 Bot Overview")
    
    if not status:
        st.warning("⚠️ Unable to connect to trading bot API")
        st.info("""
        **To start the dashboard:**
        1. Run the FastAPI server: `uvicorn shared.api.main:app --reload`
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


def _render_chart_tab(candle_chart: CandlestickChart, status: dict | None):
    """Render trading chart tab."""
    st.header("📈 Trading Chart")
    
    # Chart settings
    col1, col2, col3 = st.columns(3)
    with col1:
        timeframe = st.selectbox("Timeframe", ["1h", "15m", "4h", "1d"], index=0)
    with col2:
        limit = st.selectbox("Candles", [50, 100, 200], index=1)
    with col3:
        show_indicators = st.multiselect(
            "Indicators",
            ["MA", "RSI", "Volume"],
            default=["MA", "RSI", "Volume"]
        )
    
    # Fetch candle data
    candles_data = fetch_api("/api/candles", params={
        "timeframe": timeframe,
        "limit": limit,
    })
    
    # Fetch grid data for overlay
    grid_data = fetch_api("/api/grid")
    grid_levels = grid_data.get("levels", []) if grid_data else None
    
    current_price = status.get("current_price") if status else None
    
    if candles_data and candles_data.get("candles"):
        candle_chart.render(
            candles=candles_data["candles"],
            grid_levels=grid_levels,
            current_price=current_price,
            show_ma="MA" in show_indicators,
            show_rsi="RSI" in show_indicators,
            show_volume="Volume" in show_indicators,
            title=f"{candles_data.get('symbol', 'BTC/USDT')} - {timeframe}",
        )
    else:
        st.warning("Unable to fetch candle data. The API might be unavailable.")
        st.info("Make sure the trading bot API is running and accessible.")


def _render_grid_tab(grid_viz: GridVisualization, status: dict | None):
    """Render grid trading tab."""
    st.header("🔲 Grid Trading")
    
    grid_data = fetch_api("/api/grid")
    current_price = status.get("current_price") if status else None
    
    if grid_data:
        # Enhanced Grid Visualization
        _render_enhanced_grid(grid_data, current_price)
        
        st.divider()
        
        # Original visualization
        grid_viz.render(grid_data, current_price=current_price)
        
        st.divider()
        
        # Compact view
        st.subheader("📋 Grid Levels Detail")
        grid_viz.render_compact(grid_data, current_price=current_price)
    else:
        st.info("No grid data available. The bot may not be running.")


def _render_enhanced_grid(grid_data: dict, current_price: float | None):
    """Render enhanced horizontal grid visualization."""
    import plotly.graph_objects as go
    
    levels = grid_data.get("levels", [])
    if not levels:
        return
    
    st.subheader("📊 Grid Levels Diagram")
    
    # Sort levels by price
    sorted_levels = sorted(levels, key=lambda x: x["price"])
    
    # Create horizontal bar chart
    fig = go.Figure()
    
    prices = [l["price"] for l in sorted_levels]
    colors = []
    labels = []
    
    for level in sorted_levels:
        if level["filled"]:
            colors.append("#9E9E9E")  # Gray for filled
            labels.append(f"✅ {level['side'].upper()}")
        elif level["side"] == "buy":
            colors.append("#26A69A")  # Green for buy
            labels.append(f"🟢 BUY")
        else:
            colors.append("#EF5350")  # Red for sell
            labels.append(f"🔴 SELL")
    
    # Add bars
    fig.add_trace(go.Bar(
        y=[f"${p:,.0f}" for p in prices],
        x=[1] * len(prices),
        orientation='h',
        marker_color=colors,
        text=labels,
        textposition='inside',
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Status: %{text}<br>"
            "<extra></extra>"
        ),
    ))
    
    # Add current price line
    if current_price:
        fig.add_vline(
            x=0.5,
            line_dash="solid",
            line_color="#FFEB3B",
            line_width=3,
            annotation_text=f"Current: ${current_price:,.2f}",
        )
        # Find where current price would be
        for i, price in enumerate(prices):
            if price > current_price:
                fig.add_annotation(
                    x=1.1,
                    y=i - 0.5,
                    text=f"👈 Current: ${current_price:,.2f}",
                    showarrow=False,
                    font=dict(color="#FFEB3B", size=12),
                )
                break
    
    fig.update_layout(
        template="plotly_dark",
        height=max(300, len(levels) * 40),
        margin=dict(l=100, r=50, t=30, b=30),
        xaxis=dict(visible=False, range=[0, 1.5]),
        yaxis=dict(title="Price Levels"),
        showlegend=False,
    )
    
    st.plotly_chart(fig, use_container_width=True)


def _render_pnl_tab(pnl_chart: PnLChart):
    """Render PnL analysis tab."""
    st.header("💰 PnL Analysis")
    
    # PnL Summary
    pnl_summary = fetch_api("/api/trades/pnl")
    if pnl_summary:
        pnl_chart.render_summary(pnl_summary)
        
        # Win/Loss Pie Chart
        _render_win_loss_pie(pnl_summary)
    
    st.divider()
    
    # PnL History Charts
    pnl_history = fetch_api("/api/trades/history")
    if pnl_history and pnl_history.get("history"):
        col1, col2 = st.columns(2)
        with col1:
            pnl_chart.render_cumulative(pnl_history["history"])
        with col2:
            pnl_chart.render_daily(pnl_history["history"])
    else:
        st.info("No PnL history available yet. Start trading to see charts!")


def _render_win_loss_pie(pnl_summary: dict):
    """Render win/loss ratio pie chart."""
    import plotly.graph_objects as go
    
    st.subheader("📊 Win/Loss Ratio")
    
    wins = pnl_summary.get("winning_trades", 0)
    losses = pnl_summary.get("losing_trades", 0)
    
    if wins == 0 and losses == 0:
        st.info("No completed trades yet")
        return
    
    fig = go.Figure(data=[go.Pie(
        labels=["Wins", "Losses"],
        values=[wins, losses],
        hole=0.4,
        marker_colors=["#26A69A", "#EF5350"],
        textinfo="label+percent+value",
        hovertemplate="<b>%{label}</b><br>Count: %{value}<br>%{percent}<extra></extra>",
    )])
    
    fig.update_layout(
        template="plotly_dark",
        height=300,
        margin=dict(l=50, r=50, t=30, b=30),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.1, xanchor="center", x=0.5),
    )
    
    st.plotly_chart(fig, use_container_width=True)


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


def _render_orders_tab(order_book: OrderBook):
    """Render orders tab."""
    st.header("📑 Open Orders")
    
    # Fetch orders
    orders_data = fetch_api("/api/orders")
    
    if orders_data and orders_data.get("orders"):
        orders = orders_data["orders"]
        
        # Cancel handler
        def handle_cancel(order_id: str):
            result = fetch_api(f"/api/orders/{order_id}", method="DELETE")
            if result and result.get("success"):
                st.toast(f"✅ Order {order_id} cancelled", icon="❌")
                st.rerun()
            else:
                st.toast(f"❌ Failed to cancel order", icon="⚠️")
        
        # Check session state for cancel requests
        for key in list(st.session_state.keys()):
            if key.startswith("cancel_order_") and st.session_state[key]:
                order_id = key.replace("cancel_order_", "")
                handle_cancel(order_id)
                st.session_state[key] = False
        
        # Grouped view
        order_book.render_grouped(orders)
        
        st.divider()
        
        # Detailed view
        order_book.render(orders, on_cancel=handle_cancel)
    else:
        st.info("No open orders")


def _render_backtest_tab():
    """Render backtest tab with equity curve, metrics, and buy-and-hold comparison."""
    st.header("🧪 Backtest")

    # Import here to avoid circular imports / heavy deps at startup
    from tests.conftest import make_ohlcv_df
    from shared.backtest.engine import BacktestEngine, BacktestResult
    from shared.backtest.benchmark import StrategyBenchmark
    from shared.backtest.charts import BacktestCharts
    from binance_bot.strategies import GridStrategy, GridConfig

    # Controls
    col1, col2, col3 = st.columns(3)
    with col1:
        bt_symbol = st.text_input("Symbol", value="BTC/USDT", key="bt_symbol")
    with col2:
        bt_start = st.date_input("Start Date", value=pd.Timestamp("2025-01-01"), key="bt_start")
    with col3:
        bt_end = st.date_input("End Date", value=pd.Timestamp("2025-04-10"), key="bt_end")

    col4, col5, col6 = st.columns(3)
    with col4:
        bt_levels = st.slider("Grid Levels", 3, 30, 10, key="bt_levels")
    with col5:
        bt_spacing = st.slider("Grid Spacing %", 0.5, 5.0, 1.5, step=0.1, key="bt_spacing")
    with col6:
        bt_amount = st.number_input("Amount/Level", value=0.001, format="%.4f", key="bt_amount")

    if st.button("Run Backtest", type="primary", key="bt_run"):
        with st.spinner("Running backtest..."):
            # Generate synthetic data for demo (in production, fetch from exchange)
            n_candles = max(30, (pd.Timestamp(bt_end) - pd.Timestamp(bt_start)).days)
            data = make_ohlcv_df(n=n_candles, base_price=50000.0, trend=0.001, seed=42)

            config = GridConfig(
                grid_levels=bt_levels,
                grid_spacing_pct=bt_spacing,
                amount_per_level=bt_amount,
            )
            strategy = GridStrategy(symbol=bt_symbol, config=config)

            engine = BacktestEngine(
                symbol=bt_symbol,
                timeframe="1d",
                initial_balance=10000.0,
            )
            result = engine.run(strategy=strategy, data=data, params={"name": "Dashboard Run"})

            # Store result in session state
            st.session_state["bt_result"] = result
            st.session_state["bt_data"] = data

    # Display results if available
    result = st.session_state.get("bt_result")
    bt_data = st.session_state.get("bt_data")
    if result is None:
        st.info("Configure parameters and click 'Run Backtest' to start.")
        return

    # Metrics row
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Total Return", f"{result.total_return:+.2f}%")
    with m2:
        st.metric("Win Rate", f"{result.win_rate:.1f}%")
    with m3:
        st.metric("Sharpe Ratio", f"{result.sharpe_ratio:.2f}")
    with m4:
        st.metric("Max Drawdown", f"{result.max_drawdown:.2f}%")

    m5, m6, m7, m8 = st.columns(4)
    with m5:
        st.metric("Total Trades", result.total_trades)
    with m6:
        st.metric("Profit Factor", f"{result.profit_factor:.2f}")
    with m7:
        st.metric("Avg Win", f"${result.avg_win:,.2f}")
    with m8:
        st.metric("Avg Loss", f"${result.avg_loss:,.2f}")

    st.divider()

    # Charts
    charts = BacktestCharts()

    col_eq, col_dd = st.columns(2)
    with col_eq:
        st.plotly_chart(charts.equity_curve(result), use_container_width=True)
    with col_dd:
        st.plotly_chart(charts.drawdown_chart(result), use_container_width=True)

    st.plotly_chart(charts.monthly_returns_heatmap(result), use_container_width=True)
    st.plotly_chart(charts.trade_distribution(result), use_container_width=True)

    # Buy & Hold comparison
    st.divider()
    st.subheader("vs Buy & Hold")
    if bt_data is not None:
        bench = StrategyBenchmark()
        comp = bench.vs_buy_and_hold(result, bt_data)
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Strategy Return", f"{comp['strategy']['total_return']:+.2f}%")
        with c2:
            st.metric("Buy & Hold Return", f"{comp['buy_and_hold']['total_return']:+.2f}%")
        with c3:
            st.metric("Outperformance", f"{comp['outperformance']:+.2f}%")


if __name__ == "__main__":
    main()
