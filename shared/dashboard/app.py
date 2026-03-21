"""Grid trading dashboard — minimalist, data-dense, functional."""

import os
import statistics
import time
from datetime import datetime, timezone

import plotly.graph_objects as go
import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")


# ── API helper ───────────────────────────────────────────────────────────────


def _api(endpoint, method="GET", **kwargs):
    """Fetch from trading bot API. Returns JSON or None."""
    try:
        r = getattr(requests, method.lower())(
            f"{API_URL}{endpoint}", timeout=5, **kwargs
        )
        return r.json() if r.ok else None
    except requests.RequestException:
        return None


# ── Theme CSS ────────────────────────────────────────────────────────────────

CSS = """<style>
/* Hide Streamlit chrome */
#MainMenu, footer, .viewerBadge_container__r5tak { display: none; }
[data-testid="collapsedControl"] { display: none; }
[data-testid="stStatusWidget"] { display: none; }
header[data-testid="stHeader"] .stActionButton { display: none; }
button[kind="header"] { display: none; }

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    gap: 0; border-bottom: 1px solid #2d2d4a; background: transparent;
}
.stTabs [data-baseweb="tab"] {
    font-size: 0.72rem; font-weight: 500; letter-spacing: 0.1em;
    text-transform: uppercase; color: #606080; padding: 0.6rem 1.5rem;
    background: transparent;
}
.stTabs [aria-selected="true"] {
    color: #e2e2f0 !important; border-bottom: 2px solid #7b8cde !important;
    background: transparent !important;
}

/* Metrics */
[data-testid="stMetricValue"] {
    font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
}
[data-testid="stMetricLabel"] {
    font-size: 0.68rem !important; text-transform: uppercase;
    letter-spacing: 0.08em; color: #606080 !important;
}

/* Buttons */
.stButton > button {
    border-radius: 4px; font-size: 0.8rem; letter-spacing: 0.03em;
    border: 1px solid #2d2d4a;
}

/* ── Custom HTML elements ── */

.hdr {
    display: flex; align-items: baseline; gap: 1.5rem;
    padding: 0 0 0.75rem 0; border-bottom: 1px solid #2d2d4a;
    margin-bottom: 0.5rem;
}
.hdr-sym {
    font-size: 0.8rem; font-weight: 600; color: #8888a0;
    letter-spacing: 0.08em; text-transform: uppercase;
}
.hdr-price {
    font-size: 1.3rem; font-weight: 700; color: #e2e2f0;
    font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
}
.hdr-dot {
    width: 6px; height: 6px; border-radius: 50%; display: inline-block;
}
.hdr-status {
    font-size: 0.7rem; font-weight: 500; letter-spacing: 0.1em;
    text-transform: uppercase; display: inline-flex; align-items: center; gap: 0.4rem;
}

/* Balance */
.bal-label {
    font-size: 0.65rem; font-weight: 500; color: #505068;
    letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 0.15rem;
}
.bal-value {
    font-size: 2.2rem; font-weight: 700; line-height: 1.1;
    font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
}
.bal-pos { color: #22c55e; }
.bal-neg { color: #ef4444; }
.bal-zero { color: #6a6a85; }
.bal-sub {
    font-size: 0.78rem; font-weight: 500; margin-top: 0.15rem;
    font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
}

/* Section label */
.sect {
    font-size: 0.65rem; font-weight: 600; color: #505068;
    letter-spacing: 0.12em; text-transform: uppercase; padding: 1rem 0 0.4rem 0;
}

/* Position card */
.pos-card {
    background: #22223a; border: 1px solid #2d2d4a;
    border-radius: 6px; padding: 0.75rem 1rem; margin: 0.4rem 0;
    box-shadow: 0 1px 3px rgba(0,0,0,0.2);
}
.pos-hdr {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 0.3rem;
}
.pos-side {
    font-size: 0.65rem; font-weight: 600; letter-spacing: 0.1em;
    text-transform: uppercase; padding: 0.1rem 0.4rem; border-radius: 3px;
}
.pos-long { color: #22c55e; border: 1px solid #22c55e33; background: #22c55e0a; }
.pos-short { color: #ef4444; border: 1px solid #ef444433; background: #ef44440a; }
.pos-flat { color: #6a6a85; border: 1px solid #3a3a5533; }
.pos-pnl {
    font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
    font-weight: 600; font-size: 1rem;
}
.pos-details {
    display: flex; gap: 2rem; font-size: 0.78rem; color: #8888a0;
    font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
}

/* Activity log */
.log-entry {
    display: flex; gap: 0.8rem; padding: 0.35rem 0;
    border-bottom: 1px solid #262644; font-size: 0.78rem;
    font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
    align-items: baseline;
}
.log-time { color: #505068; white-space: nowrap; min-width: 5rem; }
.log-tag {
    font-weight: 600; font-size: 0.6rem; letter-spacing: 0.05em;
    padding: 0.08rem 0.3rem; min-width: 3.2rem; text-align: center;
    white-space: nowrap; border-radius: 3px;
}
.tag-trade { color: #22c55e; border: 1px solid #22c55e33; background: #22c55e0a; }
.tag-signal { color: #7b8cde; border: 1px solid #7b8cde33; background: #7b8cde0a; }
.tag-error { color: #ef4444; border: 1px solid #ef444433; background: #ef44440a; }
.tag-info { color: #6a6a85; border: 1px solid #6a6a8533; background: #6a6a850a; }
.tag-warn { color: #eab308; border: 1px solid #eab30833; background: #eab3080a; }
.log-msg { color: #9898b0; }

/* Grid ladder */
.grid-row {
    display: flex; align-items: center; padding: 0.3rem 0.8rem;
    border-bottom: 1px solid #262644;
    font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
    font-size: 0.78rem;
}
.grid-row:last-child { border-bottom: none; }
.grid-price { min-width: 7rem; font-weight: 500; color: #e2e2f0; }
.grid-side {
    min-width: 3rem; font-weight: 600; font-size: 0.65rem;
    letter-spacing: 0.05em; text-transform: uppercase;
}
.g-buy { color: #22c55e; }
.g-sell { color: #ef4444; }
.grid-status { min-width: 4rem; font-size: 0.65rem; color: #606080; }
.grid-filled { color: #8888a0; text-decoration: line-through; }
.grid-tpsl { font-size: 0.7rem; color: #606080; margin-left: auto; }
.grid-current {
    background: #2a2838; border: 1px solid #eab30833;
    border-radius: 4px; padding: 0.2rem 0.8rem; font-size: 0.72rem;
    color: #eab308; font-weight: 600;
    font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
}

/* Config groups */
.cfg-group {
    border: 1px solid #2d2d4a; border-radius: 6px;
    padding: 0.75rem 1rem; margin: 0.4rem 0;
    background: #22223a; box-shadow: 0 1px 3px rgba(0,0,0,0.2);
}
.cfg-row {
    display: flex; justify-content: space-between; padding: 0.25rem 0;
    font-size: 0.78rem; border-bottom: 1px solid #262644;
}
.cfg-row:last-child { border-bottom: none; }
.cfg-key { color: #606080; }
.cfg-val {
    color: #e2e2f0; font-weight: 500;
    font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
}

/* Muted placeholder text */
.muted { color: #505068; font-size: 0.8rem; padding: 2rem; text-align: center; }
</style>"""


