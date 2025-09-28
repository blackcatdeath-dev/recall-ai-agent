from __future__ import annotations
from collections import deque
import numpy as np

class PriceSeries:
    def __init__(self, maxlen: int = 256):
        self.values = deque(maxlen=maxlen)
    def add(self, x: float):
        self.values.append(float(x))
    def ready(self, n: int) -> bool:
        return len(self.values) >= n
    def np(self):
        return np.array(self.values, dtype=float)

def realized_vol(prices: np.ndarray) -> float:
    if len(prices) < 3:
        return 0.0
    rets = np.diff(np.log(prices + 1e-9))
    sd = float(np.std(rets)) if rets.size else 0.0
    return max(sd, 1e-8)
