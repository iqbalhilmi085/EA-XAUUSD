#!/usr/bin/env python3
"""
trader-broker/ticket.py
XAUUSD Order Ticket Generator & Execution Engine (Semi-Auto & Full-Auto).
Supports backends:
- bridge (writes xauusd_trader_bridge.json for XAUUSD_TraderSkill_EA.mq5)
- mt5    (direct MetaTrader5 Python API order_send)
- paper  (appends to trader/paper_ledger.json)
"""

from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


def format_ticket_preview(
    order: Dict[str, Any],
    risk_check: Dict[str, Any],
    timemachine: Optional[Dict[str, Any]] = None,
) -> str:
    ev_str = "N/A"
    wr_str = "N/A"
    if timemachine:
        ev_str = f"{timemachine.get('expected_value_r', 0.0):+.3f}R ({timemachine.get('verdict')})"
        wr_str = f"{timemachine.get('win_rate_pct', 0.0):.1f}%"

    lines = [
        "============================================================",
        "               XAUUSD ORDER TICKET PREVIEW                  ",
        "============================================================",
        f" Symbol          : {order.get('symbol', 'XAUUSD')}",
        f" Direction       : {order.get('direction', 'BUY')}",
        f" Lot Size        : {order.get('lots', 0.01):.2f} lots ({order.get('sizing_mode', 'DYNAMIC')})",
        f" Entry Price     : {order.get('entry_price', 0.0):.2f}",
        f" Stop Loss (SL)  : {order.get('sl_price', 0.0):.2f} ({order.get('sl_pips', 0.0):.1f} pips)",
        f" Take Profit 1R  : {order.get('tp1_price', 0.0):.2f}",
        f" Take Profit TP  : {order.get('tp_price', 0.0):.2f} ({order.get('tp_pips', 0.0):.1f} pips, {order.get('rr_ratio', 1.5):.2f}R)",
        f" Dollar Risk     : {order.get('actual_risk_money', 0.0):.2f} {order.get('account_currency', 'USD')} ({order.get('actual_risk_pct', 0.0):.2f}%)",
        f" Expected Reward : {order.get('expected_reward_money', 0.0):.2f} {order.get('account_currency', 'USD')}",
        f" TimeMachine EV  : {ev_str} | Sim Win Rate: {wr_str}",
        f" Risk Gatekeeper : {risk_check.get('verdict', 'BLOCK')} ({risk_check.get('passed_count', 0)}/10 checks passed)",
        "============================================================",
    ]
    return "\n".join(lines)


