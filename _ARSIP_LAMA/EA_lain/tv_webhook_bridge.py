#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tv_webhook_bridge.py
====================
Bridge TradingView -> MetaTrader 5 untuk indikator
"OBV Signal Confluence [MarkitTick]".

Alur:
  TradingView alert (JSON) --webhook--> script ini --> file JSON di
  folder <Terminal MT5>\\MQL5\\Files\\OBV_Signals --> dibaca OBV_SignalEA.mq5

Pemakaian:
  python tv_webhook_bridge.py
  python tv_webhook_bridge.py --port 8899 --token RAHASIA123
  python tv_webhook_bridge.py --dir "D:\\MT5\\MQL5\\Files"

Folder tujuan otomatis dideteksi dari %APPDATA%\\MetaQuotes\\Terminal.
"""
import argparse
import glob
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

DEFAULT_PORT = 8899
DEFAULT_PATH = "/webhook"
SIGNAL_SUBDIR = "OBV_Signals"


def find_mt5_files_dirs():
    """Deteksi semua folder MQL5\\Files milik instalasi MT5 di %APPDATA%."""
    base = os.environ.get("APPDATA", "")
    pattern = os.path.join(base, "MetaQuotes", "Terminal", "*", "MQL5", "Files")
    found = []
    for d in glob.glob(pattern):
        if os.path.isdir(d):
            found.append(os.path.abspath(d))
    return found


class Bridge:
    def __init__(self, path, token, dirs):
        self.path = path
        self.token = token
        self.dirs = dirs


class Handler(BaseHTTPRequestHandler):
    bridge = None

    def log_message(self, fmt, *args):
        print("[%s] %s" % (time.strftime("%H:%M:%S"), fmt % args))

    def _send(self, code, msg):
        body = msg.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def do_GET(self):
        if urlparse(self.path).path == "/health":
            self._send(200, "ok")
        else:
            self._send(404, "not found")

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != self.bridge.path:
            self._send(404, "not found")
            return

        # --- cek token: query string ?token=... atau header X-Webhook-Token
        if self.bridge.token:
            qs = parse_qs(u.query)
            got = ""
            if "token" in qs and qs["token"]:
                got = qs["token"][0]
            elif "X-Webhook-Token" in self.headers:
                got = self.headers.get("X-Webhook-Token", "")
            if got != self.bridge.token:
                print("DITOLAK: token salah/kosong")
                self._send(403, "forbidden")
                return

        # --- baca body
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            n = 0
        body = self.rfile.read(n).decode("utf-8", errors="replace").strip()

        # hanya ASCII agar aman dibaca EA mode FILE_ANSI
        body = body.encode("ascii", errors="ignore").decode("ascii")

        if not (body.startswith("{") and body.endswith("}")):
            self._send(400, "payload harus JSON objek")
            return

        # --- inject field token ke payload agar bisa diverifikasi EA
        if self.bridge.token and '"token"' not in body:
            body = '{"token":"%s",%s' % (self.bridge.token, body[1:])

        try:
            json.loads(body)
        except ValueError as e:
            self._send(400, "JSON tidak valid: %s" % e)
            return

        # --- tulis ke setiap folder terminal (atomic: tmp lalu rename)
        stamp = time.strftime("%Y%m%d_%H%M%S") + "_%03d" % (int(time.time() * 1000) % 1000)
        written = 0
        for d in self.bridge.dirs:
            try:
                os.makedirs(d, exist_ok=True)
                tmp = os.path.join(d, "_tmp_%s.tmp" % stamp)
                dst = os.path.join(d, "sig_%s.json" % stamp)
                with open(tmp, "w", encoding="ascii", errors="ignore") as f:
                    f.write(body)
                os.replace(tmp, dst)
                written += 1
            except OSError as e:
                print("Gagal tulis ke %s : %s" % (d, e))

        print(">>> SINYAL MASUK -> %d folder | %s" % (written, body[:160]))
        self._send(200, "ok")


def main():
    ap = argparse.ArgumentParser(description="Bridge webhook TradingView -> MT5 Files")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help="port server (default %d)" % DEFAULT_PORT)
    ap.add_argument("--path", default=DEFAULT_PATH, help="path webhook (default %s)" % DEFAULT_PATH)
    ap.add_argument("--token", default="", help='token rahasia, mis. "RAHASIA123"')
    ap.add_argument("--dir", action="append", dest="dirs",
                    help="folder MQL5\\Files eksplisit (boleh dipakai berkali-kali); "
                         "kosongkan untuk auto-detect")
    args = ap.parse_args()

    dirs = [os.path.abspath(d) for d in (args.dirs or [])]
    auto = False
    if not dirs:
        dirs = find_mt5_files_dirs()
        auto = True

    if not dirs:
        print("TIDAK ADA folder MQL5\\Files terdeteksi.")
        print("Jalankan dengan --dir \"C:\\...\\MetaQuotes\\Terminal\\<id>\\MQL5\\Files\"")
        raise SystemExit(1)

    targets = [os.path.join(d, SIGNAL_SUBDIR) for d in dirs]

    print("=" * 60)
    print("OBV Webhook Bridge aktif")
    print("  Listen   : http://0.0.0.0:%d%s" % (args.port, args.path))
    print("  Token    : %s" % ("AKTIF (%s)" % ("*" * len(args.token)) if args.token else "NONAKTIF"))
    print("  Tujuan   :")
    for t in targets:
        print("             - %s" % t)
    if auto:
        print("  (folder auto-detect dari %%APPDATA%%)")
    print("=" * 60)

    Handler.bridge = Bridge(args.path, args.token, targets)

    srv = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nBridge dimatikan.")


if __name__ == "__main__":
    main()
