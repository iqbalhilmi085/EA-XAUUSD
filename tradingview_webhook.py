#!/usr/bin/env python3
"""
tradingview_webhook.py
Jembatan (Bridge) TradingView Alert JSON -> 11-Skill Pipeline -> Telegram Bot & MetaTrader 5 EA.

Fitur:
1. Menerima HTTP POST JSON dari indikator TradingView `XAUUSD_TraderSkill_Visual.pine` (default port 8899).
2. Memvalidasi sinyal terhadap 10 aturan `trader-risk` (news blackout, daily lock, R:R, TimeMachine EV).
3. Mengirimkan visualisasi Area Entry, Stop Loss, TP1 (1R), dan TP2 (1.5R) ke Telegram `@theailentxauusd_bot`.
4. Menulis tiket eksekusi ke `trader/xauusd_trader_bridge.json` DAN otomatis menyalinnya ke folder
   `%APPDATA%/MetaQuotes/Terminal/*/MQL5/Files/xauusd_trader_bridge.json` agar `XAUUSD_TraderSkill_EA.mq5`
   bisa langsung mengeksekusi di MT5.
"""

from __future__ import annotations
import argparse
import datetime as dt
import glob
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
for folder in [
    "trader-scanner",
    "trader-news",
    "trader-analyst",
    "trader-pelosi",
    "trader-entry",
    "trader-exit",
    "trader-timemachine",
    "trader-budget",
    "trader-risk",
    "trader-alerts",
    "trader-broker",
]:
    sys.path.insert(0, str(ROOT / folder))

import news as mod_news  # type: ignore
import timemachine as mod_tm  # type: ignore
import size as mod_size  # type: ignore
import check as mod_check  # type: ignore
import ticket as mod_ticket  # type: ignore
import telegram_bot  # type: ignore


def find_mt5_files_dirs() -> List[Path]:
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        return []
    pattern = os.path.join(appdata, "MetaQuotes", "Terminal", "*", "MQL5", "Files")
    return [Path(p) for p in glob.glob(pattern) if os.path.isdir(p)]


def format_visual_zones_message(payload: Dict[str, Any], ticket_res: Dict[str, Any]) -> str:
    direction = str(payload.get("direction", "BUY")).upper()
    entry = float(payload.get("entry_price", 2663.85))
    z_low = float(payload.get("entry_zone_low", round(entry - 0.30, 2)))
    z_high = float(payload.get("entry_zone_high", round(entry + 0.30, 2)))
    sl = float(payload.get("sl_price", 2661.85))
    tp1 = float(payload.get("tp1_price", 2665.85))
    tp2 = float(payload.get("tp_price", 2666.85))
    lots = float(payload.get("lots", 0.02))
    setup = str(payload.get("setup", "DONCHIAN_BREAKOUT"))
    score = int(payload.get("score", 85))

    sl_pips = abs(entry - sl) / 0.10
    tp1_pips = abs(tp1 - entry) / 0.10
    tp2_pips = abs(tp2 - entry) / 0.10

    if direction == "BUY":
        diagram = (
            f"  🎯 TP2 (1.5R)  : {tp2:.2f}  (+{tp2_pips:.1f} pips)\n"
            f"  ┃  ▓▓▓ ZONA TARGET PROFIT ▓▓▓\n"
            f"  🛡️ TP1 / BE(1R): {tp1:.2f}  (+{tp1_pips:.1f} pips)\n"
            f"  ┃\n"
            f"  🔵 AREA ENTRY  : {entry:.2f}  [Zona: {z_low:.2f} - {z_high:.2f}]\n"
            f"  ┃  ░░░ ZONA RISIKO SL ░░░\n"
            f"  🛑 STOP LOSS   : {sl:.2f}  (-{sl_pips:.1f} pips)"
        )
    else:
        diagram = (
            f"  🛑 STOP LOSS   : {sl:.2f}  (-{sl_pips:.1f} pips)\n"
            f"  ┃  ░░░ ZONA RISIKO SL ░░░\n"
            f"  🔵 AREA ENTRY  : {entry:.2f}  [Zona: {z_low:.2f} - {z_high:.2f}]\n"
            f"  ┃\n"
            f"  🛡️ TP1 / BE(1R): {tp1:.2f}  (+{tp1_pips:.1f} pips)\n"
            f"  ┃  ▓▓▓ ZONA TARGET PROFIT ▓▓▓\n"
            f"  🎯 TP2 (1.5R)  : {tp2:.2f}  (+{tp2_pips:.1f} pips)"
        )

    return (
        f"📡 [TRADINGVIEW -> 11-SKILL XAUUSD]\n"
        f"Setup : {setup} ({direction}) | Skor: {score}/100\n"
        f"Lot   : {lots:.2f} lot | Ticket: {ticket_res.get('ticket_id')}\n"
        f"Status: {ticket_res.get('execution_status')}\n"
        f"----------------------------------------\n"
        f"{diagram}\n"
        f"----------------------------------------\n"
        f"Ketik /confirm di Telegram jika mode Semi-Auto."
    )


