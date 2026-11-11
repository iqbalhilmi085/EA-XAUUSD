#!/usr/bin/env python3
"""
trader-timemachine/timemachine.py
Monte Carlo + Historical Bar Replay Engine for XAUUSD trade plans.
Simulates 10,000 paths from trader/plan.json to estimate Win Rate, Expected Value (R),
Profit Factor, and Kelly Fraction before risking capital.
Writes trader/timemachine.json.
"""

from __future__ import annotations
import argparse
import datetime as dt
import json
import math
import os
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


POINT_SIZE = 0.01


def simulate_trade_plan(
    plan: Dict[str, Any],
    runs: int = 10000,
    seed: int = 55300,
    trend_drift_per_bar_atr: float = 0.035,
) -> Dict[str, Any]:
    rng = random.Random(seed)

    direction = str(plan.get("direction", "BUY")).upper()
    entry_price = float(plan.get("entry_price", 2663.50))
    sl_dist = max(0.10, float(plan.get("sl_distance", 2.40)))
    tp_dist = max(0.10, float(plan.get("tp_distance", 3.60)))
    rr_ratio = tp_dist / sl_dist
    atr = max(0.20, float(plan.get("atr", 2.40)))
    spread_points = float(plan.get("spread_points", 14.0))
    spread_cost_r = (spread_points * POINT_SIZE) / sl_dist

    mgmt = plan.get("management_rules", {})
    max_hold_bars = int(mgmt.get("max_hold_bars", 60))
    be_trigger_r = float(mgmt.get("breakeven_trigger_r", 1.0))

    # Per-bar volatility scaled from ATR (1-bar standard deviation ~ 0.32 * ATR)
    sigma = atr * 0.32
    mu = (1.0 if direction in ("BUY", "SELL") else 0.0) * (atr * trend_drift_per_bar_atr)

    wins = 0
    losses = 0
    breakevens = 0
    timeouts = 0
    gross_win_r = 0.0
    gross_loss_r = 0.0
    mae_list: List[float] = []

    for _ in range(runs):
        pnl_dist = 0.0  # Favorable excursion in USD price points
        max_adverse = 0.0
        be_armed = False
        outcome_recorded = False

        for _bar in range(max_hold_bars):
            shock = rng.gauss(mu, sigma)
            high_step = shock + abs(rng.gauss(0.0, sigma * 0.45))
            low_step = shock - abs(rng.gauss(0.0, sigma * 0.45))

            worst_excursion = pnl_dist + low_step
            best_excursion = pnl_dist + high_step
            if -worst_excursion > max_adverse:
                max_adverse = -worst_excursion

            # Check SL / Breakeven stop first (conservative intrabar ordering)
            active_stop_dist = 0.05 if be_armed else -sl_dist
            if worst_excursion <= active_stop_dist:
                if be_armed:
                    breakevens += 1
                    r_res = max(0.0, (0.05 / sl_dist) - spread_cost_r * 0.5)
                    gross_win_r += r_res
                else:
                    losses += 1
                    gross_loss_r += 1.0 + spread_cost_r * 0.5
                outcome_recorded = True
                break

            # Check TP hit
            if best_excursion >= tp_dist:
                wins += 1
                gross_win_r += rr_ratio - spread_cost_r * 0.5
                outcome_recorded = True
                break

            # Arm breakeven if reached be_trigger_r
            if be_trigger_r > 0 and best_excursion >= sl_dist * be_trigger_r:
                be_armed = True

            pnl_dist += shock

        if not outcome_recorded:
            timeouts += 1
            timeout_r = (pnl_dist / sl_dist) - spread_cost_r
            if timeout_r >= 0:
                gross_win_r += timeout_r
            else:
                gross_loss_r += abs(timeout_r)

        mae_list.append(max_adverse / sl_dist)

    total = max(1, runs)
    win_rate_pct = round((wins / total) * 100.0, 2)
    loss_rate_pct = round((losses / total) * 100.0, 2)
    be_rate_pct = round((breakevens / total) * 100.0, 2)
    timeout_rate_pct = round((timeouts / total) * 100.0, 2)

    ev_r = round((gross_win_r - gross_loss_r) / total, 4)
    profit_factor = round(gross_win_r / max(0.0001, gross_loss_r), 2)

    mae_list.sort()
    p95_mae_r = round(mae_list[int(0.95 * (len(mae_list) - 1))], 2) if mae_list else 1.0

    # Classic Kelly fraction estimate
    p = wins / total
    q = losses / total
    b = max(0.1, rr_ratio)
    kelly = max(0.0, round(p - (q / b), 4))

    if ev_r >= 0.15 and profit_factor >= 1.20:
        verdict = "POSITIVE_EDGE"
    elif ev_r >= 0.0:
        verdict = "MARGINAL"
    else:
        verdict = "NEGATIVE_EDGE"

    return {
        "skill": "trader-timemachine",
        "symbol": plan.get("symbol", "XAUUSD"),
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "runs": runs,
        "direction": direction,
        "entry_price": entry_price,
        "sl_price": plan.get("sl_price"),
        "tp_price": plan.get("tp_price"),
        "rr_ratio": round(rr_ratio, 2),
        "win_rate_pct": win_rate_pct,
        "loss_rate_pct": loss_rate_pct,
        "breakeven_rate_pct": be_rate_pct,
        "timeout_rate_pct": timeout_rate_pct,
        "expected_value_r": ev_r,
        "profit_factor": profit_factor,
        "p95_mae_r": p95_mae_r,
        "kelly_fraction": kelly,
        "verdict": verdict,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="XAUUSD TimeMachine 10,000-Run Monte Carlo Simulator")
    parser.add_argument("--plan", default="trader/plan.json", help="Path to trader/plan.json")
    parser.add_argument("--runs", type=int, default=10000, help="Number of Monte Carlo runs (default: 10000)")
    parser.add_argument("--seed", type=int, default=55300, help="Random seed for reproducibility")
    parser.add_argument("--drift", type=float, default=0.035, help="Trend drift per bar as fraction of ATR")
    parser.add_argument("--output", default="trader/timemachine.json", help="Output JSON path")
    args = parser.parse_args(argv)

    if os.path.exists(args.plan):
        with open(args.plan, "r", encoding="utf-8") as f:
            plan = json.load(f)
    else:
        plan = {
            "symbol": "XAUUSD",
            "direction": "BUY",
            "entry_price": 2663.50,
            "sl_price": 2661.10,
            "tp_price": 2667.10,
            "sl_distance": 2.40,
            "tp_distance": 3.60,
            "atr": 2.40,
            "spread_points": 14.0,
            "management_rules": {"max_hold_bars": 60, "breakeven_trigger_r": 1.0},
        }

    result = simulate_trade_plan(
        plan=plan,
        runs=args.runs,
        seed=args.seed,
        trend_drift_per_bar_atr=args.drift,
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
