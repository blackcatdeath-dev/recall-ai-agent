from __future__ import annotations
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from .logger import setup_logger
from .rate_limiter import RateLimiter

LOG = setup_logger()

class RecallClient:
    def __init__(self, base_url: str, api_key: str, rate_limiter: RateLimiter | None = None):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.limiter = rate_limiter
        
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=20, 
            pool_maxsize=20,
            max_retries=3
        )
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.headers = {
            "Authorization": f"Bearer {api_key}", 
            "Content-Type": "application/json"
        }
    
    def _rate_limit_wait(self, endpoint: str):
        """Wait for rate limit if limiter is configured"""
        if self.limiter:
            if not self.limiter.wait_and_acquire(endpoint, max_wait=30):
                LOG.warning(f"Rate limit wait timeout for {endpoint}")

    @retry(
        stop=stop_after_attempt(5), 
        wait=wait_exponential(min=1, max=10),
        retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError))
    )
    def get_price(self, token_address: str, chain="evm", specific="eth") -> dict:
        self._rate_limit_wait("price")
        r = self.session.get(
            f"{self.base_url}/api/price",
            params={"token": token_address, "chain": chain, "specificChain": specific},
            headers=self.headers, 
            timeout=15,
        )
        r.raise_for_status()
        return r.json()

    @retry(
        stop=stop_after_attempt(3), 
        wait=wait_exponential(min=1, max=8)
    )
    def quote(self, base_token: str, quote_token: str, usd_amount: float,
              from_chain="evm", from_specific="eth", 
              to_chain="evm", to_specific="eth") -> dict:
        self._rate_limit_wait("trade")
        payload = {
            "baseToken": base_token,
            "quoteToken": quote_token,
            "tradeAmountUsd": float(usd_amount),
            "fromChain": from_chain, 
            "fromSpecificChain": from_specific,
            "toChain": to_chain, 
            "toSpecificChain": to_specific,
        }
        r = self.session.post(
            f"{self.base_url}/api/trade/quote", 
            json=payload, 
            headers=self.headers, 
            timeout=20
        )
        r.raise_for_status()
        return r.json()

    @retry(
        stop=stop_after_attempt(5), 
        wait=wait_exponential(min=2, max=15)
    )
    def execute(self, base_token: str, quote_token: str, usd_amount: float, 
                reason: str, slippage_tolerance_pct: float,
                from_chain="evm", from_specific="eth", 
                to_chain="evm", to_specific="eth") -> dict:
        self._rate_limit_wait("trade")
        payload = {
            "baseToken": base_token,
            "quoteToken": quote_token,
            "tradeAmountUsd": float(usd_amount),
            "reason": reason,
            "slippageTolerancePct": float(slippage_tolerance_pct),
            "fromChain": from_chain, 
            "fromSpecificChain": from_specific,
            "toChain": to_chain, 
            "toSpecificChain": to_specific,
        }
        r = self.session.post(
            f"{self.base_url}/api/trade/execute", 
            json=payload, 
            headers=self.headers, 
            timeout=40
        )
        try:
            r.raise_for_status()
        except requests.HTTPError as e:
            LOG.error(f"Trade execution failed: {e} | Response: {r.text[:500]}")
            raise requests.HTTPError(f"{e} | body={r.text[:500]}") from e
        return r.json()

    @retry(
        stop=stop_after_attempt(4), 
        wait=wait_exponential(min=1, max=8)
    )
    def balances(self) -> dict:
        self._rate_limit_wait("balance")
        r = self.session.get(
            f"{self.base_url}/api/agent/balances", 
            headers=self.headers, 
            timeout=20
        )
        r.raise_for_status()
        return r.json()
    
    @retry(
        stop=stop_after_attempt(3), 
        wait=wait_exponential(min=1, max=6)
    )
    def get_tokens(self, chain="evm", specific="eth", limit=100) -> dict:
        """Fetch available tokens for a chain"""
        self._rate_limit_wait("price")
        r = self.session.get(
            f"{self.base_url}/api/tokens",
            params={"chain": chain, "specificChain": specific, "limit": limit},
            headers=self.headers,
            timeout=15
        )
        r.raise_for_status()
        return r.json()
