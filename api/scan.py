#!/usr/bin/env python3
"""GET/POST /api/scan — run the 15-skill pipeline on demand.

Protect it with SCAN_SECRET:
  /api/scan?key=<SCAN_SECRET>&push=1

Use an external scheduler (e.g. cron-job.org, every 5 minutes) to call this
endpoint. That works around Vercel Hobby's once-per-day cron limit.

Query parameters:
  key   = SCAN_SECRET (required)
  push  = 1 to push a Telegram alert when a new valid signal appears
  runs  = Monte Carlo runs (default 1000, clamped to 100..5000)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.bootstrap import notify_signal, run_pipeline  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self._run()

    def do_POST(self) -> None:
        self._run()

    def _run(self) -> None:
        expected = os.environ.get("SCAN_SECRET", "").strip()
        if not expected:
            self._send(
                503,
                {
                    "ok": False,
                    "error": "SCAN_SECRET is not configured on this deployment",
                },
            )
            return

        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        provided = (query.get("key") or [self.headers.get("x-scan-key", "")])[0]
        if provided != expected:
            self._send(401, {"ok": False, "error": "invalid scan key"})
            return

        push = (query.get("push") or ["0"])[0].lower() in ("1", "true", "yes")
        try:
            runs = int((query.get("runs") or ["1000"])[0])
        except ValueError:
            runs = 1000
        runs = max(100, min(5000, runs))

        try:
            result = run_pipeline(runs=runs)
        except Exception as exc:
            self._send(502, {"ok": False, "error": f"pipeline failed: {exc}"})
            return

        notified = False
        if push:
            try:
                notified = notify_signal(result)
            except Exception:
                notified = False

        self._send(
            200,
            {
                "ok": True,
                "notified": notified,
                "summary": result.get("summary", {}),
            },
        )
