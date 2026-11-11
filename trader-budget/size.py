#!/usr/bin/env python3
"""
trader-budget/size.py
XAUUSD Position Sizing & Compounding Budget Calculator.
Computes exact MT5 lot size from equity, risk_per_trade_pct, and SL distance.
Supports Standard (USD) and Cent (USC) accounts.
Writes trader/order_sized.json.
"""

from __future__ import annotations
import argparse
import datetime as dt
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def clamp_lot(raw_lot: float, min_lot: float = 0.01, max_lot: float = 10.0, lot_step: float = 0.01) -> float:
    if raw_lot <= min_lot:
        return min_lot
    steps = math.floor((raw_lot + 1e-9) / lot_step)
    clamped = steps * lot_step
    return round(min(max_lot, max(min_lot, clamped)), 2)


def calculate_position_size(
    plan: Dict[str, Any],
    config: Dict[str, Any],
    targets: Dict[str, Any],
) -> Dict[str, Any]:
    equity = float(config.get("account_equity", 1000.0))
    day_start_equity = float(config.get("day_start_equity", equity))
    account_ccy = str(config.get("account_currency", "USD")).upper()
    risk_pct = float(config.get("risk_per_trade_pct", 0.5))
    fixed_lot = float(config.get("fixed_lot_override", 0.0))
    contract_size = float(config.get("contract_size_oz", 100.0))
    min_lot = float(config.get("min_lot", 0.01))
    max_lot = float(config.get("max_lot", 10.0))
    lot_step = float(config.get("lot_step", 0.01))

    sl_dist = max(0.10, float(plan.get("sl_distance", 2.40)))
    tp_dist = max(0.10, float(plan.get("tp_distance", 3.60)))

    # Value of $1.00 move in XAUUSD for 1.00 lot = contract_size ($100 for standard 100 oz)
    money_per_usd_move_per_lot = contract_size
    sl_loss_per_1_lot = sl_dist * money_per_usd_move_per_lot

    target_risk_money = equity * (risk_pct / 100.0)

    if fixed_lot > 0.0:
        lots = clamp_lot(fixed_lot, min_lot, max_lot, lot_step)
        sizing_mode = "FIXED_LOT"
    else:
        raw_lot = target_risk_money / max(0.01, sl_loss_per_1_lot)
        lots = clamp_lot(raw_lot, min_lot, max_lot, lot_step)
        sizing_mode = "DYNAMIC_RISK_PCT"

    actual_risk_money = round(lots * sl_loss_per_1_lot, 2)
    actual_risk_pct = round((actual_risk_money / max(0.01, equity)) * 100.0, 3)
    expected_reward_money = round(lots * tp_dist * money_per_usd_move_per_lot, 2)

    daily_pnl_money = round(equity - day_start_equity, 2)
    daily_pnl_pct = round((daily_pnl_money / max(0.01, day_start_equity)) * 100.0, 2)
    daily_profit_cap = round(day_start_equity * (float(targets.get("daily_profit_lock_pct", 2.0)) / 100.0), 2)
    daily_loss_cap = round(day_start_equity * (float(targets.get("daily_max_loss_pct", 2.0)) / 100.0), 2)

    return {
        "skill": "trader-budget",
        "symbol": plan.get("symbol", "XAUUSD"),
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "account_currency": account_ccy,
        "account_equity": equity,
        "day_start_equity": day_start_equity,
        "sizing_mode": sizing_mode,
        "lots": lots,
        "direction": plan.get("direction", "BUY"),
        "entry_price": plan.get("entry_price"),
        "sl_price": plan.get("sl_price"),
        "tp1_price": plan.get("tp1_price"),
        "tp_price": plan.get("tp_price"),
        "sl_distance": sl_dist,
        "tp_distance": tp_dist,
        "sl_pips": plan.get("sl_pips"),
        "tp_pips": plan.get("tp_pips"),
        "rr_ratio": plan.get("rr_ratio"),
        "target_risk_pct": risk_pct,
        "target_risk_money": round(target_risk_money, 2),
        "actual_risk_money": actual_risk_money,
        "actual_risk_pct": actual_risk_pct,
        "expected_reward_money": expected_reward_money,
        "daily_budget_status": {
            "daily_pnl_money": daily_pnl_money,
            "daily_pnl_pct": daily_pnl_pct,
            "daily_profit_cap_money": daily_profit_cap,
            "daily_loss_cap_money": daily_loss_cap,
            "remaining_loss_buffer_money": round(daily_loss_cap + daily_pnl_money, 2),
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="XAUUSD Position Sizing & Budget Calculator")
    parser.add_argument("--plan", default="trader/plan.json", help="Path to trader/plan.json")
    parser.add_argument(
        "--config",
        default="trader-budget/config.example.json",
        help="Path to account budget config JSON",
    )
    parser.add_argument(
        "--targets",
        default="trader-budget/targets.example.json",
        help="Path to targets config JSON",
    )
    parser.add_argument("--output", default="trader/order_sized.json", help="Output JSON path")
    args = parser.parse_args(argv)

    with open(args.config, "r", encoding="utf-8") as f:
        config = json.load(f)
    with open(args.targets, "r", encoding="utf-8") as f:
        targets = json.load(f)

    if os.path.exists(args.plan):
        with open(args.plan, "r", encoding="utf-8") as f:
            plan = json.load(f)
    else:
        plan = {
            "symbol": "XAUUSD",
            "direction": "BUY",
            "entry_price": 2663.50,
            "sl_price": 2661.10,
            "tp1_price": 2665.90,
            "tp_price": 2667.10,
            "sl_distance": 2.40,
            "tp_distance": 3.60,
            "sl_pips": 24.0,
            "tp_pips": 36.0,
            "rr_ratio": 1.5,
        }

    result = calculate_position_size(plan=plan, config=config, targets=targets)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
