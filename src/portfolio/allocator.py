from __future__ import annotations

def risk_parity_weights(vols: dict[str, float], long_only: bool = True) -> dict[str, float]:
    inv = {k: 1.0 / max(float(v), 1e-8) for k, v in vols.items()}
    s = sum(inv.values()) or 1.0
    w = {k: (v / s) for k, v in inv.items()}
    if long_only:
        w = {k: max(0.0, v) for k, v in w.items()}
    return w
