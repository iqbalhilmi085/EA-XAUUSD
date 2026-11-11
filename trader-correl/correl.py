#!/usr/bin/env python3
"""
trader-correl/correl.py
Intermarket Correlation & SMT Divergence Analyzer for XAUUSD
(XAGUSD Silver, DXY Dollar Index, US10Y Yield, USDJPY).
Writes trader/correl.json.
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
try:
    import scan as mod_scan  # type: ignore
except Exception:
    mod_scan = None


DEFAULT_INTERMARKET = {
    "as_of": "2026-11-11T13:49:00+00:00",
    "xauusd_change_pct": 0.54,
    "xagusd_change_pct": 0.78,
    "dxy_change_pct": -0.32,
    "us10y_change_bps": -5.8,
    "usdjpy_change_pct": -0.41,
    "smt_divergence": "BULLISH_CONFIRMATION",
}


def fetch_live_intermarket() -> Optional[Dict[str, Any]]:
    if mod_scan is None:
        return None
    tv = mod_scan.fetch_tradingview_live()
    if not tv:
        return None
    xau = tv.get("xau") or {}
    ag = tv.get("silver") or {}
    dxy = tv.get("dxy") or {}
    us10y = tv.get("us10y") or {}
    usdjpy = tv.get("usdjpy") or {}

    xau_chg = round(float(xau.get("change") or 0.0), 2)
    ag_chg = round(float(ag.get("change") or 0.0), 2)
    dxy_chg = round(float(dxy.get("change") or 0.0), 2)
    # US10Y change_abs is in percentage points (e.g. +0.118 = +11.8 bps)
    us10y_abs = float(us10y.get("change_abs") or 0.0)
    us10y_bps = round(us10y_abs * 100.0, 1)
    jpy_chg = round(float(usdjpy.get("change") or 0.0), 2)

    if xau_chg < 0 and ag_chg < 0:
        smt = "BEARISH_CONFIRMATION"
    elif xau_chg > 0 and ag_chg > 0:
        smt = "BULLISH_CONFIRMATION"
    elif xau_chg > 0 and ag_chg < 0:
        smt = "SMT_BULLISH_GOLD_LEAD"
    else:
        smt = "SMT_BEARISH_GOLD_LAG"

    return {
        "as_of": tv.get("timestamp", dt.datetime.now(dt.timezone.utc).isoformat()),
        "source": "TradingView Live",
        "xauusd_price": round(float(xau.get("close") or 0.0), 2),
        "xagusd_price": round(float(ag.get("close") or 0.0), 2),
        "dxy_price": round(float(dxy.get("close") or 0.0), 3),
        "us10y_yield_pct": round(float(us10y.get("close") or 0.0), 3),
        "usdjpy_price": round(float(usdjpy.get("close") or 0.0), 3),
        "xauusd_change_pct": xau_chg,
        "xagusd_change_pct": ag_chg,
        "dxy_change_pct": dxy_chg,
        "us10y_change_bps": us10y_bps,
        "usdjpy_change_pct": jpy_chg,
        "smt_divergence": smt,
    }


def analyze_correlations(
    data: Optional[Dict[str, Any]] = None,
    symbol: str = "XAUUSD",
    live: bool = False,
) -> Dict[str, Any]:
    if data is None and live:
        data = fetch_live_intermarket()
    d = data or DEFAULT_INTERMARKET
    xau = float(d.get("xauusd_change_pct", 0.50))
    xag = float(d.get("xagusd_change_pct", 0.65))
    dxy = float(d.get("dxy_change_pct", -0.25))
    us10y = float(d.get("us10y_change_bps", -4.5))
    usdjpy = float(d.get("usdjpy_change_pct", -0.30))

    score = 0
    drivers: List[str] = []

    if dxy < -0.10:
        score += 30
        drivers.append(f"DXY melemah ({dxy:+.2f}%) -> Bullish XAUUSD")
    elif dxy > 0.10:
        score -= 30
        drivers.append(f"DXY menguat ({dxy:+.2f}%) -> Bearish XAUUSD")

    if us10y < -2.0:
        score += 25
        drivers.append(f"Yield US10Y turun ({us10y:+.1f} bps) -> Bullish XAUUSD")
    elif us10y > 2.0:
        score -= 25
        drivers.append(f"Yield US10Y naik ({us10y:+.1f} bps) -> Bearish XAUUSD")

    if xag > 0.15 and xau > 0:
        score += 25
        drivers.append(f"Silver XAGUSD kompak naik ({xag:+.2f}%) -> Konfirmasi SMT Bullish")
    elif xag < -0.15 and xau < 0:
        score -= 25
        drivers.append(f"Silver XAGUSD kompak turun ({xag:+.2f}%) -> Konfirmasi SMT Bearish")

    if usdjpy < -0.10:
        score += 20
        drivers.append(f"USDJPY turun ({usdjpy:+.2f}%) -> Aliran Yen/Emas searah Bullish")
    elif usdjpy > 0.10:
        score -= 20
        drivers.append(f"USDJPY naik ({usdjpy:+.2f}%) -> Tekanan Bearish Emas")

    score = max(-100, min(100, score))
    if score >= 35:
        bias = "BULLISH_CONFLUENCE"
    elif score <= -35:
        bias = "BEARISH_CONFLUENCE"
    else:
        bias = "MIXED_NEUTRAL"

    return {
        "skill": "trader-correl",
        "symbol": symbol,
        "timestamp": d.get("as_of", dt.datetime.now(dt.timezone.utc).isoformat()),
        "correlation_score": score,
        "correlation_bias": bias,
        "smt_state": d.get("smt_divergence", "BULLISH_CONFIRMATION"),
        "benchmarks": {
            "xauusd_change_pct": xau,
            "xagusd_change_pct": xag,
            "dxy_change_pct": dxy,
            "us10y_change_bps": us10y,
            "usdjpy_change_pct": usdjpy,
        },
        "drivers": drivers,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="XAUUSD Intermarket Correlation & SMT Analyzer")
    parser.add_argument("--fixture", default=None, help="Optional JSON fixture")
    parser.add_argument("--output", default="trader/correl.json", help="Output JSON path")
    args = parser.parse_args(argv)

    data = json.loads(Path(args.fixture).read_text(encoding="utf-8")) if args.fixture and os.path.exists(args.fixture) else None
    res = analyze_correlations(data)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
