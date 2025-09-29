from __future__ import annotations
from dataclasses import dataclass
import time

@dataclass
class RiskParams:
    min_daily_trades: int
    max_daily_trades: int
    cooldown_seconds: int
    max_single_trade_pct: float
    per_trade_base_usd: float
    max_drawdown_stop: float
    slippage_tolerance_pct: float
    max_exposure_per_asset_pct: float

class RiskManager:
    def __init__(self, params: RiskParams):
        self.p = params
        self.daily_count = 0
        self.day_start = int(time.time()) // 86400
        self.last_trade_ts = 0.0
        self.equity_peak = None
        self.stopped = False
        self.daily_trade_times = [] 

    def _reset_if_new_day(self):
        day_now = int(time.time()) // 86400
        if day_now != self.day_start:
            if self.daily_count < self.p.min_daily_trades and self.daily_count > 0:
                from ..logger import setup_logger
                LOG = setup_logger()
                LOG.warning(f"Previous day had only {self.daily_count} trades, min is {self.p.min_daily_trades}")
            
            self.day_start = day_now
            self.daily_count = 0
            self.daily_trade_times = []

    def mark_trade(self):
        """Record a trade execution"""
        self.daily_count += 1
        self.last_trade_ts = time.time()
        self.daily_trade_times.append(self.last_trade_ts)

    def get_daily_trade_count(self) -> int:
        """Get current day's trade count"""
        self._reset_if_new_day()
        return self.daily_count
    
    def needs_more_trades(self) -> bool:
        """Check if we need more trades to meet daily minimum"""
        self._reset_if_new_day()
        return self.daily_count < self.p.min_daily_trades

    def check_trade_size(self, trade_usd: float, total_portfolio_usd: float) -> tuple[bool, str]:
        """Validate trade size against portfolio constraints"""
        if total_portfolio_usd <= 0:
            return False, "Zero portfolio value"
        
        trade_pct = trade_usd / total_portfolio_usd
        if trade_pct > self.p.max_single_trade_pct:
            return False, f"Trade {trade_pct:.1%} > max {self.p.max_single_trade_pct:.1%}"
        
        return True, "OK"
    
    def check_asset_exposure(self, asset_exposure_usd: float, 
                            total_portfolio_usd: float) -> tuple[bool, str]:
        """Check if asset exposure is within limits"""
        if total_portfolio_usd <= 0:
            return True, "OK"
        
        exposure_pct = asset_exposure_usd / total_portfolio_usd
        if exposure_pct > self.p.max_exposure_per_asset_pct:
            return False, f"Asset exposure {exposure_pct:.1%} > max {self.p.max_exposure_per_asset_pct:.1%}"
        
        return True, "OK"

    def check_pretrade(self, equity_usd: float, current_exposure_usd: float = 0) -> tuple[bool, str]:
        """Pre-trade risk checks"""
        if self.stopped:
            return False, "Drawdown stop active"
        
        self._reset_if_new_day()

        if self.equity_peak is None:
            self.equity_peak = equity_usd
        else:
            self.equity_peak = max(self.equity_peak, equity_usd)
            dd = 0.0 if self.equity_peak <= 0 else (self.equity_peak - equity_usd) / self.equity_peak
            if dd >= self.p.max_drawdown_stop:
                self.stopped = True
                return False, f"Drawdown {dd:.1%} >= stop {self.p.max_drawdown_stop:.1%}"

        if self.daily_count >= self.p.max_daily_trades:
            return False, f"Daily cap {self.p.max_daily_trades} reached"

        if time.time() - self.last_trade_ts < self.p.cooldown_seconds:
            return False, f"Cooldown {self.p.cooldown_seconds}s"

        return True, "OK"
