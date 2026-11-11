#!/usr/bin/env python3
"""
trader-smc/smc.py
Smart Money Concepts (SMC) Analyzer for XAUUSD:
- Bullish/Bearish Order Blocks (Demand & Supply OB)
- Fair Value Gaps (FVG / 3-Bar Imbalance)
- Break of Structure (BOS)
Writes trader/smc.json.
"""

from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "trader-scanner"))
import scan as mod_scan  # type: ignore


def analyze_smc(bars: List[Dict[str, Any]], symbol: str = "XAUUSD") -> Dict[str, Any]:
    if len(bars) < 20:
        raise ValueError("Need at least 20 bars for SMC analysis")

    atr = mod_scan.compute_atr(bars, 14)
    last_close = float(bars[-1]["close"])

    demand_obs: List[Dict[str, Any]] = []
    supply_obs: List[Dict[str, Any]] = []
    fvgs: List[Dict[str, Any]] = []

    for i in range(2, len(bars)):
        b0 = bars[i - 2]
        b1 = bars[i - 1]
        b2 = bars[i]

        h0, l0, o0, c0 = float(b0["high"]), float(b0["low"]), float(b0["open"]), float(b0["close"])
        h1, l1, o1, c1 = float(b1["high"]), float(b1["low"]), float(b1["open"]), float(b1["close"])
        h2, l2, o2, c2 = float(b2["high"]), float(b2["low"]), float(b2["open"]), float(b2["close"])

        # Bullish FVG: candle i-2 high < candle i low
        if l2 > h0 and (c1 - o1) > atr * 0.30:
            fvgs.append({
                "type": "BULLISH_FVG",
                "bottom": round(h0, 2),
                "top": round(l2, 2),
                "mid": round((h0 + l2) / 2.0, 2),
                "time": b1.get("time", ""),
            })
        # Bearish FVG: candle i-2 low > candle i high
        elif h2 < l0 and (o1 - c1) > atr * 0.30:
            fvgs.append({
                "type": "BEARISH_FVG",
                "bottom": round(h2, 2),
                "top": round(l0, 2),
                "mid": round((h2 + l0) / 2.0, 2),
                "time": b1.get("time", ""),
            })

        # Order Block detection before strong impulse
        impulse_up = (c2 - o2) >= atr * 0.45 and c2 > h1
        impulse_dn = (o2 - c2) >= atr * 0.45 and c2 < l1
        if impulse_up:
            ob_bot = round(min(l1, l2), 2)
            ob_top = round(ob_bot + max(0.25, atr * 0.35), 2)
            demand_obs.append({
                "type": "DEMAND_OB",
                "bottom": ob_bot,
                "top": ob_top,
                "poi": round((ob_bot + ob_top) / 2.0, 2),
                "time": b1.get("time", ""),
            })
        elif impulse_dn:
            ob_top = round(max(h1, h2), 2)
            ob_bot = round(ob_top - max(0.25, atr * 0.35), 2)
            supply_obs.append({
                "type": "SUPPLY_OB",
                "bottom": ob_bot,
                "top": ob_top,
                "poi": round((ob_bot + ob_top) / 2.0, 2),
                "time": b1.get("time", ""),
            })

    # Fallback synthetic OB around current structure if smooth trend had no opposing candle
    if not demand_obs:
        ob_bot = round(last_close - atr * 0.80, 2)
        ob_top = round(last_close - atr * 0.35, 2)
        demand_obs.append({
            "type": "DEMAND_OB",
            "bottom": ob_bot,
            "top": ob_top,
            "poi": round((ob_bot + ob_top) / 2.0, 2),
            "time": bars[-1].get("time", ""),
        })
    if not supply_obs:
        ob_bot = round(last_close + atr * 0.35, 2)
        ob_top = round(last_close + atr * 0.80, 2)
        supply_obs.append({
            "type": "SUPPLY_OB",
            "bottom": ob_bot,
            "top": ob_top,
            "poi": round((ob_bot + ob_top) / 2.0, 2),
            "time": bars[-1].get("time", ""),
        })

    prev_swing_high = max(float(b["high"]) for b in bars[-16:-1])
    prev_swing_low = min(float(b["low"]) for b in bars[-16:-1])
    cur_high = float(bars[-1]["high"])
    cur_low = float(bars[-1]["low"])

    if last_close > prev_swing_high:
        structure = "BOS_BULLISH"
        smc_bias = "BULLISH"
        score = 88
    elif last_close < prev_swing_low:
        structure = "BOS_BEARISH"
        smc_bias = "BEARISH"
        score = 88
    else:
        structure = "INTERNAL_RANGE"
        smc_bias = "BULLISH" if last_close >= (prev_swing_high + prev_swing_low) / 2.0 else "BEARISH"
        score = 72

    # Buy-Side Liquidity (BSL above Equal Highs / Swing High) & Sell-Side Liquidity (SSL below Equal Lows / Swing Low)
    bsl_level = round(max(prev_swing_high, last_close + atr * 0.35), 2)
    ssl_level = round(min(prev_swing_low, last_close - atr * 0.35), 2)

    if cur_high >= prev_swing_high and last_close < prev_swing_high:
        sweep_state = "BSL_SWEPT_BEARISH_REJECTION"
    elif cur_low <= prev_swing_low and last_close > prev_swing_low:
        sweep_state = "SSL_SWEPT_BULLISH_REJECTION"
    else:
        sweep_state = "LIQUIDITY_POOL_BUILDING"

    liquidity_pools = {
        "bsl_level": bsl_level,
        "ssl_level": ssl_level,
        "sweep_state": sweep_state,
        "bsl_sweep_zone": {
            "type": "BSL_STOP_HUNT_ZONE",
            "bottom": round(bsl_level - atr * 0.12, 2),
            "top": round(bsl_level + atr * 0.15, 2),
            "poi": bsl_level,
        },
        "ssl_sweep_zone": {
            "type": "SSL_STOP_HUNT_ZONE",
            "bottom": round(ssl_level - atr * 0.15, 2),
            "top": round(ssl_level + atr * 0.12, 2),
            "poi": ssl_level,
        },
    }

    return {
        "skill": "trader-smc",
        "symbol": symbol,
        "timestamp": bars[-1].get("time", dt.datetime.now(dt.timezone.utc).isoformat()),
        "last_price": last_close,
        "structure_state": structure,
        "smc_bias": smc_bias,
        "smc_score": score,
        "nearest_demand_ob": demand_obs[-1],
        "nearest_supply_ob": supply_obs[-1],
        "active_fvgs": fvgs[-3:],
        "liquidity_pools": liquidity_pools,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="XAUUSD Smart Money Concepts (OB, FVG, BOS) Analyzer")
    parser.add_argument("--symbol", default="XAUUSD", help="Symbol")
    parser.add_argument("--bars-file", default=None, help="Optional OHLCV bars JSON")
    parser.add_argument("--output", default="trader/smc.json", help="Output JSON path")
    args = parser.parse_args(argv)

    bars = mod_scan.load_bars(bars_file=args.bars_file, symbol=args.symbol)
    res = analyze_smc(bars, symbol=args.symbol)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
