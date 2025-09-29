from __future__ import annotations
import time, numpy as np
from pathlib import Path
from tenacity import retry, stop_after_attempt, wait_exponential
import requests

from .logger import setup_logger
from .utils import load_yaml, env_config
from .recall_client import RecallClient
from .rate_limiter import RateLimiter
from .token_filter import TokenFilter
from .data import PriceSeries, realized_vol
from .signals.momentum_vol import MomVolSignal
from .risk.manager import RiskManager, RiskParams
from .portfolio.allocator import risk_parity_weights
from .execution.executor import Executor
from .metrics import max_drawdown, sharpe_ratio

LOG = setup_logger()

@retry(stop=stop_after_attempt(5), wait=wait_exponential(min=1, max=12))
def health_check(rc: RecallClient):
    r = rc.session.get(f"{rc.base_url}/api/health", headers=rc.headers, timeout=20)
    r.raise_for_status()
    js = r.json() if r.ok else {}
    if js.get("status") == "ok" or r.status_code == 200:
        LOG.info("✓ API health OK")
        return
    raise RuntimeError(f"Health not ok: {r.status_code}, {r.text[:200]}")

def get_token_balance(balances: dict, symbol: str, chain: str = None, specific: str = None) -> float:
    """Get balance for a token, optionally filtering by chain"""
    for b in balances.get("balances", []):
        tok_sym = (b.get("symbol") or "").upper()
        if tok_sym != symbol.upper():
            continue
        if chain and b.get("chain") != chain:
            continue
        if specific and b.get("specificChain") != specific:
            continue
        return float(b.get("amount", 0.0))
    return 0.0

def mark_to_market_usd(rc: RecallClient, balances: dict, tracked_tokens: dict) -> tuple[float, dict]:
    """
    Calculate total portfolio value and per-asset exposure.
    tracked_tokens: {symbol: {address, chain, specific}}
    Returns: (total_equity_usd, {symbol: exposure_usd})
    """
    price_cache = {}
    exposures = {}
    
    def _get_price(addr: str, ch: str, sp: str) -> float:
        key = f"{addr}:{ch}:{sp}".lower()
        if key not in price_cache:
            try:
                p = rc.get_price(addr, chain=ch, specific=sp)
                price_cache[key] = float(p.get("price") or p.get("prices", {}).get("toToken", 0) or 0)
            except Exception as e:
                LOG.warning(f"Price fetch failed {addr[:8]}...{ch}/{sp}: {e}")
                price_cache[key] = 0.0
        return price_cache[key]
    
    total_usd = 0.0
    
    for b in balances.get("balances", []):
        qty = float(b.get("amount", 0))
        if qty <= 0:
            continue
        
        sym = (b.get("symbol") or "").upper()
        addr = (b.get("tokenAddress") or "").lower()
        ch = b.get("chain", "evm")
        sp = b.get("specificChain", "eth")

        if sym == "USDC":
            total_usd += qty
            exposures[f"USDC_{sp}"] = exposures.get(f"USDC_{sp}", 0) + qty
            continue

        if not addr and sym in tracked_tokens:
            token_info = tracked_tokens[sym]
            addr = token_info["address"].lower()
            ch = token_info["chain"]
            sp = token_info["specific"]
        
        if addr:
            px = _get_price(addr, ch, sp)
            usd_val = qty * px
            total_usd += usd_val
            exposures[f"{sym}_{sp}"] = exposures.get(f"{sym}_{sp}", 0) + usd_val
    
    LOG.info(f"MTM | Total: ${total_usd:.2f} | Assets: {len([v for v in exposures.values() if v > 1])}")
    return total_usd, exposures

def write_telemetry(csv_path: Path, t: float, equity: float, sharpe: float, mdd: float, trades: int):
    header = ["timestamp", "equity_usd", "sharpe", "max_drawdown", "daily_trades"]
    newfile = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as f:
        import csv as _csv
        w = _csv.writer(f)
        if newfile:
            w.writerow(header)
        w.writerow([int(t), round(equity, 2), round(sharpe, 3), round(mdd, 4), trades])

