# Optimization Results — jesse-bot

## Winner: ETH-USDT 1h — Trial 2861

Selected as the production configuration after extensive Optuna hyperparameter optimization.

### Backtest Performance

| Metric | Value |
|--------|-------|
| Period | Jan 2024 – Apr 2025 (15 months) |
| Leverage | 5x |
| Return | +4.19% |
| Sharpe Ratio | 1.45 |
| Sortino Ratio | 2.77 |
| Win Rate | 55.56% |
| Max Drawdown | -2.05% |
| Total Trades | 36 |

### Optimized Hyperparameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `grid_levels_count` | 4 | Number of grid levels per side |
| `grid_spacing_pct` | 3.697 | Spacing between grid levels (%) |
| `amount_pct` | 9.988 | Position size per level (% of capital) |
| `atr_period` | 25 | ATR lookback period |
| `tp_atr_mult` | 3.465 | Take-profit as ATR multiple |
| `sl_atr_mult` | 2.744 | Stop-loss as ATR multiple |
| `trailing_activation_pct` | 3.904 | Trailing stop activation threshold (%) |
| `trailing_distance_pct` | 0.765 | Trailing stop distance (%) |
| `trend_sma_fast` | 28 | Fast SMA period for trend detection |
| `trend_sma_slow` | 63 | Slow SMA period for trend detection |
| `max_total_levels` | 21 | Maximum total open grid levels |

### Key Observations

- **Conservative grid**: Only 4 levels per side with wide 3.7% spacing suits ETH's volatility on 1h timeframe.
- **Tight trailing stop**: 0.765% distance locks in profits effectively once the 3.9% activation threshold is reached.
- **Asymmetric risk/reward**: TP multiplier (3.465) exceeds SL multiplier (2.744), giving a favorable R:R ratio of ~1.26:1.
- **Low drawdown**: -2.05% max drawdown with 5x leverage indicates robust risk management.
- **Sortino >> Sharpe**: Ratio of 2.77 vs 1.45 confirms the strategy limits downside deviation effectively.
