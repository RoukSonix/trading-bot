"""Candlestick chart component with technical indicators."""

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from typing import Optional


class CandlestickChart:
    """Component for candlestick charts with indicators."""
    
    def __init__(self):
        self.colors = {
            "up": "#26A69A",       # Green
            "down": "#EF5350",     # Red
            "ma20": "#FFA726",     # Orange
            "ma50": "#42A5F5",     # Blue
            "grid_buy": "rgba(38, 166, 154, 0.3)",
            "grid_sell": "rgba(239, 83, 80, 0.3)",
            "current_price": "#FFEB3B",  # Yellow
        }
    
    def render(
        self,
        candles: list[dict],
        grid_levels: Optional[list[dict]] = None,
        current_price: Optional[float] = None,
        show_ma: bool = True,
        show_rsi: bool = True,
        show_volume: bool = True,
        title: str = "BTC/USDT",
    ):
        """Render candlestick chart with indicators.
        
        Args:
            candles: List of OHLCV candle data
            grid_levels: Optional grid levels to show as horizontal lines
            current_price: Current price line
            show_ma: Show moving averages
            show_rsi: Show RSI subplot
            show_volume: Show volume bars
            title: Chart title
        """
        if not candles:
            st.info("No candle data available. Waiting for market data...")
            return
        
        # Convert to DataFrame
        df = pd.DataFrame(candles)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.sort_values('timestamp')
        
        # Calculate indicators
        if show_ma:
            df['MA20'] = df['close'].rolling(window=20).mean()
            df['MA50'] = df['close'].rolling(window=50).mean()
        
        if show_rsi:
            df['RSI'] = self._calculate_rsi(df['close'], period=14)
        
        # Create subplots
        row_heights = [0.6]
        rows = 1
        
        if show_rsi:
            row_heights.append(0.2)
            rows += 1
        
        if show_volume:
            row_heights.append(0.2)
            rows += 1
        
        fig = make_subplots(
            rows=rows,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=row_heights,
        )
        
        # Candlestick chart
        fig.add_trace(
            go.Candlestick(
                x=df['timestamp'],
                open=df['open'],
                high=df['high'],
                low=df['low'],
                close=df['close'],
                name='OHLC',
                increasing_line_color=self.colors['up'],
                decreasing_line_color=self.colors['down'],
            ),
            row=1, col=1
        )
        
        # Moving averages
        if show_ma and 'MA20' in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df['timestamp'],
                    y=df['MA20'],
                    mode='lines',
                    name='MA20',
                    line=dict(color=self.colors['ma20'], width=1),
                ),
                row=1, col=1
            )
            fig.add_trace(
                go.Scatter(
                    x=df['timestamp'],
                    y=df['MA50'],
                    mode='lines',
                    name='MA50',
                    line=dict(color=self.colors['ma50'], width=1),
                ),
                row=1, col=1
            )
        
        # Grid levels as horizontal lines
        if grid_levels:
            for level in grid_levels:
                color = self.colors['grid_buy'] if level['side'] == 'buy' else self.colors['grid_sell']
                line_style = 'dot' if level.get('filled') else 'dash'
                fig.add_hline(
                    y=level['price'],
                    line_dash=line_style,
                    line_color=color,
                    annotation_text=f"{level['side'].upper()} ${level['price']:,.0f}",
                    annotation_position="right",
                    row=1, col=1
                )
        
        # Current price line
        if current_price:
            fig.add_hline(
                y=current_price,
                line_dash='solid',
                line_color=self.colors['current_price'],
                line_width=2,
                annotation_text=f"Current: ${current_price:,.2f}",
                annotation_position="left",
                row=1, col=1
            )
        
        # RSI subplot
        current_row = 2
        if show_rsi and 'RSI' in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df['timestamp'],
                    y=df['RSI'],
                    mode='lines',
                    name='RSI',
                    line=dict(color='#9C27B0', width=1),
                ),
                row=current_row, col=1
            )
            # RSI levels
            fig.add_hline(y=70, line_dash='dash', line_color='rgba(239, 83, 80, 0.5)', row=current_row, col=1)
            fig.add_hline(y=30, line_dash='dash', line_color='rgba(38, 166, 154, 0.5)', row=current_row, col=1)
            fig.update_yaxes(title_text="RSI", range=[0, 100], row=current_row, col=1)
            current_row += 1
        
        # Volume subplot
        if show_volume:
            colors = ['#26A69A' if row['close'] >= row['open'] else '#EF5350' 
                     for _, row in df.iterrows()]
            fig.add_trace(
                go.Bar(
                    x=df['timestamp'],
                    y=df['volume'],
                    name='Volume',
                    marker_color=colors,
                ),
                row=current_row, col=1
            )
            fig.update_yaxes(title_text="Volume", row=current_row, col=1)
        
        # Layout
        fig.update_layout(
            title=f"📈 {title}",
            template='plotly_dark',
            height=600 if show_rsi or show_volume else 450,
            margin=dict(l=50, r=50, t=50, b=50),
            xaxis_rangeslider_visible=False,
            showlegend=True,
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.02,
                xanchor='right',
                x=1
            ),
        )
        
        fig.update_yaxes(title_text="Price ($)", row=1, col=1)
        
        st.plotly_chart(fig, use_container_width=True)
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI indicator."""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def render_mini(
        self,
        candles: list[dict],
        current_price: Optional[float] = None,
        height: int = 200,
    ):
        """Render mini price chart for header."""
        if not candles:
            return
        
        df = pd.DataFrame(candles[-24:])  # Last 24 candles
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        fig = go.Figure()
        
        # Area chart
        fig.add_trace(go.Scatter(
            x=df['timestamp'],
            y=df['close'],
            mode='lines',
            fill='tozeroy',
            fillcolor='rgba(33, 150, 243, 0.1)',
            line=dict(color='#2196F3', width=2),
        ))
        
        fig.update_layout(
            template='plotly_dark',
            height=height,
            margin=dict(l=0, r=0, t=0, b=0),
            showlegend=False,
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
        )
        
        st.plotly_chart(fig, use_container_width=True)
