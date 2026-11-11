#!/usr/bin/env python3
"""
trader-risk/check.py
XAUUSD 10-Point Pre-Trade Risk Gatekeeper.
Evaluates daily loss/profit locks, global drawdown kill-switch, post-SL cooldown,
max trades/day, per-trade risk ceiling, R:R ratio, spread, news blackout, and TimeMachine EV.
Returns PASS or BLOCK and writes trader/risk_check.json.
"""

from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def run_risk_checks(
    order_sized: Dict[str, Any],
    config: Dict[str, Any],
    targets: Dict[str, Any],
    news_data: Optional[Dict[str, Any]] = None,
    timemachine_data: Optional[Dict[str, Any]] = None,
    entries_today: int = 0,
    minutes_since_last_sl: float = 999.0,
    spread_points: float = 14.0,
    max_spread_points: float = 20.0,
    min_rr_ratio: float = 1.2,
) -> Dict[str, Any]:
    equity = float(order_sized.get("account_equity", config.get("account_equity", 1000.0)))
    day_start_equity = float(order_sized.get("day_start_equity", config.get("day_start_equity", equity)))
    peak_equity = max(equity, float(config.get("peak_equity", equity)))

    global_kill_dd_pct = float(targets.get("global_kill_drawdown_pct", 25.0))
    daily_profit_lock_pct = float(targets.get("daily_profit_lock_pct", 2.0))
    daily_max_loss_pct = float(targets.get("daily_max_loss_pct", 2.0))
    max_entries = int(targets.get("max_entries_per_day", 10))
    cooldown_min = int(targets.get("cooldown_minutes_after_sl", 5))
    max_risk_per_trade_pct = float(config.get("max_risk_per_trade_pct", 1.0))

    actual_risk_pct = float(order_sized.get("actual_risk_pct", 0.5))
    rr_ratio = float(order_sized.get("rr_ratio", 1.5))

    current_dd_pct = round(((peak_equity - equity) / max(0.01, peak_equity)) * 100.0, 2)
    daily_pnl_pct = round(((equity - day_start_equity) / max(0.01, day_start_equity)) * 100.0, 2)

    news_allowed = True
    news_status = "SAFE"
    if news_data:
        news_allowed = bool(news_data.get("trade_allowed", True))
        news_status = str(news_data.get("status", "SAFE"))

    tm_ev = 0.25
    tm_verdict = "POSITIVE_EDGE"
    if timemachine_data:
        tm_ev = float(timemachine_data.get("expected_value_r", 0.0))
        tm_verdict = str(timemachine_data.get("verdict", "POSITIVE_EDGE"))

    checks: List[Dict[str, Any]] = [
        {
            "rule": "global_kill_dd_check",
            "passed": current_dd_pct < global_kill_dd_pct,
            "detail": f"Drawdown from peak {current_dd_pct:.2f}% < kill limit {global_kill_dd_pct:.2f}%",
        },
        {
            "rule": "daily_loss_lock_check",
            "passed": daily_pnl_pct > -daily_max_loss_pct,
            "detail": f"Daily PnL {daily_pnl_pct:+.2f}% > max loss lock -{daily_max_loss_pct:.2f}%",
        },
        {
            "rule": "daily_profit_lock_check",
            "passed": daily_pnl_pct < daily_profit_lock_pct,
            "detail": f"Daily PnL {daily_pnl_pct:+.2f}% < profit lock +{daily_profit_lock_pct:.2f}%",
        },
        {
            "rule": "max_entries_per_day_check",
            "passed": entries_today < max_entries,
            "detail": f"Entries today {entries_today}/{max_entries}",
        },
        {
            "rule": "post_sl_cooldown_check",
            "passed": minutes_since_last_sl >= cooldown_min,
            "detail": f"Minutes since last SL {minutes_since_last_sl:.1f}m >= cooldown {cooldown_min}m",
        },
        {
            "rule": "max_risk_per_trade_check",
            "passed": actual_risk_pct <= max_risk_per_trade_pct,
            "detail": f"Trade risk {actual_risk_pct:.2f}% <= max {max_risk_per_trade_pct:.2f}%",
        },
        {
            "rule": "min_rr_check",
            "passed": rr_ratio >= min_rr_ratio,
            "detail": f"R:R {rr_ratio:.2f} >= min {min_rr_ratio:.2f}",
        },
        {
            "rule": "spread_ceiling_check",
            "passed": spread_points <= max_spread_points,
            "detail": f"Spread {spread_points:.1f} pts <= max {max_spread_points:.1f} pts",
        },
        {
            "rule": "news_blackout_check",
            "passed": news_allowed,
            "detail": f"News status is {news_status} (trade_allowed={news_allowed})",
        },
        {
            "rule": "timemachine_edge_check",
            "passed": tm_verdict != "NEGATIVE_EDGE" and tm_ev >= 0.0,
            "detail": f"TimeMachine EV={tm_ev:+.3f}R ({tm_verdict})",
        },
    ]

    failed = [c for c in checks if not c["passed"]]
    verdict = "PASS" if len(failed) == 0 else "BLOCK"

    return {
        "skill": "trader-risk",
        "symbol": order_sized.get("symbol", "XAUUSD"),
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "verdict": verdict,
        "passed_count": len(checks) - len(failed),
        "failed_count": len(failed),
        "blocking_reasons": [c["detail"] for c in failed],
        "checks": checks,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="XAUUSD 10-Point Risk Check Gatekeeper")
    parser.add_argument("--order", default="trader/order_sized.json", help="Path to trader/order_sized.json")
    parser.add_argument("--config", default="trader-budget/config.example.json", help="Path to budget config JSON")
    parser.add_argument("--targets", default="trader-budget/targets.example.json", help="Path to targets JSON")
    parser.add_argument("--news", default="trader/news.json", help="Path to trader/news.json")
    parser.add_argument("--timemachine", default="trader/timemachine.json", help="Path to trader/timemachine.json")
    parser.add_argument("--entries-today", type=int, default=0, help="Entries already taken today")
    parser.add_argument("--minutes-since-sl", type=float, default=999.0, help="Minutes elapsed since last SL hit")
    parser.add_argument("--spread-points", type=float, default=14.0, help="Current spread in points")
    parser.add_argument("--max-spread", type=float, default=20.0, help="Max allowed spread in points")
    parser.add_argument("--min-rr", type=float, default=1.2, help="Min allowed R:R ratio")
    parser.add_argument("--output", default="trader/risk_check.json", help="Output JSON path")
    args = parser.parse_args(argv)

    with open(args.config, "r", encoding="utf-8") as f:
        config = json.load(f)
    with open(args.targets, "r", encoding="utf-8") as f:
        targets = json.load(f)

    if os.path.exists(args.order):
        with open(args.order, "r", encoding="utf-8") as f:
            order_sized = json.load(f)
    else:
        order_sized = {
            "symbol": "XAUUSD",
            "account_equity": config.get("account_equity", 1000.0),
            "day_start_equity": config.get("day_start_equity", 1000.0),
            "actual_risk_pct": 0.5,
            "rr_ratio": 1.5,
        }

    news_data = None
    if os.path.exists(args.news):
        with open(args.news, "r", encoding="utf-8") as f:
            news_data = json.load(f)

    tm_data = None
    if os.path.exists(args.timemachine):
        with open(args.timemachine, "r", encoding="utf-8") as f:
            tm_data = json.load(f)

    result = run_risk_checks(
        order_sized=order_sized,
        config=config,
        targets=targets,
        news_data=news_data,
        timemachine_data=tm_data,
        entries_today=args.entries_today,
        minutes_since_last_sl=args.minutes_since_sl,
        spread_points=args.spread_points,
        max_spread_points=args.max_spread,
        min_rr_ratio=args.min_rr,
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
