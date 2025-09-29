from __future__ import annotations
from .logger import setup_logger

LOG = setup_logger()

class TokenFilter:
    """Filters tokens based on competition eligibility criteria"""
    
    def __init__(self, min_age_hours: float, min_24h_vol: float, 
                 min_liquidity: float, min_fdv: float):
        self.min_age_h = min_age_hours
        self.min_vol = min_24h_vol
        self.min_liq = min_liquidity
        self.min_fdv = min_fdv
    
    def is_eligible(self, token_data: dict) -> tuple[bool, str]:
        """
        Check if token meets all eligibility requirements.
        Returns (eligible, reason)
        """
        age_h = float(token_data.get('ageHours', 0))
        if age_h < self.min_age_h:
            return False, f"Age {age_h:.0f}h < {self.min_age_h:.0f}h"

        vol_24h = float(token_data.get('volume24h', 0))
        if vol_24h < self.min_vol:
            return False, f"Vol24h ${vol_24h:.0f} < ${self.min_vol:.0f}"

        liquidity = float(token_data.get('liquidity', 0))
        if liquidity < self.min_liq:
            return False, f"Liquidity ${liquidity:.0f} < ${self.min_liq:.0f}"

        fdv = float(token_data.get('fdv', 0))
        if fdv < self.min_fdv:
            return False, f"FDV ${fdv:.0f} < ${self.min_fdv:.0f}"
        
        return True, "OK"
    
    def filter_tokens(self, tokens: list[dict]) -> list[dict]:
        """Return only eligible tokens from a list"""
        eligible = []
        for tok in tokens:
            ok, reason = self.is_eligible(tok)
            symbol = tok.get('symbol', 'UNK')
            if ok:
                LOG.debug(f"✓ {symbol} eligible")
                eligible.append(tok)
            else:
                LOG.debug(f"✗ {symbol} rejected: {reason}")
        
        LOG.info(f"Token filter: {len(eligible)}/{len(tokens)} eligible")
        return eligible
