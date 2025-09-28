from __future__ import annotations
import numpy as np

class MomVolSignal:
    def __init__(self, look_s: int, look_l: int, vol_look: int, z_entry: float, z_exit: float):
        self.s = look_s; self.l = look_l; self.v = vol_look
        self.z_entry = z_entry; self.z_exit = z_exit

    def _z(self, arr: np.ndarray) -> float:
        if len(arr) < max(self.l, self.v):
            return 0.0
        m_s = float(np.mean(arr[-self.s:])); m_l = float(np.mean(arr[-self.l:]))
        spread = m_s - m_l
        vol = float(np.std(arr[-self.v:]))
        if vol == 0.0:
            return 0.0
        return spread / vol

    def decide_weight(self, arr: np.ndarray) -> float:
        z = self._z(arr)
        if z <= self.z_exit:
            return 0.0
        if z >= self.z_entry:
            return float(min(1.0, (z - self.z_entry) / max(self.z_entry, 1e-6) + 0.5))
        return float(max(0.0, (z - self.z_exit) / max(self.z_entry - self.z_exit, 1e-6) * 0.3))
