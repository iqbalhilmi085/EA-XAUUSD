#!/usr/bin/env python3
"""
deploy/vercel/setup_webhook.py
Point the Telegram bot to the Vercel deployment and register its commands.

Usage:
  python deploy/vercel/setup_webhook.py --url https://your-app.vercel.app
  python deploy/vercel/setup_webhook.py --url https://your-app.vercel.app --info
  python deploy/vercel/setup_webhook.py --delete

Token is read from --token or TELEGRAM_BOT_TOKEN.
Secret is read from --secret or TELEGRAM_WEBHOOK_SECRET (optional but recommended).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from typing import Any, Dict, Optional

COMMANDS = [
    ("push", "Push Kartu Sinyal Live (Scalping + Swing + Liquidity + Lookbook)"),
    ("logbook", "Lookbook History Harian (TP / BE+ / SL / Aktif)"),
    ("scalping", "Fokus Area Entry Scalping (M5/M15)"),
    ("swing", "Fokus Area Entry Swing (H1/H4)"),
    ("liquidity", "Fokus Area Entry Liquidity (Stop Hunt BSL/SSL)"),
    ("simulasi_sl", "Tes Notifikasi SL & Area Recovery"),
    ("validasi", "Hasil Backtest 5 Tahun (WR 100%)"),
    ("berita", "Analisis Berita XAU/USD (teks atau link)"),
    ("smc", "Order Block, FVG & Struktur BOS"),
    ("session", "Killzone Emas (London/NY/Asian)"),
    ("correl", "Korelasi XAGUSD, DXY, US10Y & USDJPY"),
    ("scan", "Scan setup XAUUSD Live TradingView"),
    ("plan", "Rencana Trade & Simulasi TimeMachine"),
    ("status", "Ringkasan status 15 skill"),
]


def call(token: str, method: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Set Telegram webhook for the Vercel bot")
    parser.add_argument("--url", default="", help="Deployment URL, e.g. https://xxx.vercel.app")
    parser.add_argument("--token", default=os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    parser.add_argument("--secret", default=os.environ.get("TELEGRAM_WEBHOOK_SECRET", ""))
    parser.add_argument("--info", action="store_true", help="Only print current webhook info")
    parser.add_argument("--delete", action="store_true", help="Delete the webhook")
    args = parser.parse_args(argv)

    token = args.token.strip()
    if not token:
        print("ERROR: set TELEGRAM_BOT_TOKEN or pass --token", file=sys.stderr)
        return 1

    if args.delete:
        print(json.dumps(call(token, "deleteWebhook"), indent=2))
        return 0

    if args.info:
        print(json.dumps(call(token, "getWebhookInfo"), indent=2))
        return 0

    if not args.url:
        print("ERROR: pass --url https://your-app.vercel.app", file=sys.stderr)
        return 1

    webhook_url = args.url.rstrip("/") + "/api/telegram"
    payload: Dict[str, Any] = {
        "url": webhook_url,
        "allowed_updates": ["message", "callback_query"],
        "drop_pending_updates": True,
    }
    if args.secret.strip():
        payload["secret_token"] = args.secret.strip()

    print("setWebhook ->", webhook_url)
    print(json.dumps(call(token, "setWebhook", payload), indent=2))

    print("setMyCommands")
    commands = [{"command": name, "description": desc} for name, desc in COMMANDS]
    print(json.dumps(call(token, "setMyCommands", {"commands": commands}), indent=2))

    print("getWebhookInfo")
    print(json.dumps(call(token, "getWebhookInfo"), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
