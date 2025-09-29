from __future__ import annotations
import time
from collections import deque
from threading import Lock

class RateLimiter:
    """Token bucket rate limiter with per-endpoint tracking"""
    
    def __init__(self, limits: dict):
        self.limits = limits
        self.windows = {
            'trade': deque(maxlen=limits.get('trade_operations', 100)),
            'price': deque(maxlen=limits.get('price_queries', 300)),
            'balance': deque(maxlen=limits.get('balance_checks', 30)),
            'global_rpm': deque(maxlen=limits.get('global_rpm', 3000)),
            'global_rph': deque(maxlen=limits.get('global_rph', 10000)),
        }
        self.lock = Lock()
    
    def _clean_window(self, window: deque, duration: float):
        """Remove timestamps older than duration"""
        now = time.time()
        while window and window[0] < now - duration:
            window.popleft()
    
    def acquire(self, endpoint: str = 'global') -> tuple[bool, float]:
        """
        Try to acquire rate limit token.
        Returns (success, wait_time_seconds)
        """
        with self.lock:
            now = time.time()
            
            if 'trade' in endpoint:
                window = self.windows['trade']
                limit = self.limits.get('trade_operations', 100)
                duration = 60
            elif 'price' in endpoint:
                window = self.windows['price']
                limit = self.limits.get('price_queries', 300)
                duration = 60
            elif 'balance' in endpoint or 'portfolio' in endpoint:
                window = self.windows['balance']
                limit = self.limits.get('balance_checks', 30)
                duration = 60
            else:
                window = self.windows['global_rpm']
                limit = self.limits.get('global_rpm', 3000)
                duration = 60

            self._clean_window(window, duration)

            global_rpm = self.windows['global_rpm']
            self._clean_window(global_rpm, 60)
            if len(global_rpm) >= self.limits.get('global_rpm', 3000):
                wait = 60 - (now - global_rpm[0]) + 0.1
                return False, max(0, wait)

            global_rph = self.windows['global_rph']
            self._clean_window(global_rph, 3600)
            if len(global_rph) >= self.limits.get('global_rph', 10000):
                wait = 3600 - (now - global_rph[0]) + 1
                return False, max(0, wait)

            if len(window) >= limit:
                wait = duration - (now - window[0]) + 0.1
                return False, max(0, wait)

            window.append(now)
            global_rpm.append(now)
            global_rph.append(now)
            
            return True, 0.0
    
    def wait_and_acquire(self, endpoint: str = 'global', max_wait: float = 30):
        """Block until rate limit allows request"""
        while True:
            ok, wait = self.acquire(endpoint)
            if ok:
                return True
            if wait > max_wait:
                return False
            time.sleep(min(wait, max_wait))
