#!/usr/bin/env python3
"""
trader-exit/exit.py
Pre-trade Exit Planner for XAUUSD.
Calculates SL (max of ATR*mult, 3x spread, broker stops level), TP (RR * SL),
1R breakeven trigger, ATR trailing stop rules, and time-based exit.
Writes trader/plan.json.
"""

from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


PIP_SIZE = 0.10
POINT_SIZE = 0.01


def build_exit_plan(
    entry_data: Dict[str, Any],
    atr_mult: float = 1.0,
    rr_target: float = 1.5,
    stops_level_points: int = 10,
    max_hold_bars: int = 60,
    be_trigger_r: float = 1.0,
    trail_atr_mult: float = 1.0,
) -> Dict[str, Any]:
    symbol = entry_data.get("symbol", "XAUUSD")
    direction = str(entry_data.get("direction", "NONE")).upper()
    if direction == "NONE":
        direction = str(entry_data.get("intended_direction", "BUY")).upper()

    entry_price = float(entry_data.get("entry_price", 2650.0))
    atr = max(0.20, float(entry_data.get("atr", 2.50)))
    spread_points = float(entry_data.get("spread_points", 15.0))
    spread_dist = spread_points * POINT_SIZE
    stops_dist = (stops_level_points + 1) * POINT_SIZE

    # Match Project5_Trend_v3 SL formula: max(atr_mult * ATR, 3 * spread, 1 pip, stops_level)
    sl_dist = max(atr_mult * atr, spread_dist * 3.0, PIP_SIZE, stops_dist)
    sl_dist = round(sl_dist, 2)
    tp_dist = round(max(sl_dist * rr_target, stops_dist), 2)
    tp1_dist = round(sl_dist * 1.0, 2)

    if direction == "BUY":
        sl_price = round(entry_price - sl_dist, 2)
        tp1_price = round(entry_price + tp1_dist, 2)
        tp_price = round(entry_price + tp_dist, 2)
        be_trigger_price = round(entry_price + sl_dist * be_trigger_r, 2)
        be_lock_price = round(entry_price + 0.05, 2)
    else:
        sl_price = round(entry_price + sl_dist, 2)
        tp1_price = round(entry_price - tp1_dist, 2)
        tp_price = round(entry_price - tp_dist, 2)
        be_trigger_price = round(entry_price - sl_dist * be_trigger_r, 2)
        be_lock_price = round(entry_price - 0.05, 2)

    rr_ratio = round(tp_dist / sl_dist, 2) if sl_dist > 0 else rr_target

    return {
        "skill": "trader-exit",
        "symbol": symbol,
        "timestamp": entry_data.get("timestamp", dt.datetime.now(dt.timezone.utc).isoformat()),
        "entry_state": entry_data.get("state", "TRIGGERED"),
        "setup_id": entry_data.get("setup_id", "XAU_DONCHIAN_BUY"),
        "setup_type": entry_data.get("setup_type", "DONCHIAN_TREND_BREAKOUT"),
        "direction": direction,
        "entry_price": entry_price,
        "sl_price": sl_price,
        "tp1_price": tp1_price,
        "tp_price": tp_price,
        "sl_distance": sl_dist,
        "tp_distance": tp_dist,
        "sl_pips": round(sl_dist / PIP_SIZE, 1),
        "tp_pips": round(tp_dist / PIP_SIZE, 1),
        "rr_ratio": rr_ratio,
        "atr": atr,
        "atr_mult": atr_mult,
        "spread_points": spread_points,
        "management_rules": {
            "breakeven_trigger_r": be_trigger_r,
            "breakeven_trigger_price": be_trigger_price,
            "breakeven_lock_price": be_lock_price,
            "trailing_atr_mult": trail_atr_mult,
            "max_hold_bars": max_hold_bars,
            "flatten_on_daily_lock": True,
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="XAUUSD Pre-Trade Exit Plan Builder")
    parser.add_argument("--entry", default="trader/entry.json", help="Path to trader/entry.json")
    parser.add_argument("--atr-mult", type=float, default=1.0, help="ATR multiplier for SL (default: 1.0)")
    parser.add_argument("--rr", type=float, default=1.5, help="Reward-to-Risk ratio for TP (default: 1.5)")
    parser.add_argument("--stops-level", type=int, default=10, help="Broker minimum stops level in points")
    parser.add_argument("--max-hold-bars", type=int, default=60, help="Time exit in bars")
    parser.add_argument("--output", default="trader/plan.json", help="Output plan JSON path")
    args = parser.parse_args(argv)

    if os.path.exists(args.entry):
        with open(args.entry, "r", encoding="utf-8") as f:
            entry_data = json.load(f)
    else:
        entry_data = {
            "symbol": "XAUUSD",
            "state": "TRIGGERED",
            "direction": "BUY",
            "entry_price": 2663.50,
            "atr": 2.40,
            "spread_points": 14.0,
        }

    result = build_exit_plan(
        entry_data=entry_data,
        atr_mult=args.atr_mult,
        rr_target=args.rr,
        stops_level_points=args.stops_level,
        max_hold_bars=args.max_hold_bars,
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
