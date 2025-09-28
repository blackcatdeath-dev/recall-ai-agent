# blackcatdeath — Recall Trading Agent (Production)

Autonomous trading agent Recall Competition.

## Fitur
- Momentum + Volatility (z-score) signal
- Risk-Parity allocation (vol targeting)
- Risk guard: max exposure, cooldown, daily cap, drawdown stop
- Exposure hanya menghitung aset yang dikelola (universe), non-tracked diabaikan dari limit
- Slippage guard saat eksekusi
- Retry & health-check robust
- Telemetry CSV (equity, Sharpe, MDD)

## Quickstart
```bash
python -m venv .venv
# Windows
.\.venv\Scripts\Activate.ps1
# macOS/Linux
# source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
# Edit .env: RECALL_API_KEY & RECALL_ENV (production / sandbox)

python -m src.main
