from __future__ import annotations
import time, numpy as np
from pathlib import Path
from tenacity import retry, stop_after_attempt, wait_exponential
import requests

from .logger import setup_logger
from .utils import load_yaml, env_config
from .recall_client import RecallClient
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
    try:
        js = r.json()
    except Exception:
        js = {}
    if js.get("status") == "ok" or r.status_code == 200:
        LOG.info("API health OK")
        return
    raise RuntimeError(f"Health not ok: code={r.status_code}, body={r.text[:200]}")

def get_token_balance(balances: dict, symbol: str) -> float:
    for b in balances.get("balances", []):
        if (b.get("symbol") or "").upper() == symbol.upper():
            return float(b.get("amount", 0.0))
    return 0.0

def mark_to_market_usd(rc: RecallClient, balances: dict, universe: dict) -> tuple[float, float, dict]:
    usdc_addr = universe["USDC"]["address"].lower()
    tracked_addrs = {universe[s]["address"].lower() for s in universe if s != "USDC"}
    price_cache: dict[str, float] = {}
    cash_usd = 0.0
    exposure_tracked = 0.0
    ignored_noncash = 0.0

    def _price(addr: str, ch: str, sp: str) -> float:
        key = addr.lower()
        if key not in price_cache:
            p = rc.get_price(addr, chain=ch, specific=sp)
            price_cache[key] = float(p.get("price") or p.get("prices", {}).get("toToken", 0.0) or 0.0)
        return price_cache[key]

    for b in balances.get("balances", []):
        qty = float(b.get("amount", 0.0))
        if qty <= 0: continue
        addr = (b.get("tokenAddress") or "").lower()
        ch = b.get("chain", "evm"); sp = b.get("specificChain", "eth")
        if not addr:
            sym = (b.get("symbol") or "").upper()
            if sym in universe:
                addr = universe[sym]["address"].lower()
                ch = universe[sym]["chain"]; sp = universe[sym]["specific"]
        if addr == usdc_addr:
            cash_usd += qty; continue
        px = _price(addr, ch, sp); usd = qty * px
        if addr in tracked_addrs: exposure_tracked += usd
        else: ignored_noncash += usd

    equity = cash_usd + exposure_tracked + ignored_noncash
    LOG.info("MTM | cash=$%.2f exposure_tracked=$%.2f ignored_noncash=$%.2f equity=$%.2f" % (cash_usd, exposure_tracked, ignored_noncash, equity))
    return float(equity), float(exposure_tracked), price_cache

def write_telemetry(csv_path: Path, t: float, equity: float, sharpe: float, mdd: float):
    header = ["timestamp","equity_usd","sharpe","max_drawdown"]
    newfile = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as f:
        import csv as _csv
        w = _csv.writer(f)
        if newfile: w.writerow(header)
        w.writerow([int(t), round(equity,4), round(sharpe,4), round(mdd,4)])

