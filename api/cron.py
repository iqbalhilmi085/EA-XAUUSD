#!/usr/bin/env python3
"""GET /api/cron — daily report triggered by Vercel Cron.

vercel.json schedules this once per day (Hobby limit). If CRON_SECRET is set,
Vercel sends it automatically as `Authorization: Bearer <CRON_SECRET>`.

The endpoint:
  - pushes a fresh triggered signal once (de-duplicated), or
  - sends a daily summary when there is no new signal.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.bootstrap import (  # noqa: E402
    notify_signal,
    run_pipeline,
    send_daily_report,
)


class handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        secret = os.environ.get("CRON_SECRET", "").strip()
        if secret:
            expected = f"Bearer {secret}"
            if self.headers.get("Authorization", "") != expected:
                self._send(401, {"ok": False, "error": "invalid cron secret"})
                return

        try:
            result = run_pipeline()
        except Exception as exc:
            self._send(502, {"ok": False, "error": f"pipeline failed: {exc}"})
            return

        notified = False
        report_sent = False
        try:
            notified = notify_signal(result)
            if not notified:
                report_sent = send_daily_report(result)
        except Exception:
            pass

        self._send(
            200,
            {
                "ok": True,
                "notified": notified,
                "daily_report_sent": report_sent,
                "summary": result.get("summary", {}),
            },
        )
