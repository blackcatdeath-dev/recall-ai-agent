from __future__ import annotations
import numpy as np

def max_drawdown(equity: list[float]) -> float:
    if not equity: return 0.0
    eq = np.array(equity, dtype=float)
    peaks = np.maximum.accumulate(eq)
    dd = (peaks - eq) / np.maximum(peaks, 1e-9)
    return float(np.max(dd)) if dd.size else 0.0

def sharpe_ratio(equity: list[float], bar_seconds: int) -> float:
    if len(equity) < 3: return 0.0
    eq = np.array(equity, dtype=float)
    rets = np.diff(np.log(eq + 1e-9))
    if rets.size < 2: return 0.0
    mu, sd = float(np.mean(rets)), float(np.std(rets))
    if sd == 0.0: return 0.0
    bars_per_year = (365*24*3600) / max(bar_seconds,1)
    return float((mu/sd) * np.sqrt(bars_per_year))
