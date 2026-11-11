#!/usr/bin/env python3
"""
xauusd_bot.py
Master Orchestrator for the 15 XAUUSD Trader-Skill Modules:
 1. trader-scanner     (scan.py)
 2. trader-news        (news.py)
 3. trader-analyst     (facts.py)
 4. trader-pelosi      (ptr.py)
 5. trader-entry       (entry.py)
 6. trader-exit        (exit.py)
 7. trader-timemachine (timemachine.py)
 8. trader-budget      (size.py)
 9. trader-risk        (check.py)
10. trader-alerts      (alerts.py)
11. trader-broker      (ticket.py)
12. trader-smc         (smc.py)       [NEW: Order Blocks, FVG & BOS]
13. trader-session     (session.py)   [NEW: London/NY Killzone Clock]
14. trader-correl      (correl.py)    [NEW: Silver/DXY/US10Y/USDJPY SMT]
15. trader-journal     (journal.py)   [NEW: Auto-Push Telegram & Journal]
"""

from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
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
    "trader-smc",
    "trader-session",
    "trader-correl",
    "trader-journal",
]:
    sys.path.insert(0, str(ROOT / folder))

import scan as mod_scan  # type: ignore
import news as mod_news  # type: ignore
import facts as mod_facts  # type: ignore
import ptr as mod_ptr  # type: ignore
import entry as mod_entry  # type: ignore
import exit as mod_exit  # type: ignore
import timemachine as mod_tm  # type: ignore
import size as mod_size  # type: ignore
import check as mod_check  # type: ignore
import alerts as mod_alerts  # type: ignore
import ticket as mod_ticket  # type: ignore
import smc as mod_smc  # type: ignore
import session as mod_session  # type: ignore
import correl as mod_correl  # type: ignore
import journal as mod_journal  # type: ignore


