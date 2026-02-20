"""Prompt templates for AI trading agent."""

SYSTEM_PROMPT = """You are a professional cryptocurrency trading analyst. Your role is to analyze market data and provide trading recommendations.

You are part of a Grid Trading bot system. Your analysis helps decide:
1. Whether market conditions are suitable for grid trading
2. Optimal grid parameters (price range, number of levels)
3. Risk assessment and position sizing

Be concise, data-driven, and always consider risk management. Never recommend risking more than the user can afford to lose.

Current trading mode: Grid Trading on Binance Testnet.
"""

MARKET_ANALYSIS_PROMPT = """Analyze the following market data for {symbol}:

## Price Data
- Current Price: ${current_price:.4f}
- 24h High: ${high_24h:.4f}
- 24h Low: ${low_24h:.4f}
- 24h Change: {change_24h:+.2f}%

## Technical Indicators
{indicators}

## Order Book Summary
- Best Bid: ${best_bid:.4f}
- Best Ask: ${best_ask:.4f}
- Spread: {spread:.4f}%

## Recent Price Action
{price_action}

---

Provide a brief analysis covering:
1. **Trend**: Current market trend (bullish/bearish/sideways)
2. **Volatility**: Is volatility suitable for grid trading?
3. **Support/Resistance**: Key levels to watch
4. **Recommendation**: Should we activate grid trading? If yes, suggest price range.
5. **Risk Level**: Low/Medium/High

Keep response under 200 words. Be direct.
"""

GRID_OPTIMIZATION_PROMPT = """Based on the market analysis, optimize grid parameters for {symbol}:

## Current Market State
- Price: ${current_price:.4f}
- ATR (14): ${atr:.4f}
- Bollinger Bands: ${bb_lower:.4f} - ${bb_upper:.4f}
- RSI (14): {rsi:.1f}

## Current Grid Settings
- Price Range: ${grid_lower:.4f} - ${grid_upper:.4f}
- Number of Levels: {num_levels}
- Investment per Level: ${investment_per_level:.2f}

## Constraints
- Max Investment: ${max_investment:.2f}
- Risk Tolerance: {risk_tolerance}

---

Provide optimized grid parameters:
1. **Recommended Price Range**: Lower and upper bounds
2. **Number of Levels**: How many grid levels (5-20)
3. **Level Spacing**: Percentage between levels
4. **Reasoning**: Brief explanation

Output in this format:
GRID_LOWER: <value>
GRID_UPPER: <value>
NUM_LEVELS: <value>
CONFIDENCE: <0-100>
REASONING: <one line>
"""

RISK_ASSESSMENT_PROMPT = """Assess trading risk for the following position:

## Position Details
- Symbol: {symbol}
- Side: {side}
- Entry Price: ${entry_price:.4f}
- Current Price: ${current_price:.4f}
- Position Size: {position_size} {base_currency}
- Position Value: ${position_value:.2f}
- Unrealized PnL: ${unrealized_pnl:.2f} ({pnl_percent:+.2f}%)

## Market Context
- 24h Volatility: {volatility:.2f}%
- RSI: {rsi:.1f}
- Trend: {trend}

## Portfolio
- Total Balance: ${total_balance:.2f}
- Position as % of Portfolio: {position_pct:.1f}%

---

Provide risk assessment:
1. **Risk Score**: 1-10 (1=low risk, 10=extreme risk)
2. **Action**: HOLD / REDUCE / CLOSE / ADD
3. **Stop Loss**: Recommended stop loss price
4. **Take Profit**: Recommended take profit price
5. **Warning**: Any immediate concerns?

Be conservative. Protecting capital is priority #1.
"""

SIGNAL_CONFIRMATION_PROMPT = """Confirm or reject this trading signal:

## Signal
- Type: {signal_type}
- Symbol: {symbol}
- Price: ${price:.4f}
- Grid Level: {grid_level}
- Reason: {reason}

## Market Context
{market_context}

## Recent Trades
{recent_trades}

---

Decision (respond with ONE word followed by brief reason):
- CONFIRM: Execute the signal
- REJECT: Do not execute
- WAIT: Wait for better entry

Format: <DECISION>: <reason in 10 words or less>
"""