def run():
    cfg = load_yaml(str(Path(__file__).parent.parent / "config" / "config.yaml"))
    env = env_config(cfg)
    LOG.info(f"Using base_url={env.base_url}")

    rc = RecallClient(base_url=env.base_url, api_key=env.api_key)
    health_check(rc)

    risk_cfg = cfg.get("risk", {}); tele_cfg = cfg.get("telemetry", {}); port_cfg = cfg.get("portfolio", {}); strat_cfg = cfg.get("strategy", {})
    look_s = int(strat_cfg.get("lookback_short", 20))
    look_l = int(strat_cfg.get("lookback_long", 120))
    vol_look = int(strat_cfg.get("vol_lookback", 120))
    z_entry = float(strat_cfg.get("z_entry", 1.0))
    z_exit = float(strat_cfg.get("z_exit", 0.2))
    min_mom = float(strat_cfg.get("min_momentum", 0.0))
    bar_sec = int(strat_cfg.get("bar_seconds", 30))
    LOG.info(f"CFG strategy => short={look_s} long={look_l} vol={vol_look} z_exit={z_exit} min_mom={min_mom} bar={bar_sec}")

    risk = RiskManager(RiskParams(
        max_daily_trades=int(risk_cfg.get("max_daily_trades", 60)),
        cooldown_seconds=int(risk_cfg.get("cooldown_seconds", 30)),
        max_gross_exposure_usd=float(risk_cfg.get("max_gross_exposure_usd", 2000)),
        per_trade_usd=float(risk_cfg.get("per_trade_usd", 25)),
        max_drawdown_stop=float(risk_cfg.get("max_drawdown_stop", 0.20)),
        slippage_tolerance_pct=float(risk_cfg.get("slippage_tolerance_pct", 0.5)),
    ))

    rebalance_every = float(port_cfg.get("rebalance_every_sec", 120))
    target_cash_frac = float(port_cfg.get("target_cash_frac", 0.2))
    csv_path = Path(tele_cfg.get("csv_path", "telemetry_equity.csv"))
    log_every = float(tele_cfg.get("log_every_sec", 300))

    ex = Executor(rc, slippage_tolerance_pct=risk.p.slippage_tolerance_pct)

    U = cfg.get("universe", {}).get("tokens", {})
    USDC = U["USDC"]["address"]; WETH = U["WETH"]["address"]; WBTC = U["WBTC"]["address"]

    px_WETH = PriceSeries(maxlen=max(look_l, vol_look) + 10)
    px_WBTC = PriceSeries(maxlen=max(look_l, vol_look) + 10)
    sig = MomVolSignal(look_s, look_l, vol_look, z_entry, z_exit)

    last_rebalance = 0.0; last_log = 0.0; eq_series: list[float] = []

    while True:
        try:
            pWETH = rc.get_price(WETH, chain=U["WETH"]["chain"], specific=U["WETH"]["specific"])
            pWBTC = rc.get_price(WBTC, chain=U["WBTC"]["chain"], specific=U["WBTC"]["specific"])
            px_weth = float(pWETH.get("price") or pWETH.get("prices", {}).get("toToken", 0.0) or 0.0)
            px_wbtc = float(pWBTC.get("price") or pWBTC.get("prices", {}).get("toToken", 0.0) or 0.0)
            if px_weth > 0: px_WETH.add(px_weth)
            if px_wbtc > 0: px_WBTC.add(px_wbtc)

            now = time.time()
            min_ready = min(look_l, vol_look)
            if not (px_WETH.ready(min_ready) and px_WBTC.ready(min_ready)):
                LOG.info(f"Warm-up: lenWETH={len(px_WETH.values)}/{min_ready} lenWBTC={len(px_WBTC.values)}/{min_ready}")
                time.sleep(bar_sec); continue

            arr_weth = px_WETH.np(); arr_wbtc = px_WBTC.np()
            w_weth = sig.decide_weight(arr_weth)
            w_wbtc = sig.decide_weight(arr_wbtc)
            mom_weth = float(np.mean(arr_weth[-look_s:]) / np.mean(arr_weth[-look_l:]) - 1.0)
            mom_wbtc = float(np.mean(arr_wbtc[-look_s:]) / np.mean(arr_wbtc[-look_l:]) - 1.0)

            vols = {"WETH": realized_vol(arr_weth[-vol_look:]), "WBTC": realized_vol(arr_wbtc[-vol_look:])}
            rp = risk_parity_weights(vols, long_only=True)
            w_weth *= rp["WETH"]; w_wbtc *= rp["WBTC"]

            w_cash = max(0.0, 1.0 - (w_weth + w_wbtc))
            if w_cash < target_cash_frac:
                scale = (1.0 - target_cash_frac) / max(1e-9, (w_weth + w_wbtc))
                w_weth *= scale; w_wbtc *= scale; w_cash = target_cash_frac

            bals = rc.balances()
            bal_weth = get_token_balance(bals, "WETH")
            bal_wbtc = get_token_balance(bals, "WBTC")
            weth_usd_pos = bal_weth * max(px_weth, 0.0)
            wbtc_usd_pos = bal_wbtc * max(px_wbtc, 0.0)
            sell_usd_weth = min(risk.p.per_trade_usd, weth_usd_pos)
            sell_usd_wbtc = min(risk.p.per_trade_usd, wbtc_usd_pos)

            # EXIT rules
            if (mom_weth < min_mom) or (w_weth == 0.0):
                if sell_usd_weth > 1e-6:
                    res = ex.sell_all(U["WETH"]["address"], U["USDC"]["address"], sell_usd_weth,
                                      chain=U["WETH"]["chain"], specific=U["WETH"]["specific"])
                    LOG.info(f"EXIT WETH: {res}"); risk.mark_trade()
                else:
                    LOG.info("EXIT WETH skipped: no position")
            if (mom_wbtc < min_mom) or (w_wbtc == 0.0):
                if sell_usd_wbtc > 1e-6:
                    res = ex.sell_all(U["WBTC"]["address"], U["USDC"]["address"], sell_usd_wbtc,
                                      chain=U["WBTC"]["chain"], specific=U["WBTC"]["specific"])
                    LOG.info(f"EXIT WBTC: {res}"); risk.mark_trade()
                else:
                    LOG.info("EXIT WBTC skipped: no position")

            if now - last_rebalance >= rebalance_every:
                Umini = {"USDC": U["USDC"], "WETH": U["WETH"], "WBTC": U["WBTC"]}
                equity, exposure, _ = mark_to_market_usd(rc, bals, Umini)
                ok, why = risk.check_pretrade(equity, exposure)
                if not ok:
                    LOG.warning(f"Skip rebalance: {why}")
                else:
                    capacity = max(0.0, risk.p.max_gross_exposure_usd - exposure)
                    trade_amt = min(float(risk.p.per_trade_usd), capacity)
                    LOG.info(f"RISK check | exposure_now=${exposure:.2f} | per_trade=${risk.p.per_trade_usd:.2f} | max_exposure=${risk.p.max_gross_exposure_usd:.2f} | cap_left=${capacity:.2f}")
                    if trade_amt < 1e-6:
                        LOG.warning("Skip rebalance: Exposure limit (no remaining capacity)")
                    else:
                        if w_weth > 0.0:
                            res = ex.trade_usd_notional(U['USDC']['address'], U['WETH']['address'], trade_amt,
                                                        chain=U['USDC']['chain'], specific=U['USDC']['specific'])
                            LOG.info(f"BUY WETH: {res}"); risk.mark_trade()
                        if w_wbtc > 0.0:
                            res = ex.trade_usd_notional(U['USDC']['address'], U['WBTC']['address'], trade_amt,
                                                        chain=U['USDC']['chain'], specific=U['USDC']['specific'])
                            LOG.info(f"BUY WBTC: {res}"); risk.mark_trade()
                    last_rebalance = now

                # Telemetry
                eq_series.append(equity)
                if len(eq_series) >= 3 and (now - last_log) >= log_every:
                    sh = sharpe_ratio(eq_series, bar_seconds=bar_sec)
                    mdd = max_drawdown(eq_series)
                    LOG.info(f"Equity=${equity:.2f} | Sharpe={sh:.2f} | MDD={mdd:.2%}")
                    write_telemetry(csv_path, now, equity, sh, mdd)
                    last_log = now

            time.sleep(bar_sec)

        except KeyboardInterrupt:
            LOG.info("Interrupted by user."); break
        except requests.HTTPError as e:
            LOG.exception(f"HTTP error: {e}")
            time.sleep(5)
        except Exception as e:
            LOG.exception(f"Main loop error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    run()