def process_tradingview_signal(
    tv_payload: Dict[str, Any],
    expected_token: str = "RAHASIA123",
    mode: str = "semi",
    confirm: str = "no",
    send_tg: bool = True,
    state_dir: str = "trader",
) -> Dict[str, Any]:
    if expected_token and tv_payload.get("token") != expected_token:
        return {"ok": False, "error": "Invalid webhook token"}

    symbol = str(tv_payload.get("symbol", "XAUUSD"))
    direction = str(tv_payload.get("direction", "BUY")).upper()
    entry_price = float(tv_payload.get("entry_price", 2663.85))
    sl_price = float(tv_payload.get("sl_price", 2661.85))
    tp1_price = float(tv_payload.get("tp1_price", 2665.85))
    tp_price = float(tv_payload.get("tp_price", 2666.85))
    atr = float(tv_payload.get("atr", abs(entry_price - sl_price)))

    sl_dist = round(abs(entry_price - sl_price), 2)
    tp_dist = round(abs(tp_price - entry_price), 2)
    rr_ratio = round(tp_dist / max(0.10, sl_dist), 2)

    plan = {
        "symbol": symbol,
        "direction": direction,
        "entry_price": entry_price,
        "entry_zone_low": float(tv_payload.get("entry_zone_low", round(entry_price - atr * 0.15, 2))),
        "entry_zone_high": float(tv_payload.get("entry_zone_high", round(entry_price + atr * 0.15, 2))),
        "sl_price": sl_price,
        "tp1_price": tp1_price,
        "tp_price": tp_price,
        "sl_distance": sl_dist,
        "tp_distance": tp_dist,
        "sl_pips": round(sl_dist / 0.10, 1),
        "tp_pips": round(tp_dist / 0.10, 1),
        "rr_ratio": rr_ratio,
        "atr": atr,
        "spread_points": 14.0,
        "management_rules": {"max_hold_bars": 60, "breakeven_trigger_r": 1.0},
    }

    out_dir = Path(state_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")

    # Simulasi TimeMachine + Position Sizing + 10-Point Risk Check
    tm_res = mod_tm.simulate_trade_plan(plan, runs=2000)
    config = json.loads((ROOT / "trader-budget" / "config.example.json").read_text(encoding="utf-8"))
    targets = json.loads((ROOT / "trader-budget" / "targets.example.json").read_text(encoding="utf-8"))
    order_sized = mod_size.calculate_position_size(plan, config, targets)
    news_res = mod_news.evaluate_news(mod_news.default_news_payload(), symbol=symbol)
    risk_res = mod_check.run_risk_checks(
        order_sized=order_sized,
        config=config,
        targets=targets,
        news_data=news_res,
        timemachine_data=tm_res,
    )

    bridge_file = out_dir / "xauusd_trader_bridge.json"
    ticket_res = mod_ticket.execute_ticket(
        order=order_sized,
        risk_check=risk_res,
        timemachine=tm_res,
        mode=mode,
        confirm=confirm,
        backend="bridge",
        bridge_path=str(bridge_file),
        paper_ledger_path=str(out_dir / "paper_ledger.json"),
    )

    # Jika dieksekusi, salin juga ke semua folder MQL5/Files milik MT5
    if ticket_res.get("execution_status") == "EXECUTED" and bridge_file.exists():
        bridge_text = bridge_file.read_text(encoding="utf-8")
        for mt5_dir in find_mt5_files_dirs():
            try:
                (mt5_dir / "xauusd_trader_bridge.json").write_text(bridge_text, encoding="utf-8")
            except Exception:
                pass

    visual_msg = format_visual_zones_message(
        dict(tv_payload, lots=order_sized["lots"], entry_zone_low=plan["entry_zone_low"], entry_zone_high=plan["entry_zone_high"]),
        ticket_res,
    )

    if send_tg:
        try:
            tg_cfg = telegram_bot.load_telegram_config(str(ROOT / "telegram.json"))
            if tg_cfg.get("bot_token") and tg_cfg.get("chat_id"):
                telegram_bot.send_telegram_message(tg_cfg["bot_token"], tg_cfg["chat_id"], visual_msg)
        except Exception:
            pass

    return {
        "ok": True,
        "ticket_id": ticket_res["ticket_id"],
        "execution_status": ticket_res["execution_status"],
        "risk_verdict": risk_res["verdict"],
        "visual_message": visual_msg,
    }


class TVWebhookHandler(BaseHTTPRequestHandler):
    expected_token = "RAHASIA123"
    exec_mode = "semi"

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except Exception as exc:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(f"Invalid JSON: {exc}".encode("utf-8"))
            return

        res = process_tradingview_signal(
            payload,
            expected_token=self.expected_token,
            mode=self.exec_mode,
            confirm="yes" if self.exec_mode == "auto" else "no",
            send_tg=True,
        )
        code = 200 if res.get("ok") else 403
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(res).encode("utf-8"))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="TradingView -> 11-Skill -> Telegram & MT5 Webhook Server")
    parser.add_argument("--port", type=int, default=8899, help="HTTP port (default: 8899)")
    parser.add_argument("--token", default="RAHASIA123", help="Webhook secret token")
    parser.add_argument("--mode", choices=["semi", "auto"], default="semi", help="Execution mode (semi or auto)")
    parser.add_argument("--test-signal", action="store_true", help="Simulate a TradingView BUY webhook locally")
    args = parser.parse_args(argv)

    if args.test_signal:
        sample = {
            "token": args.token,
            "symbol": "XAUUSD",
            "direction": "BUY",
            "setup": "DONCHIAN_BUY",
            "score": 90,
            "entry_price": 2663.85,
            "entry_zone_low": 2663.55,
            "entry_zone_high": 2664.15,
            "sl_price": 2661.85,
            "tp1_price": 2665.85,
            "tp_price": 2666.85,
            "atr": 2.00,
        }
        res = process_tradingview_signal(sample, expected_token=args.token, mode=args.mode, send_tg=True)
        print(res["visual_message"])
        return 0

    TVWebhookHandler.expected_token = args.token
    TVWebhookHandler.exec_mode = args.mode
    server = ThreadingHTTPServer(("0.0.0.0", args.port), TVWebhookHandler)
    print(f"=== TradingView Webhook Bridge Aktif di http://127.0.0.1:{args.port}/webhook (Mode: {args.mode}) ===")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer dihentikan.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
