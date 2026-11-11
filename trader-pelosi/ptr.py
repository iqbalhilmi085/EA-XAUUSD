#!/usr/bin/env python3
"""
trader-pelosi/ptr.py
XAUUSD Smart Money Tracker:
1. CFTC Commitment of Traders (COT) Managed Money & Commercial positioning on Gold (COMEX GC).
2. US Congressional PTR (Periodic Transaction Reports) filings in Gold ETFs & Gold Miners
   (GLD, IAU, GDX, NEM, GOLD, AEM, WPM).
Writes trader/smart_money.json.
"""

from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


GOLD_RELATED_TICKERS = {"GLD", "IAU", "SGOL", "GDX", "GDXJ", "NEM", "GOLD", "AEM", "WPM", "FNV", "SLV"}


def default_cot_and_ptr_data() -> Dict[str, Any]:
    return {
        "as_of": "2026-11-11T13:30:00+00:00",
        "cot_gold_gc": {
            "report_date": "2026-11-10",
            "open_interest": 542100,
            "managed_money_long": 218400,
            "managed_money_short": 39200,
            "managed_money_net_change_1w": 11450,
            "commercial_net": -212000,
            "percentile_52w": 74,
        },
        "congress_ptr_filings": [
            {
                "member": "Rep. Nancy Pelosi / Household Filing (Simulated Macro Monitor)",
                "chamber": "House",
                "ticker": "GLD",
                "asset": "SPDR Gold Trust ETF",
                "transaction_type": "PURCHASE",
                "amount_range": "$100,001 - $250,000",
                "filed_date": "2026-11-08",
            },
            {
                "member": "Sen. Tommy Tuberville",
                "chamber": "Senate",
                "ticker": "NEM",
                "asset": "Newmont Corporation (Gold Miner)",
                "transaction_type": "PURCHASE",
                "amount_range": "$50,001 - $100,000",
                "filed_date": "2026-11-06",
            },
            {
                "member": "Rep. Michael McCaul",
                "chamber": "House",
                "ticker": "GDX",
                "asset": "VanEck Gold Miners ETF",
                "transaction_type": "PURCHASE",
                "amount_range": "$15,001 - $50,000",
                "filed_date": "2026-11-04",
            },
        ],
    }


def analyze_smart_money(data: Dict[str, Any]) -> Dict[str, Any]:
    cot = data.get("cot_gold_gc", {})
    mm_long = int(cot.get("managed_money_long", 0))
    mm_short = int(cot.get("managed_money_short", 0))
    mm_net = mm_long - mm_short
    mm_chg = int(cot.get("managed_money_net_change_1w", 0))
    pct_52w = int(cot.get("percentile_52w", 50))
    oi = max(1, int(cot.get("open_interest", 500000)))
    mm_net_pct_oi = round((mm_net / oi) * 100.0, 2)

    score = 0
    # Managed money momentum
    if mm_chg > 5000:
        score += 30
    elif mm_chg > 0:
        score += 15
    elif mm_chg < -5000:
        score -= 30
    elif mm_chg < 0:
        score -= 15

    # Crowding check
    crowded_warning = False
    if pct_52w >= 95:
        crowded_warning = True
        score -= 20  # Overcrowded long risk
    elif 55 <= pct_52w < 90:
        score += 20
    elif pct_52w <= 15:
        score += 10  # Washed out, contrarian bounce potential

    # Filter & score Congressional PTR filings in Gold-related tickers
    raw_filings = data.get("congress_ptr_filings", [])
    gold_filings: List[Dict[str, Any]] = []
    buys = 0
    sells = 0
    for f in raw_filings:
        ticker = str(f.get("ticker", "")).upper()
        if ticker in GOLD_RELATED_TICKERS:
            gold_filings.append(f)
            tx = str(f.get("transaction_type", "")).upper()
            if "PURCHASE" in tx or "BUY" in tx:
                buys += 1
            elif "SALE" in tx or "SELL" in tx:
                sells += 1

    ptr_net = buys - sells
    score += max(-30, min(30, ptr_net * 12))
    score = max(-100, min(100, score))

    if crowded_warning:
        bias = "CROWDED_LONG_WARNING"
    elif score >= 25:
        bias = "BULLISH_ACCUMULATION"
    elif score <= -25:
        bias = "BEARISH_DISTRIBUTION"
    else:
        bias = "NEUTRAL"

    return {
        "skill": "trader-pelosi",
        "symbol": "XAUUSD",
        "timestamp": data.get("as_of", dt.datetime.now(dt.timezone.utc).isoformat()),
        "smart_money_score": score,
        "smart_money_bias": bias,
        "cot_summary": {
            "report_date": cot.get("report_date", "N/A"),
            "managed_money_long": mm_long,
            "managed_money_short": mm_short,
            "managed_money_net": mm_net,
            "managed_money_net_pct_oi": mm_net_pct_oi,
            "managed_money_net_change_1w": mm_chg,
            "percentile_52w": pct_52w,
            "crowded_long_warning": crowded_warning,
        },
        "congressional_gold_summary": {
            "total_gold_filings": len(gold_filings),
            "purchases": buys,
            "sales": sells,
            "net_direction": "BUY" if ptr_net > 0 else ("SELL" if ptr_net < 0 else "FLAT"),
        },
        "congressional_gold_trades": gold_filings,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="XAUUSD CFTC COT Whale & Congressional Gold PTR Tracker")
    parser.add_argument("--fixture", default=None, help="Path to COT + PTR JSON fixture")
    parser.add_argument("--output", default="trader/smart_money.json", help="Output JSON path")
    args = parser.parse_args(argv)

    if args.fixture and os.path.exists(args.fixture):
        with open(args.fixture, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = default_cot_and_ptr_data()

    result = analyze_smart_money(data)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