# ── Plotly base layout ───────────────────────────────────────────────────────

_PLOTLY_BASE = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(26,26,46,0.4)",
    font=dict(family="ui-monospace, 'SF Mono', Menlo, Consolas, monospace", color="#8888a0"),
    showlegend=False,
)


# ── Main ─────────────────────────────────────────────────────────────────────


def main():
    st.set_page_config(
        page_title="GRID",
        page_icon=None,
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(CSS, unsafe_allow_html=True)

    for key, default in [("auto_refresh", True), ("refresh_sec", 10)]:
        if key not in st.session_state:
            st.session_state[key] = default

    status = _api("/api/status")
    _header(status)

    tabs = st.tabs(["OVERVIEW", "ACTIVITY", "GRID", "SETTINGS"])
    with tabs[0]:
        _tab_overview(status)
    with tabs[1]:
        _tab_activity(status)
    with tabs[2]:
        _tab_grid(status)
    with tabs[3]:
        _tab_settings(status)

    if st.session_state.auto_refresh:
        last_refresh = st.session_state.get("_last_refresh", 0)
        if time.time() - last_refresh >= st.session_state.refresh_sec:
            st.session_state._last_refresh = time.time()
            st.rerun()


# ── Header ───────────────────────────────────────────────────────────────────


def _header(status):
    if not status:
        st.markdown(
            '<div class="hdr">'
            '<span class="hdr-sym">---</span>'
            '<span class="hdr-status">'
            '<span class="hdr-dot" style="background:#6a6a85"></span>'
            '<span style="color:#6a6a85">OFFLINE</span>'
            "</span></div>",
            unsafe_allow_html=True,
        )
        return

    symbol = status.get("symbol", "---")
    price = status.get("current_price")
    state = status.get("state", "unknown")

    if not price:
        pd = _api("/api/candles/current-price")
        price = pd.get("price") if pd else None

    price_str = f"${price:,.2f}" if price else "---"
    colors = {"trading": "#22c55e", "waiting": "#eab308", "paused": "#eab308"}
    c = colors.get(state, "#6a6a85")

    st.markdown(
        f'<div class="hdr">'
        f'<span class="hdr-sym">{symbol}</span>'
        f'<span class="hdr-price">{price_str}</span>'
        f'<span class="hdr-status">'
        f'<span class="hdr-dot" style="background:{c}"></span>'
        f'<span style="color:{c}">{state.upper()}</span>'
        f"</span></div>",
        unsafe_allow_html=True,
    )


# ── Tab 1: Overview ─────────────────────────────────────────────────────────


def _tab_overview(status):
    if not status:
        st.warning("Cannot connect to API")
        st.code("uvicorn shared.api.main:app --host 0.0.0.0 --port 8000")
        return

    pnl_data = _api("/api/trades/pnl")
    positions = _api("/api/positions")
    pnl_history = _api("/api/trades/history")

    total_pnl = (pnl_data.get("total_pnl", 0) or 0) if pnl_data else 0
    win_rate = ((pnl_data.get("win_rate", 0) or 0) * 100) if pnl_data else 0
    unrealized = _sum_unrealized(positions)
    history = (pnl_history.get("history") or []) if pnl_history else []

    _overview_balance_section(total_pnl, unrealized, history)
    _overview_metrics_row(history, win_rate)

    st.markdown('<div class="sect">ACTIVE POSITION</div>', unsafe_allow_html=True)
    _render_position(positions)
    st.markdown('<div class="sect">STRATEGY</div>', unsafe_allow_html=True)
    _render_strategy(status)


def _sum_unrealized(positions):
    total = 0.0
    if positions and positions.get("positions"):
        for pos in positions["positions"]:
            total += pos.get("unrealized_pnl", 0) or 0
    return total


def _overview_balance_section(total_pnl, unrealized, history):
    initial_balance = float(os.getenv("PAPER_INITIAL_BALANCE", "10000.0"))
    account_balance = initial_balance + total_pnl + unrealized
    balance_change = account_balance - initial_balance
    balance_pct = (balance_change / initial_balance * 100) if initial_balance > 0 else 0

    col_bal, col_chart = st.columns([1, 2])

    with col_bal:
        st.markdown(
            f'<div style="padding:1rem 0">'
            f'<div class="bal-label">ACCOUNT BALANCE</div>'
            f'<div class="bal-value" style="font-size:2.5rem">${account_balance:,.2f}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )

        pnl_cls = "bal-pos" if balance_change > 0 else ("bal-neg" if balance_change < 0 else "bal-zero")
        pnl_sign = "+" if balance_change > 0 else ""
        st.markdown(
            f'<div class="bal-sub">'
            f'<span style="color:#555">P&L</span> '
            f'<span class="{pnl_cls}">{pnl_sign}${balance_change:,.2f} ({pnl_sign}{balance_pct:.2f}%)</span>'
            f"</div>",
            unsafe_allow_html=True,
        )

        if total_pnl != 0 or unrealized != 0:
            rc = "#22c55e" if total_pnl >= 0 else "#ef4444"
            uc = "#22c55e" if unrealized >= 0 else "#ef4444"
            st.markdown(
                f'<div class="bal-sub">'
                f'<span style="color:#606080">Realized</span> '
                f'<span style="color:{rc}">${total_pnl:+,.2f}</span>'
                f"&nbsp;&nbsp;"
                f'<span style="color:#606080">Unrealized</span> '
                f'<span style="color:{uc}">${unrealized:+,.2f}</span>'
                f"</div>",
                unsafe_allow_html=True,
            )

    with col_chart:
        if history:
            _equity_chart(history)
        else:
            st.markdown('<div class="muted">No trading history</div>', unsafe_allow_html=True)


def _overview_metrics_row(history, win_rate):
    profit_factor = _compute_profit_factor(history)
    sharpe = _compute_sharpe(history)
    max_dd = _compute_max_drawdown(history)

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Win Rate", f"{win_rate:.1f}%")
    with m2:
        pf = f"{profit_factor:.2f}" if profit_factor < 1e6 else "---"
        st.metric("Profit Factor", pf)
    with m3:
        st.metric("Sharpe Ratio", f"{sharpe:.2f}")
    with m4:
        st.metric("Max Drawdown", f"${max_dd:,.2f}")


def _compute_profit_factor(history):
    if not history:
        return 0.0
    gross_profit = sum(h.get("pnl", 0) for h in history if (h.get("pnl", 0) or 0) > 0)
    gross_loss = abs(sum(h.get("pnl", 0) for h in history if (h.get("pnl", 0) or 0) < 0))
    if gross_loss > 0:
        return gross_profit / gross_loss
    return gross_profit if gross_profit > 0 else 0.0


def _compute_sharpe(history):
    if not history or len(history) < 2:
        return 0.0
    pnls = [h.get("pnl", 0) or 0 for h in history]
    try:
        mean = statistics.mean(pnls)
        std = statistics.stdev(pnls)
        return mean / std if std > 0 else 0.0
    except statistics.StatisticsError:
        return 0.0


def _compute_max_drawdown(history):
    if not history:
        return 0.0
    peak = 0.0
    max_dd = 0.0
    for h in history:
        cum = h.get("cumulative_pnl", 0) or 0
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _equity_chart(history):
    timestamps = [h.get("timestamp", "") for h in history]
    values = [h.get("cumulative_pnl", 0) or 0 for h in history]

    if not values:
        return

    final = values[-1]
    line_color = "#22c55e" if final >= 0 else "#ef4444"
    fill_color = "rgba(34,197,94,0.08)" if final >= 0 else "rgba(239,68,68,0.08)"

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=values,
            mode="lines",
            line=dict(color=line_color, width=1.5),
            fill="tozeroy",
            fillcolor=fill_color,
            hovertemplate="$%{y:,.2f}<extra></extra>",
        )
    )
    fig.add_hline(y=0, line_dash="dot", line_color="#2d2d4a", line_width=0.5)
    fig.update_layout(
        **_PLOTLY_BASE,
        height=200,
        margin=dict(l=0, r=0, t=10, b=0),
        xaxis=dict(showgrid=False, tickfont=dict(size=9, color="#505068")),
        yaxis=dict(
            showgrid=True,
            gridcolor="#262644",
            tickfont=dict(size=9, color="#505068"),
            tickprefix="$",
            zeroline=False,
        ),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def _render_position(positions):
    if not positions or not positions.get("positions"):
        st.markdown(
            '<div style="color:#505068;font-size:0.8rem;padding:0.3rem 0">'
            "No active position</div>",
            unsafe_allow_html=True,
        )
        return

    for pos in positions["positions"]:
        side = pos.get("side", "flat")
        amount = pos.get("amount", 0) or 0
        entry = pos.get("entry_price", 0) or 0
        upnl = pos.get("unrealized_pnl", 0) or 0

        if amount == 0:
            st.markdown(
                '<div style="color:#505068;font-size:0.8rem;padding:0.3rem 0">'
                "No active position</div>",
                unsafe_allow_html=True,
            )
            continue

        side_cls = {"long": "pos-long", "short": "pos-short"}.get(side, "pos-flat")
        pnl_cls = "bal-pos" if upnl >= 0 else "bal-neg"

        st.markdown(
            f'<div class="pos-card">'
            f'<div class="pos-hdr">'
            f'<span class="pos-side {side_cls}">{side.upper()}</span>'
            f'<span class="pos-pnl {pnl_cls}">${upnl:+,.2f}</span>'
            f"</div>"
            f'<div class="pos-details">'
            f"<span>Size {amount:.6f}</span>"
            f"<span>Entry ${entry:,.2f}</span>"
            f"</div></div>",
            unsafe_allow_html=True,
        )


def _render_strategy(status):
    engine = status.get("strategy_engine") if status else None
    if not engine:
        engine = _api("/api/bot/strategy-engine")

    config = _api("/api/bot/config")

    if engine:
        name = engine.get("active_strategy", "---")
        regime = engine.get("current_regime", "---")
        confidence = engine.get("confidence", None)
        parts = [
            f'<span style="color:#e2e2f0;font-weight:500">{name}</span>',
            f"Regime: {regime}",
        ]
        if confidence is not None:
            parts.append(f"Confidence: {confidence:.0%}")
        st.markdown(
            '<div style="font-size:0.8rem;color:#8888a0;padding:0.3rem 0">'
            + "&nbsp;&nbsp;&middot;&nbsp;&nbsp;".join(parts)
            + "</div>",
            unsafe_allow_html=True,
        )
    elif config:
        ai = "AI Grid" if config.get("ai_enabled") else "Grid"
        levels = config.get("grid_levels", "?")
        spacing = config.get("grid_spacing_pct", "?")
        st.markdown(
            f'<div style="font-size:0.8rem;color:#8888a0;padding:0.3rem 0">'
            f'<span style="color:#e2e2f0;font-weight:500">{ai}</span>'
            f"&nbsp;&nbsp;&middot;&nbsp;&nbsp;{levels} levels"
            f"&nbsp;&nbsp;&middot;&nbsp;&nbsp;{spacing}% spacing"
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="color:#505068;font-size:0.8rem;padding:0.3rem 0">'
            "Not available</div>",
            unsafe_allow_html=True,
        )


# ── Tab 2: Activity Log ─────────────────────────────────────────────────────


def _tab_activity(status):
    filter_type = st.selectbox(
        "Filter", ["ALL", "TRADE", "INFO", "ERROR"], label_visibility="collapsed",
    )

    entries = _build_activity_entries(status)

    if filter_type != "ALL":
        entries = [e for e in entries if e["type"] == filter_type]

    entries.sort(
        key=lambda e: e["time"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    if not entries:
        st.markdown('<div class="muted">No activity</div>', unsafe_allow_html=True)
        return

    html = []
    for e in entries[:200]:
        time_str = e["time"].strftime("%H:%M:%S") if e["time"] else "---"
        tag = e["type"].lower()
        tag_cls = f"tag-{tag}" if tag in ("trade", "signal", "error", "info", "warn") else "tag-info"
        html.append(
            f'<div class="log-entry">'
            f'<span class="log-time">{time_str}</span>'
            f'<span class="log-tag {tag_cls}">{e["type"]}</span>'
            f'<span class="log-msg">{e["msg"]}</span>'
            f"</div>"
        )
    st.markdown("".join(html), unsafe_allow_html=True)


def _build_activity_entries(status):
    """Build activity log entries from trades and bot status."""
    entries = []

    trades = _api("/api/trades", params={"per_page": 100})
    if trades and trades.get("trades"):
        for t in trades["trades"]:
            ts_ms = t.get("timestamp", 0)
            ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc) if ts_ms else None
            side = t.get("side", "?")
            price = t.get("price", 0) or 0
            amount = t.get("amount", 0) or 0
            symbol = t.get("symbol", "")
            cost = t.get("cost", 0) or (price * amount)
            side_color = "#22c55e" if side == "buy" else "#ef4444"
            msg = (
                f'<span style="color:{side_color}">{side.upper()}</span> '
                f"{amount:.6f} {symbol} @ ${price:,.2f} = ${cost:,.2f}"
            )
            entries.append({"time": ts, "type": "TRADE", "msg": msg})

    if status:
        errors = status.get("errors", 0) or 0
        if errors > 0:
            entries.append({"time": datetime.now(timezone.utc), "type": "ERROR", "msg": f"{errors} error(s) recorded"})
        state = status.get("state", "unknown")
        uptime = status.get("uptime_seconds", 0) or 0
        h, m = int(uptime // 3600), int((uptime % 3600) // 60)
        ticks = status.get("ticks", 0)
        entries.append({"time": datetime.now(timezone.utc), "type": "INFO", "msg": f"State: {state.upper()} | Uptime: {h}h {m}m | Ticks: {ticks}"})

    return entries


# ── Tab 3: Grid View ────────────────────────────────────────────────────────


def _tab_grid(status):
    grid_data = _api("/api/grid")
    current_price = status.get("current_price") if status else None

    if not grid_data or not grid_data.get("levels"):
        st.markdown('<div class="muted">No grid data</div>', unsafe_allow_html=True)
        return

    levels = grid_data["levels"]

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Levels", len(levels))
    with c2:
        st.metric("Filled", sum(1 for lv in levels if lv.get("filled")))
    with c3:
        st.metric("Buy Orders", sum(1 for lv in levels if lv.get("side") == "buy" and not lv.get("filled")))
    with c4:
        st.metric("Sell Orders", sum(1 for lv in levels if lv.get("side") == "sell" and not lv.get("filled")))

    _grid_chart(levels, current_price)
    st.markdown('<div class="sect">LEVEL DETAIL</div>', unsafe_allow_html=True)
    st.markdown(_grid_level_ladder(levels, current_price), unsafe_allow_html=True)


def _grid_level_ladder(levels, current_price):
    """Build HTML for grid level detail ladder."""
    sorted_levels = sorted(levels, key=lambda x: x["price"], reverse=True)
    html = ['<div style="border:1px solid #2d2d4a;background:#1e1e34;border-radius:6px;overflow:hidden">']
    price_inserted = False

    for lv in sorted_levels:
        price = lv["price"]
        if current_price and not price_inserted and price < current_price:
            html.append(f'<div class="grid-current">&#9656; CURRENT ${current_price:,.2f}</div>')
            price_inserted = True

        side = lv.get("side", "?")
        is_filled = lv.get("filled", False)
        side_cls = "g-buy" if side == "buy" else "g-sell"
        filled_cls = "grid-filled" if is_filled else ""
        status_text = "FILLED" if is_filled else "ACTIVE"

        tpsl = ""
        tp = lv.get("take_profit")
        sl = lv.get("stop_loss")
        if tp:
            tpsl += f"TP ${tp:,.0f} "
        if sl:
            tpsl += f"SL ${sl:,.0f}"

        html.append(
            f'<div class="grid-row">'
            f'<span class="grid-price {filled_cls}">${price:,.2f}</span>'
            f'<span class="grid-side {side_cls}">{side}</span>'
            f'<span class="grid-status">{status_text}</span>'
            f'<span class="grid-tpsl">{tpsl}</span>'
            f"</div>"
        )

    if current_price and not price_inserted:
        html.append(f'<div class="grid-current">&#9656; CURRENT ${current_price:,.2f}</div>')

    html.append("</div>")
    return "".join(html)


def _grid_chart(levels, current_price):
    sorted_levels = sorted(levels, key=lambda x: x["price"])

    fig = go.Figure()

    # Invisible trace to establish axes
    all_prices = [lv["price"] for lv in sorted_levels]
    if current_price:
        all_prices.append(current_price)

    fig.add_trace(
        go.Scatter(
            x=[0.5] * len(all_prices),
            y=all_prices,
            mode="markers",
            marker=dict(size=0, opacity=0),
            showlegend=False,
            hoverinfo="skip",
        )
    )

    # Level lines
    for lv in sorted_levels:
        price = lv["price"]
        filled = lv.get("filled", False)
        side = lv.get("side", "buy")

        if filled:
            color, width, dash = "#3a3a55", 1, "dot"
        elif side == "buy":
            color, width, dash = "#22c55e", 1.5, "solid"
        else:
            color, width, dash = "#ef4444", 1.5, "solid"

        fig.add_shape(
            type="line",
            x0=0,
            x1=1,
            y0=price,
            y1=price,
            line=dict(color=color, width=width, dash=dash),
        )

    # Current price
    if current_price:
        fig.add_shape(
            type="line",
            x0=0,
            x1=1,
            y0=current_price,
            y1=current_price,
            line=dict(color="#eab308", width=2),
        )
        fig.add_annotation(
            x=1.05,
            y=current_price,
            text=f"${current_price:,.2f}",
            showarrow=False,
            font=dict(size=10, color="#eab308"),
        )

    y_min = min(all_prices) * 0.999
    y_max = max(all_prices) * 1.001

    fig.update_layout(
        **_PLOTLY_BASE,
        height=max(200, len(sorted_levels) * 25),
        margin=dict(l=0, r=80, t=10, b=10),
        xaxis=dict(visible=False, range=[0, 1.2]),
        yaxis=dict(
            range=[y_min, y_max],
            showgrid=False,
            tickprefix="$",
            tickfont=dict(size=9, color="#505068"),
        ),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ── Tab 4: Settings ─────────────────────────────────────────────────────────


def _tab_settings(status):
    _settings_bot_control(status)
    _settings_strategy_config()

    st.markdown('<div class="sect">DASHBOARD</div>', unsafe_allow_html=True)
    st.session_state.auto_refresh = st.checkbox("Auto-refresh", value=st.session_state.auto_refresh)
    st.session_state.refresh_sec = st.slider("Interval (sec)", 5, 60, st.session_state.refresh_sec)


def _settings_bot_control(status):
    """Render bot control section in settings tab."""
    st.markdown('<div class="sect">BOT CONTROL</div>', unsafe_allow_html=True)

    if status:
        state = status.get("state", "unknown")
        uptime = status.get("uptime_seconds", 0) or 0
        h, m = int(uptime // 3600), int((uptime % 3600) // 60)
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("State", state.upper())
        with c2:
            st.metric("Uptime", f"{h}h {m}m")
        with c3:
            st.metric("Errors", status.get("errors", 0))
    else:
        st.warning("API offline")

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("PAUSE", use_container_width=True):
            r = _api("/api/bot/pause", method="POST")
            st.toast("Bot paused" if r and r.get("success") else "Failed")
    with c2:
        if st.button("RESUME", use_container_width=True, type="primary"):
            r = _api("/api/bot/resume", method="POST")
            st.toast("Bot resumed" if r and r.get("success") else "Failed")
    with c3:
        if st.button("STOP", use_container_width=True):
            r = _api("/api/bot/stop", method="POST")
            st.toast("Bot stopped" if r and r.get("success") else "Failed")


def _settings_strategy_config():
    """Render strategy and risk config sections."""
    st.markdown('<div class="sect">STRATEGY</div>', unsafe_allow_html=True)
    config = _api("/api/bot/config")

    if config:
        rows = [
            ("Symbol", config.get("symbol", "---")),
            ("Grid Levels", config.get("grid_levels", "---")),
            ("Grid Spacing", f'{config.get("grid_spacing_pct", "---")}%'),
            ("Amount / Level", config.get("amount_per_level", "---")),
            ("AI Enabled", "Yes" if config.get("ai_enabled") else "No"),
        ]
        _render_cfg_group(rows)
    else:
        st.markdown('<div style="color:#505068;font-size:0.8rem">Not available</div>', unsafe_allow_html=True)

    st.markdown('<div class="sect">RISK PARAMETERS</div>', unsafe_allow_html=True)
    if config:
        _render_cfg_group([("Risk Tolerance", config.get("risk_tolerance", "---"))])


def _render_cfg_group(rows):
    """Render a config group card."""
    html = '<div class="cfg-group">'
    for k, v in rows:
        html += f'<div class="cfg-row"><span class="cfg-key">{k}</span><span class="cfg-val">{v}</span></div>'
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)




if __name__ == "__main__":
    main()
