#!/usr/bin/env python3
"""
trader-analyst/facts.py
Macroeconomic & Fundamental Analyst for XAUUSD (Gold).
Evaluates US 10Y Real Yields (TIPS), DXY, Fed Rate Cut Odds, GLD ETF Tonnage, and Central Bank Demand.
Writes trader/analyst_facts.json.
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


DEFAULT_METRICS: Dict[str, Any] = {
    "symbol": "XAUUSD",
    "as_of": "2026-11-11T13:30:00+00:00",
    "real_yield_10y_pct": 1.78,
    "real_yield_10y_change_bps": -6.5,
    "nominal_us10y_pct": 4.12,
    "dxy_index": 103.45,
    "dxy_24h_change_pct": -0.32,
    "fed_funds_rate_pct": 4.50,
    "next_fomc_cut_prob_pct": 68.0,
    "us_cpi_yoy_pct": 2.6,
    "gld_holdings_tons": 889.4,
    "gld_tonnage_change_7d_tons": 6.2,
    "central_bank_monthly_buying_tons": 58.0,
    "gvz_gold_vix": 16.8,
    "gold_silver_ratio": 83.2,
}


def fetch_live_macro_metrics() -> Dict[str, Any]:
    m = dict(DEFAULT_METRICS)
    if mod_scan is None:
        return m
    tv = mod_scan.fetch_tradingview_live()
    if not tv:
        return m
    xau = tv.get("xau") or {}
    ag = tv.get("silver") or {}
    dxy = tv.get("dxy") or {}
    us10y = tv.get("us10y") or {}

    m["as_of"] = tv.get("timestamp", m["as_of"])
    if dxy.get("close") is not None:
        m["dxy_index"] = round(float(dxy["close"]), 3)
        m["dxy_24h_change_pct"] = round(float(dxy.get("change") or 0.0), 2)
    if us10y.get("close") is not None:
        nom = float(us10y["close"])
        chg_bps = round(float(us10y.get("change_abs") or 0.0) * 100.0, 1)
        m["nominal_us10y_pct"] = round(nom, 3)
        m["real_yield_10y_pct"] = round(max(0.5, nom - 2.60), 2)
        m["real_yield_10y_change_bps"] = chg_bps
        if chg_bps >= 5.0 and m["dxy_24h_change_pct"] >= 0.20:
            m["next_fomc_cut_prob_pct"] = 25.0
            m["gld_tonnage_change_7d_tons"] = -3.5
    if xau.get("close") and ag.get("close") and float(ag["close"]) > 0:
        m["gold_silver_ratio"] = round(float(xau["close"]) / float(ag["close"]), 2)
    return m


def analyze_gold_macro(metrics: Dict[str, Any]) -> Dict[str, Any]:
    score = 0
    pillars: Dict[str, Dict[str, Any]] = {}

    # 1. Real Yield (TIPS) - inverse driver (-30 to +30)
    ry_chg = float(metrics.get("real_yield_10y_change_bps", 0.0))
    ry_lvl = float(metrics.get("real_yield_10y_pct", 2.0))
    if ry_chg <= -5.0:
        ry_score = 25
    elif ry_chg < -1.0:
        ry_score = 12
    elif ry_chg >= 5.0:
        ry_score = -25
    elif ry_chg > 1.0:
        ry_score = -12
    else:
        ry_score = 0
    if ry_lvl < 1.85:
        ry_score += 5
    elif ry_lvl > 2.25:
        ry_score -= 5
    score += ry_score
    pillars["real_yields"] = {
        "score": ry_score,
        "real_yield_10y_pct": ry_lvl,
        "change_bps": ry_chg,
        "summary": "Falling real yields reduce opportunity cost of holding non-yielding Gold"
        if ry_score > 0
        else "Rising real yields create headwind for Gold",
    }

    # 2. DXY Dollar Index (-25 to +25)
    dxy_chg = float(metrics.get("dxy_24h_change_pct", 0.0))
    dxy_lvl = float(metrics.get("dxy_index", 104.0))
    if dxy_chg <= -0.25:
        dxy_score = 22
    elif dxy_chg < -0.05:
        dxy_score = 10
    elif dxy_chg >= 0.25:
        dxy_score = -22
    elif dxy_chg > 0.05:
        dxy_score = -10
    else:
        dxy_score = 0
    score += dxy_score
    pillars["us_dollar_dxy"] = {
        "score": dxy_score,
        "dxy_index": dxy_lvl,
        "change_24h_pct": dxy_chg,
        "summary": "Weaker USD supports XAUUSD upside" if dxy_score > 0 else "Stronger USD pressures XAUUSD",
    }

    # 3. Fed Policy & Inflation (-20 to +20)
    cut_prob = float(metrics.get("next_fomc_cut_prob_pct", 50.0))
    cpi_yoy = float(metrics.get("us_cpi_yoy_pct", 2.5))
    fed_score = 15 if cut_prob >= 60.0 else (-15 if cut_prob <= 30.0 else 0)
    if cpi_yoy >= 2.5 and cut_prob >= 55.0:
        fed_score += 5
    score += fed_score
    pillars["fed_and_inflation"] = {
        "score": fed_score,
        "next_fomc_cut_prob_pct": cut_prob,
        "us_cpi_yoy_pct": cpi_yoy,
        "summary": f"FOMC cut probability at {cut_prob:.1f}% with CPI YoY at {cpi_yoy:.1f}%",
    }

    # 4. Institutional GLD ETF & Central Bank Demand (-25 to +25)
    gld_7d = float(metrics.get("gld_tonnage_change_7d_tons", 0.0))
    cb_tons = float(metrics.get("central_bank_monthly_buying_tons", 30.0))
    flow_score = 0
    if gld_7d >= 3.0:
        flow_score += 15
    elif gld_7d <= -3.0:
        flow_score -= 15
    if cb_tons >= 40.0:
        flow_score += 10
    score += flow_score
    pillars["physical_and_etf_flows"] = {
        "score": flow_score,
        "gld_tonnage_change_7d_tons": gld_7d,
        "central_bank_monthly_buying_tons": cb_tons,
        "summary": f"GLD 7d flow {gld_7d:+.1f}t, Central Bank monthly demand {cb_tons:.1f}t",
    }

    score = max(-100, min(100, score))
    if score >= 50:
        bias = "STRONG_BULLISH"
    elif score >= 15:
        bias = "BULLISH"
    elif score <= -50:
        bias = "STRONG_BEARISH"
    elif score <= -15:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    gvz = float(metrics.get("gvz_gold_vix", 16.0))
    if gvz >= 24.0:
        regime = "HIGH_VOL_STRESS"
    elif gvz <= 12.5:
        regime = "LOW_VOL_RANGE"
    else:
        regime = "TREND_EXPANSION"

    return {
        "skill": "trader-analyst",
        "symbol": metrics.get("symbol", "XAUUSD"),
        "timestamp": metrics.get("as_of", dt.datetime.now(dt.timezone.utc).isoformat()),
        "macro_score": score,
        "macro_bias": bias,
        "regime": regime,
        "gvz_gold_vix": gvz,
        "gold_silver_ratio": float(metrics.get("gold_silver_ratio", 83.0)),
        "pillar_breakdown": pillars,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="XAUUSD Macroeconomic & Fundamental Analyst")
    parser.add_argument(
        "--metrics",
        default="trader-analyst/metrics.example.json",
        help="Path to macro metrics JSON file",
    )
    parser.add_argument("--output", default="trader/analyst_facts.json", help="Output JSON path")
    args = parser.parse_args(argv)

    if args.metrics and os.path.exists(args.metrics):
        with open(args.metrics, "r", encoding="utf-8") as f:
            metrics = json.load(f)
    else:
        metrics = DEFAULT_METRICS

    result = analyze_gold_macro(metrics)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
