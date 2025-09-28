from __future__ import annotations
from ..recall_client import RecallClient
from ..logger import setup_logger

LOG = setup_logger()

class Executor:
    def __init__(self, rc: RecallClient, slippage_tolerance_pct: float):
        self.rc = rc
        self.slippage = slippage_tolerance_pct

    def trade_usd_notional(self, base_token: str, quote_token: str, usd_amount: float,
                           chain='evm', specific='eth') -> dict:
        reason = "Policy Rebalance"
        LOG.info(f"BUY: {base_token[:6]} -> {quote_token[:6]} | usd={usd_amount}")
        return self.rc.execute(base_token, quote_token, usd_amount, reason,
                               slippage_tolerance_pct=self.slippage,
                               from_chain=chain, from_specific=specific,
                               to_chain=chain, to_specific=specific)

    def sell_all(self, token: str, to_usdc: str, usd_chunk: float,
                 chain='evm', specific='eth') -> dict:
        reason = "Exit Leg"
        LOG.info(f"SELL: {token[:6]} -> {to_usdc[:6]} | usd={usd_chunk}")
        return self.rc.execute(token, to_usdc, usd_chunk, reason,
                               slippage_tolerance_pct=self.slippage,
                               from_chain=chain, from_specific=specific,
                               to_chain=chain, to_specific=specific)
