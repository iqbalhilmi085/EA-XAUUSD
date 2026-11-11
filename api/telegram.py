#!/usr/bin/env python3
"""POST /api/telegram — Telegram webhook handler for Vercel.

Set the webhook once with:
  python deploy/vercel/setup_webhook.py --url https://<project>.vercel.app

Optional but recommended: set TELEGRAM_WEBHOOK_SECRET so only Telegram can
call this endpoint.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.bootstrap import get_config, handle_update  # noqa: E402


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
                "service": "xauusd-telegram-webhook",
                "configured": bool(cfg["bot_token"] and cfg["chat_id"]),
            },
        )

    def do_POST(self) -> None:
        secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()
        if secret:
            provided = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if provided != secret:
                self._send(401, {"ok": False, "error": "invalid webhook secret"})
                return

        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            update = json.loads(raw.decode("utf-8") or "{}")
        except Exception as exc:
            self._send(400, {"ok": False, "error": f"invalid json: {exc}"})
            return

        try:
            result = handle_update(update)
        except Exception as exc:
            # Always return 200 so Telegram does not retry a permanently
            # failing update (e.g. upstream data source outage).
            self._send(200, {"ok": False, "error": str(exc)})
            return

        self._send(200, result)
