#!/usr/bin/env python3
"""GET /api — health check for the Vercel deployment (no secrets exposed)."""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.bootstrap import get_config  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        cfg = get_config()
        self._send(
            200,
            {
                "ok": True,
                "service": "xauusd-15skill-vercel",
                "telegram_configured": bool(cfg["bot_token"] and cfg["chat_id"]),
                "symbol": cfg["symbol"],
                "backend": cfg["backend"],
                "mode": cfg["default_mode"],
                "endpoints": {
                    "telegram_webhook": "/api/telegram",
                    "scan": "/api/scan?key=<SCAN_SECRET>&push=1",
                    "cron": "/api/cron",
                },
                "note": "Vercel hanya untuk sinyal. Eksekusi order tetap manual (tidak ada MT5).",
            },
        )
