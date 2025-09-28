from __future__ import annotations
from dataclasses import dataclass
import time

@dataclass
class RiskParams:
    max_daily_trades: int
    cooldown_seconds: int
    max_gross_exposure_usd: float
    per_trade_usd: float
    max_drawdown_stop: float
    slippage_tolerance_pct: float

class RiskManager:
    def __init__(self, params: RiskParams):
        self.p = params
        self.daily_count = 0
        
        self.day_start = int(time.time()) // 86400
        self.last_trade_ts = 0.0
        self.equity_peak = None
        self.stopped = False

    def _reset_if_new_day(self):
        day_now = int(time.time()) // 86400
        if day_now != self.day_start:
            self.day_start = day_now
            self.daily_count = 0

    def mark_trade(self):
        self.daily_count += 1
        self.last_trade_ts = time.time()

    def check_pretrade(self, equity_usd: float, exposure_usd: float):
        if self.stopped:
            return False, "Drawdown stop (stopped)"
        self._reset_if_new_day()

        if self.equity_peak is None:
            self.equity_peak = equity_usd
        else:
            self.equity_peak = max(self.equity_peak, equity_usd)
            dd = 0.0 if self.equity_peak <= 0 else (self.equity_peak - equity_usd) / self.equity_peak
            if dd >= self.p.max_drawdown_stop:
                self.stopped = True
                return False, "Drawdown stop reached"

        if self.daily_count >= self.p.max_daily_trades:
            return False, "Daily trade cap"

        if time.time() - self.last_trade_ts < self.p.cooldown_seconds:
            return False, "Cooldown"

        if exposure_usd + self.p.per_trade_usd > self.p.max_gross_exposure_usd:
            return False, "Exposure limit"

        return True, "OK"
