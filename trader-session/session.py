#!/usr/bin/env python3
"""
trader-session/session.py
Institutional Gold Killzone & Liquidity Session Analyzer for XAUUSD.
Writes trader/session.json.
"""

from __future__ import annotations
import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def evaluate_session(now_utc: Optional[dt.datetime] = None, symbol: str = "XAUUSD") -> Dict[str, Any]:
    if now_utc is None:
        now_utc = dt.datetime.now(dt.timezone.utc)

    hr = now_utc.hour
    mn = now_utc.minute

    if 7 <= hr < 11:
        session_name = "LONDON_OPEN_KILLZONE"
        quality_score = 92
        wr100_allowed = True
        note = "High European bullion liquidity; watch Asian High/Low breakout"
    elif 12 <= hr < 17:
        session_name = "NY_OPEN_OVERLAP_KILLZONE"
        quality_score = 98
        wr100_allowed = True
        note = "Peak London-NY Overlap & COMEX volume; highest breakout follow-through"
    elif 0 <= hr < 7:
        session_name = "ASIAN_ACCUMULATION"
        quality_score = 75
        wr100_allowed = True
        note = "Asian session accumulation; only take strong marubozu breakouts"
    elif 11 <= hr < 12 or 17 <= hr < 20:
        session_name = "INTRADAY_CONTINUATION"
        quality_score = 82
        wr100_allowed = True
        note = "Active intraday session before NY close"
    else:
        session_name = "ROLLOVER_DANGER_ZONE"
        quality_score = 20
        wr100_allowed = False
        note = "NY Close / Server Rollover (>=20:00 UTC) - blocked by WR 100% Precision Mode"

    lbma_fix_proximity = (hr == 10 and 15 <= mn <= 45) or (hr == 15 and 0 <= mn <= 20)

    return {
        "skill": "trader-session",
        "symbol": symbol,
        "timestamp": now_utc.isoformat(),
        "utc_hour": hr,
        "active_session": session_name,
        "liquidity_quality_score": quality_score,
        "wr100_session_allowed": wr100_allowed,
        "lbma_fixing_window": lbma_fix_proximity,
        "note": note,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="XAUUSD Institutional Killzone & Session Clock")
    parser.add_argument("--symbol", default="XAUUSD", help="Symbol")
    parser.add_argument("--now", default=None, help="Optional UTC ISO timestamp")
    parser.add_argument("--output", default="trader/session.json", help="Output JSON path")
    args = parser.parse_args(argv)

    now_utc = dt.datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else None
    res = evaluate_session(now_utc=now_utc, symbol=args.symbol)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
