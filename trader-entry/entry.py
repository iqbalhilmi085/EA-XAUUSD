#!/usr/bin/env python3
"""
trader-entry/entry.py
Bar-by-bar XAUUSD Entry Timing Engine.
Reads trader/watchlist.json (or scans bars directly) and checks spread, candle close confirmation,
and optional macro/smart-money confluence. Writes trader/entry.json.
"""

from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Allow importing scanner utilities when needed
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "trader-scanner"))
import scan as scanner_mod  # type: ignore


def evaluate_entry(
    watchlist: Dict[str, Any],
    max_spread_points: float = 20.0,
    min_score: int = 70,
    analyst_facts: Optional[Dict[str, Any]] = None,
    smart_money: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    symbol = watchlist.get("symbol", "XAUUSD")
    spread_points = float(watchlist.get("spread_points", 15.0))
    atr = float(watchlist.get("atr", 2.50))
    last_price = float(watchlist.get("last_price", 2650.0))
    top_setup = watchlist.get("top_setup")

    reasons: List[str] = []
    spread_ok = spread_points <= max_spread_points
    if spread_ok:
        reasons.append(f"Spread OK ({spread_points:.1f} <= {max_spread_points:.1f} pts)")
    else:
        reasons.append(f"Spread TOO WIDE ({spread_points:.1f} > {max_spread_points:.1f} pts)")

    if not top_setup:
        return {
            "skill": "trader-entry",
            "symbol": symbol,
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            "state": "WAIT",
            "direction": "NONE",
            "entry_price": last_price,
            "atr": atr,
            "spread_points": spread_points,
            "confidence": 0,
            "reasons": ["No active setup in watchlist"],
        }

    direction = str(top_setup.get("direction", "NONE")).upper()
    setup_status = str(top_setup.get("status", "WATCHING")).upper()
    setup_score = int(top_setup.get("score", 50))
    trigger_price = float(top_setup.get("trigger_price", last_price))
    setup_type = str(top_setup.get("setup_type", "DONCHIAN_TREND_BREAKOUT"))

    # Check bar close breakout vs trigger_price
    if direction == "BUY":
        price_confirmed = last_price >= trigger_price and setup_status == "READY"
    elif direction == "SELL":
        price_confirmed = last_price <= trigger_price and setup_status == "READY"
    else:
        price_confirmed = False

    if price_confirmed:
        reasons.append(
            f"Bar close confirmed {direction} ({last_price:.2f} vs trigger {trigger_price:.2f}) [{setup_type}]"
        )
    else:
        reasons.append(
            f"Waiting for bar close beyond trigger {trigger_price:.2f} (current {last_price:.2f})"
        )

    confidence = setup_score
    if analyst_facts:
        macro_score = int(analyst_facts.get("macro_score", 0))
        if (direction == "BUY" and macro_score > 0) or (direction == "SELL" and macro_score < 0):
            confidence = min(99, confidence + 6)
            reasons.append(f"Macro analyst aligned ({analyst_facts.get('macro_bias')}, score {macro_score})")
        elif (direction == "BUY" and macro_score <= -30) or (direction == "SELL" and macro_score >= 30):
            confidence = max(10, confidence - 10)
            reasons.append(f"Macro headwind warning ({analyst_facts.get('macro_bias')})")

    if smart_money:
        sm_score = int(smart_money.get("smart_money_score", 0))
        if (direction == "BUY" and sm_score > 0) or (direction == "SELL" and sm_score < 0):
            confidence = min(99, confidence + 4)
            reasons.append(f"Smart money COT/PTR aligned ({smart_money.get('smart_money_bias')})")

    triggered = bool(spread_ok and price_confirmed and confidence >= min_score)

    return {
        "skill": "trader-entry",
        "symbol": symbol,
        "timestamp": watchlist.get("timestamp", dt.datetime.now(dt.timezone.utc).isoformat()),
        "state": "TRIGGERED" if triggered else "WAIT",
        "direction": direction if triggered else "NONE",
        "intended_direction": direction,
        "setup_id": top_setup.get("setup_id", "XAU_SETUP"),
        "setup_type": setup_type,
        "entry_price": round(last_price, 2),
        "trigger_price": round(trigger_price, 2),
        "invalid_price": float(top_setup.get("invalid_price", last_price)),
        "atr": round(atr, 2),
        "spread_points": spread_points,
        "confidence": confidence,
        "reasons": reasons,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="XAUUSD Entry Trigger Engine")
    parser.add_argument("--watchlist", default="trader/watchlist.json", help="Path to watchlist.json")
    parser.add_argument("--bars-file", default=None, help="Optional bars JSON file to scan on the fly")
    parser.add_argument("--analyst", default="trader/analyst_facts.json", help="Optional analyst_facts.json")
    parser.add_argument("--smart-money", default="trader/smart_money.json", help="Optional smart_money.json")
    parser.add_argument("--max-spread", type=float, default=20.0, help="Max allowed spread in points")
    parser.add_argument("--min-score", type=int, default=70, help="Minimum confidence score to trigger")
    parser.add_argument("--output", default="trader/entry.json", help="Output entry JSON path")
    args = parser.parse_args(argv)

    if args.bars_file or not os.path.exists(args.watchlist):
        bars = scanner_mod.load_bars(bars_file=args.bars_file)
        watchlist = scanner_mod.scan_xauusd(bars=bars)
    else:
        with open(args.watchlist, "r", encoding="utf-8") as f:
            watchlist = json.load(f)

    analyst_facts = None
    if args.analyst and os.path.exists(args.analyst):
        with open(args.analyst, "r", encoding="utf-8") as f:
            analyst_facts = json.load(f)

    smart_money = None
    if args.smart_money and os.path.exists(args.smart_money):
        with open(args.smart_money, "r", encoding="utf-8") as f:
            smart_money = json.load(f)

    result = evaluate_entry(
        watchlist=watchlist,
        max_spread_points=args.max_spread,
        min_score=args.min_score,
        analyst_facts=analyst_facts,
        smart_money=smart_money,
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
