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
        """
        Buy quote_token using base_token (usually USDC -> target token).
        """
        reason = "Strategy Entry"
        LOG.info(f"BUY: {base_token[:8]}... -> {quote_token[:8]}... | ${usd_amount:.2f} on {chain}/{specific}")
        
        return self.rc.execute(
            base_token, quote_token, usd_amount, reason,
            slippage_tolerance_pct=self.slippage,
            from_chain=chain, from_specific=specific,
            to_chain=chain, to_specific=specific
        )

    def sell_all(self, token: str, to_usdc: str, usd_chunk: float,
                 chain='evm', specific='eth') -> dict:
        """
        Sell token back to USDC.
        """
        reason = "Strategy Exit"
        LOG.info(f"SELL: {token[:8]}... -> {to_usdc[:8]}... | ${usd_chunk:.2f} on {chain}/{specific}")
        
        return self.rc.execute(
            token, to_usdc, usd_chunk, reason,
            slippage_tolerance_pct=self.slippage,
            from_chain=chain, from_specific=specific,
            to_chain=chain, to_specific=specific
        )
    
    def cross_chain_swap(self, token: str, target_token: str, usd_amount: float,
                        from_chain: str, from_specific: str,
                        to_chain: str, to_specific: str) -> dict:
        """
        Execute cross-chain swap (if allowed by competition rules).
        """
        reason = "Cross-chain Rebalance"
        LOG.info(f"CROSS-CHAIN: {token[:8]}... -> {target_token[:8]}... | ${usd_amount:.2f}")
        LOG.info(f"  From: {from_chain}/{from_specific} -> To: {to_chain}/{to_specific}")
        
        return self.rc.execute(
            token, target_token, usd_amount, reason,
            slippage_tolerance_pct=self.slippage,
            from_chain=from_chain, from_specific=from_specific,
            to_chain=to_chain, to_specific=to_specific
        )