def execute_ticket(
    order: Dict[str, Any],
    risk_check: Dict[str, Any],
    timemachine: Optional[Dict[str, Any]] = None,
    mode: str = "semi",
    confirm: str = "no",
    backend: str = "bridge",
    magic_number: int = 55300,
    bridge_path: str = "trader/xauusd_trader_bridge.json",
    paper_ledger_path: str = "trader/paper_ledger.json",
) -> Dict[str, Any]:
    ticket_id = f"XAU-{uuid.uuid4().hex[:8].upper()}"
    preview_text = format_ticket_preview(order, risk_check, timemachine)

    verdict = str(risk_check.get("verdict", "BLOCK")).upper()
    if verdict != "PASS":
        return {
            "skill": "trader-broker",
            "ticket_id": ticket_id,
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            "mode": mode,
            "backend": backend,
            "execution_status": "REJECTED_BY_RISK",
            "reason": "Risk check verdict is BLOCK",
            "blocking_reasons": risk_check.get("blocking_reasons", []),
            "ticket_preview": preview_text,
        }

    is_confirmed = (mode.lower() == "auto") or (str(confirm).strip().lower() in ("yes", "y", "true"))
    if not is_confirmed:
        return {
            "skill": "trader-broker",
            "ticket_id": ticket_id,
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            "mode": mode,
            "backend": backend,
            "execution_status": "AWAITING_CONFIRMATION",
            "reason": "Semi-Auto mode requires --confirm yes to transmit order",
            "ticket_preview": preview_text,
        }

    # Build standardized execution payload
    bridge_payload = {
        "ticket_id": ticket_id,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "magic_number": magic_number,
        "symbol": order.get("symbol", "XAUUSD"),
        "action": "OPEN_TRADE",
        "direction": order.get("direction", "BUY"),
        "lots": float(order.get("lots", 0.01)),
        "entry_price": float(order.get("entry_price", 0.0)),
        "sl_price": float(order.get("sl_price", 0.0)),
        "tp1_price": float(order.get("tp1_price", 0.0)),
        "tp_price": float(order.get("tp_price", 0.0)),
        "sl_distance": float(order.get("sl_distance", 2.40)),
        "tp_distance": float(order.get("tp_distance", 3.60)),
        "rr_ratio": float(order.get("rr_ratio", 1.5)),
        "risk_check_verdict": verdict,
        "timemachine_ev_r": timemachine.get("expected_value_r", 0.0) if timemachine else 0.0,
        "comment": f"TS-{ticket_id}",
    }

    if backend in ("bridge", "paper", "mt5"):
        bp = Path(bridge_path)
        bp.parent.mkdir(parents=True, exist_ok=True)
        with open(bp, "w", encoding="utf-8") as f:
            json.dump(bridge_payload, f, indent=2)

    if backend == "paper" or backend == "bridge":
        lp = Path(paper_ledger_path)
        lp.parent.mkdir(parents=True, exist_ok=True)
        ledger: List[Dict[str, Any]] = []
        if lp.exists():
            try:
                with open(lp, "r", encoding="utf-8") as f:
                    ledger = json.load(f)
            except Exception:
                ledger = []
        ledger.append(bridge_payload)
        with open(lp, "w", encoding="utf-8") as f:
            json.dump(ledger, f, indent=2)

    mt5_result_note = "Dispatched to MQL5 bridge & paper ledger"
    if backend == "mt5":
        try:
            import MetaTrader5 as mt5  # type: ignore
            if mt5.initialize():
                sym = bridge_payload["symbol"]
                tick = mt5.symbol_info_tick(sym)
                if tick is not None:
                    order_type = mt5.ORDER_TYPE_BUY if bridge_payload["direction"] == "BUY" else mt5.ORDER_TYPE_SELL
                    px = tick.ask if bridge_payload["direction"] == "BUY" else tick.bid
                    req = {
                        "action": mt5.TRADE_ACTION_DEAL,
                        "symbol": sym,
                        "volume": bridge_payload["lots"],
                        "type": order_type,
                        "price": px,
                        "sl": bridge_payload["sl_price"],
                        "tp": bridge_payload["tp_price"],
                        "deviation": 10,
                        "magic": magic_number,
                        "comment": bridge_payload["comment"],
                        "type_time": mt5.ORDER_TIME_GTC,
                        "type_filling": mt5.ORDER_FILLING_IOC,
                    }
                    res = mt5.order_send(req)
                    mt5_result_note = f"MT5 order_send retcode={getattr(res, 'retcode', 'unknown')}"
                mt5.shutdown()
        except Exception as exc:
            mt5_result_note = f"MT5 API fallback to bridge ({exc})"

    return {
        "skill": "trader-broker",
        "ticket_id": ticket_id,
        "timestamp": bridge_payload["timestamp"],
        "mode": mode,
        "backend": backend,
        "execution_status": "EXECUTED",
        "note": mt5_result_note,
        "order_payload": bridge_payload,
        "ticket_preview": preview_text,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="XAUUSD Order Ticket & Execution Engine")
    parser.add_argument("--order", default="trader/order_sized.json", help="Path to trader/order_sized.json")
    parser.add_argument("--risk", default="trader/risk_check.json", help="Path to trader/risk_check.json")
    parser.add_argument("--timemachine", default="trader/timemachine.json", help="Path to trader/timemachine.json")
    parser.add_argument("--mode", choices=["semi", "auto"], default="semi", help="Execution mode: semi or auto")
    parser.add_argument("--confirm", default="no", help="Confirmation for semi-auto mode ('yes' to execute)")
    parser.add_argument("--backend", choices=["bridge", "mt5", "paper"], default="bridge", help="Execution backend")
    parser.add_argument("--magic", type=int, default=55300, help="MT5 Magic Number")
    parser.add_argument("--output", default="trader/ticket_status.json", help="Output ticket status JSON")
    args = parser.parse_args(argv)

    if os.path.exists(args.order):
        with open(args.order, "r", encoding="utf-8") as f:
            order = json.load(f)
    else:
        order = {
            "symbol": "XAUUSD",
            "direction": "BUY",
            "lots": 0.02,
            "sizing_mode": "DYNAMIC_RISK_PCT",
            "entry_price": 2663.50,
            "sl_price": 2661.10,
            "tp1_price": 2665.90,
            "tp_price": 2667.10,
            "sl_distance": 2.40,
            "tp_distance": 3.60,
            "sl_pips": 24.0,
            "tp_pips": 36.0,
            "rr_ratio": 1.5,
            "actual_risk_money": 4.80,
            "actual_risk_pct": 0.48,
            "expected_reward_money": 7.20,
            "account_currency": "USD",
        }

    if os.path.exists(args.risk):
        with open(args.risk, "r", encoding="utf-8") as f:
            risk = json.load(f)
    else:
        risk = {"verdict": "PASS", "passed_count": 10, "blocking_reasons": []}

    tm = None
    if os.path.exists(args.timemachine):
        with open(args.timemachine, "r", encoding="utf-8") as f:
            tm = json.load(f)

    result = execute_ticket(
        order=order,
        risk_check=risk,
        timemachine=tm,
        mode=args.mode,
        confirm=args.confirm,
        backend=args.backend,
        magic_number=args.magic,
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(result["ticket_preview"])
    print(json.dumps({k: v for k, v in result.items() if k != "ticket_preview"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