def discover_tokens(rc: RecallClient, chains: list[dict], token_filter: TokenFilter) -> dict:
    """
    Discover top liquid tokens across all chains.
    Returns: {symbol_chain: {address, chain, specific, ...}}
    """
    discovered = {}
    
    for chain_cfg in chains:
        ch = chain_cfg["chain"]
        sp = chain_cfg["specific"]
        LOG.info(f"Discovering tokens on {ch}/{sp}...")
        
        try:
            resp = rc.get_tokens(chain=ch, specific=sp, limit=50)
            tokens = resp.get("tokens", [])
            eligible = token_filter.filter_tokens(tokens)
            
            for tok in eligible[:10]: 
                sym = tok.get("symbol", "UNK").upper()
                addr = tok.get("address", "")
                if not addr:
                    continue
                
                key = f"{sym}_{sp}"
                discovered[key] = {
                    "symbol": sym,
                    "address": addr,
                    "chain": ch,
                    "specific": sp,
                    "volume24h": tok.get("volume24h", 0),
                    "liquidity": tok.get("liquidity", 0),
                }
            
            LOG.info(f"  → {len(eligible)} eligible tokens on {ch}/{sp}")
        
        except Exception as e:
            LOG.error(f"Token discovery failed on {ch}/{sp}: {e}")
    
    LOG.info(f"Total discovered: {len(discovered)} tokens")
    return discovered

