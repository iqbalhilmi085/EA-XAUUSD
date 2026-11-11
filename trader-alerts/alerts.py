#!/usr/bin/env python3
"""
trader-alerts/alerts.py
XAUUSD Multi-Condition Alert Engine (Price levels, ATR spikes, Spread warnings, Entry triggers).
Writes trader/alerts_triggered.json.
"""

from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def evaluate_alerts(
    alert_config: Dict[str, Any],
    watchlist: Optional[Dict[str, Any]] = None,
    entry_data: Optional[Dict[str, Any]] = None,
    risk_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    symbol = alert_config.get("symbol", "XAUUSD")
    last_price = float(watchlist.get("last_price", 2663.50)) if watchlist else 2663.50
    atr = float(watchlist.get("atr", 2.40)) if watchlist else 2.40
    spread = float(watchlist.get("spread_points", 14.0)) if watchlist else 14.0

    triggered: List[Dict[str, Any]] = []
    for rule in alert_config.get("rules", []):
        r_type = str(rule.get("type", "")).upper()
        threshold = float(rule.get("threshold", 0.0))
        fired = False
        current_val: Any = None

        if r_type == "PRICE_ABOVE":
            current_val = last_price
            fired = last_price >= threshold
        elif r_type == "PRICE_BELOW":
            current_val = last_price
            fired = last_price <= threshold
        elif r_type == "ATR_SPIKE":
            current_val = atr
            fired = atr >= threshold
        elif r_type == "SPREAD_WIDENING":
            current_val = spread
            fired = spread > threshold
        elif r_type == "ENTRY_TRIGGERED" and entry_data:
            conf = float(entry_data.get("confidence", 0))
            current_val = conf
            fired = entry_data.get("state") == "TRIGGERED" and conf >= threshold
        elif r_type == "RISK_BLOCK" and risk_data:
            current_val = risk_data.get("verdict")
            fired = risk_data.get("verdict") == "BLOCK"

        if fired:
            triggered.append({
                "id": rule.get("id", r_type),
                "type": r_type,
                "threshold": threshold,
                "current_value": current_val,
                "message": rule.get("message", f"Alert {r_type} triggered"),
            })

    return {
        "skill": "trader-alerts",
        "symbol": symbol,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "last_price": last_price,
        "atr": atr,
        "spread_points": spread,
        "triggered_count": len(triggered),
        "triggered_alerts": triggered,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="XAUUSD Multi-Condition Alert Engine")
    parser.add_argument("--config", default="trader-alerts/alerts.example.json", help="Path to alerts config JSON")
    parser.add_argument("--watchlist", default="trader/watchlist.json", help="Path to watchlist.json")
    parser.add_argument("--entry", default="trader/entry.json", help="Path to entry.json")
    parser.add_argument("--risk", default="trader/risk_check.json", help="Path to risk_check.json")
    parser.add_argument("--output", default="trader/alerts_triggered.json", help="Output JSON path")
    args = parser.parse_args(argv)

    with open(args.config, "r", encoding="utf-8") as f:
        alert_config = json.load(f)

    watchlist = json.load(open(args.watchlist, "r", encoding="utf-8")) if os.path.exists(args.watchlist) else None
    entry_data = json.load(open(args.entry, "r", encoding="utf-8")) if os.path.exists(args.entry) else None
    risk_data = json.load(open(args.risk, "r", encoding="utf-8")) if os.path.exists(args.risk) else None

    result = evaluate_alerts(
        alert_config=alert_config,
        watchlist=watchlist,
        entry_data=entry_data,
        risk_data=risk_data,
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