def run_full_pipeline(
    symbol: str = "XAUUSD",
    source: str = "tradingview",
    bars_file: Optional[str] = None,
    mode: str = "semi",
    confirm: str = "no",
    backend: str = "bridge",
    runs: int = 10000,
    state_dir: str = "trader",
    push_telegram: bool = False,
) -> Dict[str, Any]:
    out_dir = Path(state_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    is_live = bars_file is None and source in ("tradingview", "live", "auto")

    # 1. Scanner
    bars = mod_scan.load_bars(source=source, bars_file=bars_file, symbol=symbol)
    watchlist = mod_scan.scan_xauusd(bars=bars, symbol=symbol)
    (out_dir / "watchlist.json").write_text(json.dumps(watchlist, indent=2), encoding="utf-8")

    # 2 & 16. News + Indonesian XAU/USD News Analysis (.github/skills/xauusd-news-analysis/SKILL.md)
    news_res = mod_news.evaluate_news(mod_news.default_news_payload(), symbol=symbol, live=is_live)
    (out_dir / "news.json").write_text(json.dumps(news_res, indent=2), encoding="utf-8")

    # 3. Analyst
    macro_metrics = mod_facts.fetch_live_macro_metrics() if is_live else mod_facts.DEFAULT_METRICS
    analyst_res = mod_facts.analyze_gold_macro(macro_metrics)
    (out_dir / "analyst_facts.json").write_text(json.dumps(analyst_res, indent=2), encoding="utf-8")

    # 4. Pelosi / COT Smart Money
    sm_res = mod_ptr.analyze_smart_money(mod_ptr.default_cot_and_ptr_data())
    (out_dir / "smart_money.json").write_text(json.dumps(sm_res, indent=2), encoding="utf-8")

    # 12. SMC (Order Blocks, FVG & BOS)
    smc_res = mod_smc.analyze_smc(bars, symbol=symbol)
    (out_dir / "smc.json").write_text(json.dumps(smc_res, indent=2), encoding="utf-8")

    # 13. Session Killzone Clock
    session_res = mod_session.evaluate_session(symbol=symbol)
    (out_dir / "session.json").write_text(json.dumps(session_res, indent=2), encoding="utf-8")

    # 14. Intermarket Correlation & SMT
    correl_res = mod_correl.analyze_correlations(symbol=symbol, live=is_live)
    (out_dir / "correl.json").write_text(json.dumps(correl_res, indent=2), encoding="utf-8")

    # 5. Entry
    entry_res = mod_entry.evaluate_entry(
        watchlist=watchlist,
        analyst_facts=analyst_res,
        smart_money=sm_res,
    )
    (out_dir / "entry.json").write_text(json.dumps(entry_res, indent=2), encoding="utf-8")

    # 6. Exit Plan
    plan_res = mod_exit.build_exit_plan(entry_data=entry_res)
    (out_dir / "plan.json").write_text(json.dumps(plan_res, indent=2), encoding="utf-8")

    # 7. TimeMachine
    tm_res = mod_tm.simulate_trade_plan(plan=plan_res, runs=runs)
    (out_dir / "timemachine.json").write_text(json.dumps(tm_res, indent=2), encoding="utf-8")

    # 8. Budget / Position Sizing
    cfg_path = ROOT / "trader-budget" / "config.example.json"
    tgt_path = ROOT / "trader-budget" / "targets.example.json"
    config = json.loads(cfg_path.read_text(encoding="utf-8"))
    targets = json.loads(tgt_path.read_text(encoding="utf-8"))
    order_sized = mod_size.calculate_position_size(plan=plan_res, config=config, targets=targets)
    (out_dir / "order_sized.json").write_text(json.dumps(order_sized, indent=2), encoding="utf-8")

    # 9. Risk Gatekeeper
    risk_res = mod_check.run_risk_checks(
        order_sized=order_sized,
        config=config,
        targets=targets,
        news_data=news_res,
        timemachine_data=tm_res,
        spread_points=float(watchlist.get("spread_points", 14.0)),
    )
    (out_dir / "risk_check.json").write_text(json.dumps(risk_res, indent=2), encoding="utf-8")

    # 10. Alerts
    alert_cfg_path = ROOT / "trader-alerts" / "alerts.example.json"
    alert_cfg = json.loads(alert_cfg_path.read_text(encoding="utf-8"))
    alerts_res = mod_alerts.evaluate_alerts(
        alert_config=alert_cfg,
        watchlist=watchlist,
        entry_data=entry_res,
        risk_data=risk_res,
    )
    (out_dir / "alerts_triggered.json").write_text(json.dumps(alerts_res, indent=2), encoding="utf-8")

    # 11. Broker Ticket & Execution
    ticket_res = mod_ticket.execute_ticket(
        order=order_sized,
        risk_check=risk_res,
        timemachine=tm_res,
        mode=mode,
        confirm=confirm,
        backend=backend,
        bridge_path=str(out_dir / "xauusd_trader_bridge.json"),
        paper_ledger_path=str(out_dir / "paper_ledger.json"),
    )
    (out_dir / "ticket_status.json").write_text(json.dumps(ticket_res, indent=2), encoding="utf-8")

    # 15. Journal & Auto-Push to Telegram
    journal_entry = mod_journal.build_15skill_push_message(out_dir)
    if push_telegram:
        journal_entry = mod_journal.push_to_telegram_if_triggered(
            journal_entry,
            telegram_cfg_path=ROOT / "telegram.json",
            ledger_path=out_dir / "journal_ledger.json",
        )
    (out_dir / "journal_last.json").write_text(json.dumps(journal_entry, indent=2), encoding="utf-8")

    summary = {
        "symbol": symbol,
        "data_source": watchlist.get("data_source", "OANDA:XAUUSD"),
        "last_price": watchlist.get("last_price"),
        "skills_count": 15,
        "trend_bias": watchlist["trend_bias"],
        "news_status": news_res["status"],
        "xauusd_news_sentimen": (news_res.get("xauusd_news_analysis") or {}).get("sentimen", "NETRAL"),
        "macro_bias": analyst_res["macro_bias"],
        "smart_money_bias": sm_res["smart_money_bias"],
        "smc_structure": smc_res["structure_state"],
        "active_session": session_res["active_session"],
        "correlation_bias": correl_res["correlation_bias"],
        "entry_state": entry_res["state"],
        "direction": order_sized["direction"],
        "lots": order_sized["lots"],
        "entry_price": order_sized["entry_price"],
        "sl_price": order_sized["sl_price"],
        "tp_price": order_sized["tp_price"],
        "timemachine_ev_r": tm_res["expected_value_r"],
        "risk_verdict": risk_res["verdict"],
        "alerts_fired": alerts_res["triggered_count"],
        "execution_status": ticket_res["execution_status"],
        "ticket_id": ticket_res["ticket_id"],
        "pushed_to_telegram": journal_entry.get("pushed_to_telegram", False),
    }
    (out_dir / "pipeline_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return {
        "summary": summary,
        "ticket_preview": ticket_res["ticket_preview"],
        "push_message": journal_entry["push_message"],
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="XAUUSD 16-Skill End-to-End Trading Bot Orchestrator")
    parser.add_argument("--symbol", default="XAUUSD", help="Trading symbol (default: XAUUSD)")
    parser.add_argument("--source", choices=["tradingview", "fixture", "mt5"], default="tradingview", help="Bar feed source")
    parser.add_argument("--bars-file", default=None, help="Optional OHLCV bars JSON file")
    parser.add_argument("--mode", choices=["semi", "auto"], default="semi", help="Execution mode")
    parser.add_argument("--confirm", default="no", help="Confirmation for semi-auto ('yes' to execute)")
    parser.add_argument("--backend", choices=["bridge", "mt5", "paper"], default="bridge", help="Broker backend")
    parser.add_argument("--runs", type=int, default=10000, help="TimeMachine simulation runs")
    parser.add_argument("--push-telegram", action="store_true", help="Automatically push to Telegram if entry triggers")
    parser.add_argument("--json", action="store_true", help="Print JSON summary only")
    args = parser.parse_args(argv)

    res = run_full_pipeline(
        symbol=args.symbol,
        source=args.source,
        bars_file=args.bars_file,
        mode=args.mode,
        confirm=args.confirm,
        backend=args.backend,
        runs=args.runs,
        push_telegram=args.push_telegram,
    )
    if not args.json:
        print(res["ticket_preview"])
    print(json.dumps(res["summary"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