def run():
    cfg = load_yaml(str(Path(__file__).parent.parent / "config" / "config.yaml"))
    env = env_config(cfg)
    LOG.info(f"Using base_url={env.base_url}")

    rate_limits = cfg.get("rate_limits", {})
    limiter = RateLimiter(rate_limits)

    rc = RecallClient(base_url=env.base_url, api_key=env.api_key, rate_limiter=limiter)
    health_check(rc)

    tf_cfg = cfg.get("token_filters", {})
    token_filter = TokenFilter(
        min_age_hours=float(tf_cfg.get("min_age_hours", 4380)),
        min_24h_vol=float(tf_cfg.get("min_24h_volume_usd", 500000)),
        min_liquidity=float(tf_cfg.get("min_liquidity_usd", 500000)),
        min_fdv=float(tf_cfg.get("min_fdv_usd", 1000000))
    )

    chains = cfg.get("chains", [])
    universe = discover_tokens(rc, chains, token_filter)
    
    if not universe:
        LOG.error("No eligible tokens found! Exiting.")
        return
   
    strat_cfg = cfg.get("strategy", {})
    look_s = int(strat_cfg.get("lookback_short", 20))
    look_l = int(strat_cfg.get("lookback_long", 100))
    vol_look = int(strat_cfg.get("vol_lookback", 80))
    z_entry = float(strat_cfg.get("z_entry", 1.2))
    z_exit = float(strat_cfg.get("z_exit", 0.3))
    min_mom = float(strat_cfg.get("min_momentum", 0.005))
    bar_sec = int(strat_cfg.get("bar_seconds", 45))
    
    LOG.info(f"Strategy: short={look_s} long={look_l} vol={vol_look} z_entry={z_entry} bar={bar_sec}s")

    risk_cfg = cfg.get("risk", {})
    risk = RiskManager(RiskParams(
        min_daily_trades=int(risk_cfg.get("min_daily_trades", 3)),
        max_daily_trades=int(risk_cfg.get("max_daily_trades", 120)),
        cooldown_seconds=int(risk_cfg.get("cooldown_seconds", 20)),
        max_single_trade_pct=float(risk_cfg.get("max_single_trade_pct", 0.25)),
        per_trade_base_usd=float(risk_cfg.get("per_trade_base_usd", 100)),
        max_drawdown_stop=float(risk_cfg.get("max_drawdown_stop", 0.18)),
        slippage_tolerance_pct=float(risk_cfg.get("slippage_tolerance_pct", 1.0)),
        max_exposure_per_asset_pct=float(risk_cfg.get("max_exposure_per_asset_pct", 0.35))
    ))

    port_cfg = cfg.get("portfolio", {})
    rebalance_every = float(port_cfg.get("rebalance_every_sec", 180))
    target_cash_frac = float(port_cfg.get("target_cash_frac", 0.15))
    max_assets = int(port_cfg.get("max_assets", 8))

    tele_cfg = cfg.get("telemetry", {})
    csv_path = Path(tele_cfg.get("csv_path", "telemetry_equity.csv"))
    log_every = float(tele_cfg.get("log_every_sec", 300))

    ex = Executor(rc, slippage_tolerance_pct=risk.p.slippage_tolerance_pct)

    price_series = {}
    for key in universe:
        price_series[key] = PriceSeries(maxlen=max(look_l, vol_look) + 20)

    sig = MomVolSignal(look_s, look_l, vol_look, z_entry, z_exit)

    last_rebalance = 0.0
    last_log = 0.0
    eq_series = []
    
    LOG.info(f"Starting main loop with {len(universe)} tokens...")
    
    while True:
        try:
            now = time.time()

            for key, tok in universe.items():
                try:
                    p_resp = rc.get_price(
                        tok["address"], 
                        chain=tok["chain"], 
                        specific=tok["specific"]
                    )
                    px = float(p_resp.get("price") or p_resp.get("prices", {}).get("toToken", 0) or 0)
                    if px > 0:
                        price_series[key].add(px)
                except Exception as e:
                    LOG.debug(f"Price fetch failed {key}: {e}")

            min_ready = min(look_l, vol_look)
            ready_count = sum(1 for ps in price_series.values() if ps.ready(min_ready))
            if ready_count < 2:
                LOG.info(f"Warmup: {ready_count}/{len(price_series)} tokens ready")
                time.sleep(bar_sec)
                continue

            signals = {}
            for key, ps in price_series.items():
                if not ps.ready(min_ready):
                    continue
                
                arr = ps.np()
                weight = sig.decide_weight(arr)
                mom = float(np.mean(arr[-look_s:]) / np.mean(arr[-look_l:]) - 1.0)
                vol = realized_vol(arr[-vol_look:])
                
                if mom > min_mom and weight > 0:
                    signals[key] = {
                        "weight": weight,
                        "momentum": mom,
                        "volatility": vol,
                        "price": arr[-1]
                    }
            
            LOG.info(f"Signals: {len(signals)} tokens with positive signal")

            bals = rc.balances()
            equity, exposures = mark_to_market_usd(rc, bals, universe)
            eq_series.append(equity)

            if signals:
                vols_dict = {k: v["volatility"] for k, v in signals.items()}
                rp_weights = risk_parity_weights(vols_dict, long_only=True)

                for key in signals:
                    signals[key]["final_weight"] = signals[key]["weight"] * rp_weights[key]

                total_w = sum(s["final_weight"] for s in signals.values())
                if total_w > 0:
                    for key in signals:
                        signals[key]["final_weight"] /= total_w

            for key, tok in universe.items():
                sym = tok["symbol"]
                sp = tok["specific"]

                bal = get_token_balance(bals, sym, chain=tok["chain"], specific=sp)
                if bal <= 0:
                    continue

                exposure = exposures.get(key, 0)
                if exposure < 1:
                    continue

                should_exit = False
                if key not in signals:
                    should_exit = True
                    reason = "no signal"
                else:
                    ps = price_series[key]
                    if ps.ready(min_ready):
                        arr = ps.np()
                        mom = float(np.mean(arr[-look_s:]) / np.mean(arr[-look_l:]) - 1.0)
                        if mom < min_mom:
                            should_exit = True
                            reason = f"low momentum {mom:.2%}"
                
                if should_exit:
                    LOG.info(f"EXIT {key}: {reason} | exposure=${exposure:.2f}")
                    try:
                        usdc_addr = None
                        for ub_key, ub_tok in universe.items():
                            if ub_tok["symbol"] == "USDC" and ub_tok["specific"] == sp:
                                usdc_addr = ub_tok["address"]
                                break
                        
                        if usdc_addr:
                            trade_size = min(exposure, risk.p.per_trade_base_usd)
                            res = ex.sell_all(
                                tok["address"], usdc_addr, trade_size,
                                chain=tok["chain"], specific=sp
                            )
                            LOG.info(f"  → Sold ${trade_size:.2f}: {res.get('transactionHash', 'OK')}")
                            risk.mark_trade()
                        else:
                            LOG.warning(f"  → No USDC found on {sp}, skip exit")
                    
                    except Exception as e:
                        LOG.error(f"Exit failed for {key}: {e}")

            if now - last_rebalance >= rebalance_every:
                LOG.info(f"=== REBALANCE (trades today: {risk.get_daily_trade_count()}) ===")
                
                ok, why = risk.check_pretrade(equity)
                if not ok:
                    LOG.warning(f"Skip rebalance: {why}")
                else:
                    sorted_signals = sorted(
                        signals.items(), 
                        key=lambda x: x[1]["final_weight"], 
                        reverse=True
                    )[:max_assets]
                    
                    for key, sig_data in sorted_signals:
                        tok = universe[key]
                        sym = tok["symbol"]
                        sp = tok["specific"]

                        target_pct = sig_data["final_weight"] * (1.0 - target_cash_frac)
                        target_usd = equity * target_pct

                        current_exp = exposures.get(key, 0)

                        delta_usd = target_usd - current_exp
                        
                        if delta_usd > 5: 
                            trade_size = min(delta_usd, risk.p.per_trade_base_usd)
                            
                            ok_size, msg = risk.check_trade_size(trade_size, equity)
                            if not ok_size:
                                LOG.warning(f"  {key} trade size check: {msg}")
                                continue
                            
                            ok_exp, msg = risk.check_asset_exposure(current_exp + trade_size, equity)
                            if not ok_exp:
                                LOG.warning(f"  {key} exposure check: {msg}")
                                continue

                            usdc_addr = None
                            for ub_key, ub_tok in universe.items():
                                if ub_tok["symbol"] == "USDC" and ub_tok["specific"] == sp:
                                    usdc_addr = ub_tok["address"]
                                    break
                            
                            if not usdc_addr:
                                LOG.warning(f"  {key} no USDC on {sp}")
                                continue
                            
                            try:
                                LOG.info(f"BUY {key}: ${trade_size:.2f} (target={target_pct:.1%})")
                                res = ex.trade_usd_notional(
                                    usdc_addr, tok["address"], trade_size,
                                    chain=tok["chain"], specific=sp
                                )
                                LOG.info(f"  → {res.get('transactionHash', 'OK')}")
                                risk.mark_trade()
                            
                            except Exception as e:
                                LOG.error(f"  {key} buy failed: {e}")
                
                last_rebalance = now

            if len(eq_series) >= 3 and (now - last_log) >= log_every:
                sh = sharpe_ratio(eq_series, bar_seconds=bar_sec)
                mdd = max_drawdown(eq_series)
                trades_today = risk.get_daily_trade_count()
                
                LOG.info(f"📊 Equity=${equity:.2f} | Sharpe={sh:.2f} | MDD={mdd:.1%} | Trades={trades_today}")
                
                if risk.needs_more_trades():
                    LOG.warning(f"⚠️  Need {risk.p.min_daily_trades - trades_today} more trades today!")
                
                write_telemetry(csv_path, now, equity, sh, mdd, trades_today)
                last_log = now

            time.sleep(bar_sec)
        
        except KeyboardInterrupt:
            LOG.info("🛑 Interrupted by user")
            break
        
        except requests.HTTPError as e:
            LOG.exception(f"HTTP error: {e}")
            time.sleep(10)
        
        except Exception as e:
            LOG.exception(f"Main loop error: {e}")
            time.sleep(10)
    
    LOG.info("Agent stopped")

if __name__ == "__main__":
    run()
