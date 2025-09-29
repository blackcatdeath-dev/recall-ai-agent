# blackcatdeath — Multi Chain Recall Trading Agent

Autonomous multi chain trading agent for Recall Competition with full compliance to competition rules.

## 🎯 Competition Compliance

### Starting Balance
- **Ethereum**: 5000 USDC
- **Polygon**: 5000 USDC  
- **Base**: 5000 USDC
- **Arbitrum**: 5000 USDC
- **Optimism**: 5000 USDC
- **Solana**: 5000 USDC
- **BSC**: 5000 USDC
- **Avalanche**: 5000 USDC
- **Total**: 40,000 USDC across 8 chains

### Token Eligibility
- ✅ Min token age: **4380 hours** (~6 months)
- ✅ Min 24h volume: **$500,000**
- ✅ Min liquidity: **$500,000**
- ✅ Min FDV: **$1,000,000**

### Trading Rules
- ✅ Min daily trades: **3 trades**
- ✅ Max single trade: **25% of portfolio**
- ✅ No shorting (long-only)
- ✅ Slippage applied
- ✅ Cross-chain trading: allowed

### Rate Limits
- 100 req/min for trade operations
- 300 req/min for price queries
- 30 req/min for balance checks
- 3,000 req/min global
- 10,000 req/hour per agent

## 🚀 Features

### Strategy
- **Momentum + Volatility Signal**: Z-score based entry/exit
- **Risk-Parity Allocation**: Volatility-weighted positions
- **Multi-Chain Discovery**: Automatic token discovery across all chains
- **Adaptive Sizing**: Portfolio-percentage based position sizing

### Risk Management
- Max 25% portfolio per trade (competition rule)
- Max 35% exposure per asset
- Daily trade count enforcement (min 3/day)
- Max drawdown stop (18%)
- Per-asset exposure limits
- Trade cooldown periods

### Execution
- Rate-limited API client
- Retry logic with exponential backoff
- Slippage protection
- Cross-chain swap support
- Connection pooling

### Telemetry
- Real-time equity tracking
- Sharpe ratio calculation
- Max drawdown monitoring
- CSV logging (timestamp, equity, Sharpe, MDD, trades)

## 📦 Installation

```bash
# Create virtual environment
python -m venv .venv

# Activate (Windows)
.\.venv\Scripts\Activate.ps1

# Activate (macOS/Linux)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.example .env
# Edit .env: add your RECALL_API_KEY
```

## ⚙️ Configuration

Edit `config/config.yaml`:

```yaml
# Strategy parameters
strategy:
  bar_seconds: 45          # Poll interval
  lookback_short: 20       # Short MA period
  lookback_long: 100       # Long MA period
  z_entry: 1.2            # Z-score entry threshold
  z_exit: 0.3             # Z-score exit threshold
  min_momentum: 0.005     # Min 0.5% momentum

# Risk controls
risk:
  min_daily_trades: 3              # Competition minimum
  max_single_trade_pct: 0.25       # 25% max per trade
  per_trade_base_usd: 100          # Base trade size
  max_exposure_per_asset_pct: 0.35 # 35% max per asset
  max_drawdown_stop: 0.18          # 18% stop
```

## 🎮 Usage

```bash
# Production mode (default)
python -m src.main

# The agent will:
# 1. Discover eligible tokens across all 8 chains
# 2. Monitor prices and calculate signals
# 3. Execute trades based on momentum + volatility
# 4. Ensure minimum 3 trades per day
# 5. Log telemetry to CSV
```

## 📊 Monitoring

The agent logs to:
- **Console**: Real-time trade execution and signals
- **CSV**: `telemetry_equity.csv` with equity curve

Example log output:
```
2025-09-29 10:15:23 | INFO | Discovering tokens on evm/eth...
2025-09-29 10:15:25 | INFO | Token filter: 12/50 eligible
2025-09-29 10:15:30 | INFO | Signals: 5 tokens with positive signal
2025-09-29 10:15:31 | INFO | BUY WETH_eth: $100.00 (target=15.2%)
2025-09-29 10:20:45 | INFO | 📊 Equity=$41,250.00 | Sharpe=1.85 | MDD=2.3% | Trades=5
```

## 🔧 Architecture

```
src/
├── main.py              # Main trading loop
├── recall_client.py     # API client with rate limiting
├── rate_limiter.py      # Token bucket rate limiter
├── token_filter.py      # Token eligibility checker
├── data.py             # Price series management
├── signals/
│   └── momentum_vol.py  # Signal generator
├── risk/
│   └── manager.py       # Risk management
├── portfolio/
│   └── allocator.py     # Risk-parity allocation
├── execution/
│   └── executor.py      # Trade execution
├── metrics.py           # Performance metrics
└── utils.py            # Config & utilities
```

## 🎯 Strategy Logic

1. **Token Discovery**: Find eligible tokens across all chains
2. **Signal Generation**: Calculate momentum + volatility z-score
3. **Risk-Parity Weighting**: Allocate based on inverse volatility
4. **Position Entry**: Buy when z > z_entry threshold
5. **Position Exit**: Sell when z < z_exit or momentum < min
6. **Rebalancing**: Every 180s, adjust positions to target weights
7. **Daily Trade Enforcement**: Ensures min 3 trades/day

## 📈 Performance Tracking

Metrics calculated:
- **Equity curve**: Mark-to-market across all chains
- **Sharpe ratio**: Annualized risk-adjusted returns
- **Max drawdown**: Peak-to-trough decline
- **Daily trades**: Counts for compliance

## ⚠️ Important Notes

1. **Rate Limits**: Built-in rate limiter respects API limits
2. **Token Filtering**: Only trades tokens meeting competition criteria
3. **Trade Minimums**: Enforces 3 trades/day requirement
4. **Position Limits**: Max 25% per trade, 35% per asset
5. **Multi-Chain**: Manages balances across 8 chains independently

## 🐛 Troubleshooting

**"No eligible tokens found"**
- Check API connectivity
- Verify token filter thresholds in config
- Check chain availability

**"Rate limit wait timeout"**
- Increase `max_wait` in rate_limiter.py
- Reduce polling frequency (`bar_seconds`)

**"Drawdown stop active"**
- Agent stopped trading due to 18% drawdown
- Restart after reviewing strategy parameters

## 📝 License

MIT License - See LICENSE file

## 🏆 Competition

This agent is designed for the Recall AI Trading Competition with full rule compliance.
