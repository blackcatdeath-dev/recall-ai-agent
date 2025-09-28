from __future__ import annotations
import requests
from tenacity import retry, stop_after_attempt, wait_exponential
from .logger import setup_logger

LOG = setup_logger()

class RecallClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        
        adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=10)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(min=1, max=8))
    def get_price(self, token_address: str, chain="evm", specific="eth") -> dict:
        r = self.session.get(
            f"{self.base_url}/api/price",
            params={"token": token_address, "chain": chain, "specificChain": specific},
            headers=self.headers, timeout=15,
        )
        r.raise_for_status()
        return r.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=6))
    def quote(self, base_token: str, quote_token: str, usd_amount: float,
              from_chain="evm", from_specific="eth", to_chain="evm", to_specific="eth") -> dict:
        payload = {
            "baseToken": base_token,
            "quoteToken": quote_token,
            "tradeAmountUsd": float(usd_amount),
            "fromChain": from_chain, "fromSpecificChain": from_specific,
            "toChain": to_chain, "toSpecificChain": to_specific,
        }
        r = self.session.post(f"{self.base_url}/api/trade/quote", json=payload, headers=self.headers, timeout=20)
        r.raise_for_status()
        return r.json()

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(min=1, max=12))
    def execute(self, base_token: str, quote_token: str, usd_amount: float, reason: str,
                slippage_tolerance_pct: float, from_chain="evm", from_specific="eth", to_chain="evm", to_specific="eth") -> dict:
        payload = {
            "baseToken": base_token,
            "quoteToken": quote_token,
            "tradeAmountUsd": float(usd_amount),
            "reason": reason,
            "slippageTolerancePct": float(slippage_tolerance_pct),
            "fromChain": from_chain, "fromSpecificChain": from_specific,
            "toChain": to_chain, "toSpecificChain": to_specific,
        }
        r = self.session.post(f"{self.base_url}/api/trade/execute", json=payload, headers=self.headers, timeout=30)
        try:
            r.raise_for_status()
        except requests.HTTPError as e:
            raise requests.HTTPError(f"{e} | body={r.text}") from e
        return r.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=6))
    def balances(self) -> dict:
        r = self.session.get(f"{self.base_url}/api/agent/balances", headers=self.headers, timeout=15)
        r.raise_for_status()
        return r.json()
