#!/usr/bin/env python3
"""
lib/bootstrap.py
Shared bootstrap for the Vercel serverless deployment.

Vercel functions run on a read-only filesystem (except /tmp) and have no
persistent process, so this module:
  - builds config from environment variables (no telegram.json needed)
  - keeps all state under /tmp/trader (per invocation / warm instance)
  - exposes the 15-skill pipeline, Telegram sender and webhook dispatcher
  - optionally de-duplicates alerts with Upstash Redis (free tier)

Nothing here is used by the local/desktop bot; it is only imported by api/*.py.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import telegram_bot  # noqa: E402
import xauusd_bot  # noqa: E402
import news as mod_news  # noqa: E402


def env(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default) or "").strip()


_DEFAULT_STATE = (
    "/tmp/trader"
    if os.name != "nt"
    else os.path.join(tempfile.gettempdir(), "xauusd-trader")
)
STATE_DIR = Path(env("STATE_DIR", _DEFAULT_STATE))
STATE_DIR.mkdir(parents=True, exist_ok=True)


def get_config() -> Dict[str, Any]:
    """Build the bot config from Vercel environment variables."""
    token = env("TELEGRAM_BOT_TOKEN")
    chat_id = env("TELEGRAM_CHAT_ID")
    allowed = [
        item.strip()
        for item in env("TELEGRAM_ALLOWED_CHAT_IDS").split(",")
        if item.strip()
    ]
    if chat_id and chat_id not in allowed:
        allowed.insert(0, chat_id)
    return {
        "bot_token": token,
        "chat_id": chat_id,
        "allowed_chat_ids": allowed,
        "symbol": env("SYMBOL", "XAUUSD"),
        "backend": env("BACKEND", "paper"),
        "default_mode": env("DEFAULT_MODE", "semi"),
    }


def run_pipeline(
    mode: Optional[str] = None,
    confirm: str = "no",
    runs: int = 1000,
) -> Dict[str, Any]:
    """Run the full 15-skill pipeline with serverless-safe state."""
    cfg = get_config()
    return xauusd_bot.run_full_pipeline(
        symbol=cfg["symbol"],
        mode=mode or cfg["default_mode"],
        confirm=confirm,
        backend=cfg["backend"],
        runs=runs,
        state_dir=str(STATE_DIR),
        push_telegram=False,
    )


def send_message(text: str, chat_id: Optional[str] = None) -> bool:
    cfg = get_config()
    target = (chat_id or cfg["chat_id"]).strip()
    if not cfg["bot_token"] or not target:
        return False
    try:
        telegram_bot.send_telegram_message(cfg["bot_token"], target, text)
        return True
    except Exception:
        return False


def signal_hash(summary: Dict[str, Any]) -> str:
    """Stable hash of a trade plan so cold starts do not re-push the same alert.

    Entry price is intentionally excluded: it moves on every scan. Direction and
    the SL/TP plan change only when the setup really changes.
    """
    def rounded(key: str) -> str:
        try:
            return f"{float(summary.get(key, 0)):.1f}"
        except (TypeError, ValueError):
            return str(summary.get(key, ""))

    parts = [
        str(summary.get("symbol", "")),
        str(summary.get("direction", "")),
        rounded("sl_price"),
        rounded("tp_price"),
    ]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]



def _file_lock_ok(key: str, ttl: int) -> bool:
    lock_dir = STATE_DIR / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    path = lock_dir / f"{key}.lock"
    now = time.time()
    if path.exists() and (now - path.stat().st_mtime) < ttl:
        return False
    path.write_text(str(now), encoding="utf-8")
    return True


def _upstash_lock_ok(key: str, ttl: int) -> Optional[bool]:
    base = env("UPSTASH_REDIS_REST_URL").rstrip("/")
    token = env("UPSTASH_REDIS_REST_TOKEN")
    if not base or not token:
        return None
    url = f"{base}/set/xau:{key}?NX&EX={ttl}"
    req = urllib.request.Request(
        url,
        data=b"1",
        method="POST",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode("utf-8") or "{}")
    return data.get("result") == "OK"


def acquire_alert_lock(key: str, ttl: int = 900) -> bool:
    """Return True only when this signal has not been alerted in the last ttl."""
    try:
        remote = _upstash_lock_ok(key, ttl)
        if remote is not None:
            return remote
    except Exception:
        pass
    try:
        return _file_lock_ok(key, ttl)
    except Exception:
        return True


def _summary_text(summary: Dict[str, Any]) -> str:
    return (
        f"XAUUSD {summary.get('entry_state', '-')} "
        f"{summary.get('direction', '-')} @ {summary.get('entry_price', '-')}\n"
        f"SL {summary.get('sl_price', '-')} | TP {summary.get('tp_price', '-')}\n"
        f"Risk: {summary.get('risk_verdict', '-')} | "
        f"EV: {summary.get('timemachine_ev_r', 0):+.3f}R"
    )


def notify_signal(res: Dict[str, Any], ttl: int = 900) -> bool:
    """Push a triggered signal once per signal hash."""
    summary = res.get("summary") or {}
    if str(summary.get("entry_state", "")).upper() != "TRIGGERED":
        return False
    if str(summary.get("risk_verdict", "")).upper() != "PASS":
        return False
    if not acquire_alert_lock(signal_hash(summary), ttl=ttl):
        return False
    return send_message(res.get("push_message") or _summary_text(summary))


def send_daily_report(res: Dict[str, Any]) -> bool:
    summary = res.get("summary") or {}
    text = (
        "LAPORAN HARIAN XAUUSD (Vercel)\n"
        f"Harga   : ${summary.get('last_price', 0):.2f} "
        f"({summary.get('data_source', '-')})\n"
        f"Tren    : {summary.get('trend_bias', '-')} | "
        f"Makro: {summary.get('macro_bias', '-')}\n"
        f"Berita  : {summary.get('news_status', '-')} "
        f"({summary.get('xauusd_news_sentimen', '-')})\n"
        f"SMC     : {summary.get('smc_structure', '-')} | "
        f"Sesi: {summary.get('active_session', '-')}\n"
        f"Korelasi: {summary.get('correlation_bias', '-')}\n"
        f"Sinyal  : {summary.get('entry_state', '-')} "
        f"{summary.get('direction', '-')} @ ${summary.get('entry_price', 0)}\n"
        f"Risk    : {summary.get('risk_verdict', '-')} | "
        f"EV: {summary.get('timemachine_ev_r', 0):+.3f}R\n\n"
        "Catatan: Vercel tidak terhubung ke MT5. Eksekusi tetap manual."
    )
    return send_message(text)


def _dispatch(
    text: str,
    symbol: str,
    backend: str,
    state_dir: str,
) -> str:
    """Route one Telegram command/text to the existing 15-skill handler."""
    cmd = text.strip().split(maxsplit=1)[0].lower() if text.strip() else "/help"
    if "@" in cmd:
        cmd = cmd.split("@")[0]

    if cmd in ("/confirm", "/auto"):
        return (
            "Eksekusi order TIDAK tersedia di Vercel.\n"
            "Vercel tidak punya MetaTrader 5 dan tidak bisa menulis file bridge.\n\n"
            "Gunakan sinyal ini untuk entry MANUAL di MT5 / HP, "
            "atau jalankan bot versi Windows untuk full-auto."
        )

    if text.strip().startswith("/"):
        return telegram_bot.handle_command(
            text,
            symbol=symbol,
            backend=backend,
            state_dir=state_dir,
        )

    lowered = text.lower()
    if len(text) > 12 or "t.me/" in lowered or "http" in lowered:
        try:
            result = mod_news.analyze_xauusd_news_indonesia(text)
            return str(result["formatted_output"])
        except Exception as exc:
            return f"Gagal menganalisis berita: {exc}"

    return telegram_bot.handle_command(
        "/help",
        symbol=symbol,
        backend=backend,
        state_dir=state_dir,
    )


def handle_update(update: Dict[str, Any]) -> Dict[str, Any]:
    """Handle one Telegram webhook update and reply to the sender."""
    cfg = get_config()
    token = cfg["bot_token"]
    allowed = set(cfg["allowed_chat_ids"])
    symbol = cfg["symbol"]
    backend = cfg["backend"]
    state_dir = str(STATE_DIR)

    callback = update.get("callback_query")
    if callback:
        callback_id = str(callback.get("id", ""))
        data = str(callback.get("data", "/push")).strip() or "/push"
        message = callback.get("message") or {}
        chat_id = str((message.get("chat") or {}).get("id", "")).strip()
        if callback_id:
            telegram_bot.answer_callback_query(
                token, callback_id, f"Memuat {data}..."
            )
        if not chat_id:
            return {"ok": True, "handled": "callback_without_chat"}
        if allowed and chat_id not in allowed:
            send_message("Akses ditolak: Chat ID Anda tidak terdaftar.", chat_id)
            return {"ok": True, "handled": "callback_denied"}
        reply = _dispatch(data, symbol, backend, state_dir)
        send_message(reply, chat_id)
        return {"ok": True, "handled": "callback"}

    message = update.get("message") or {}
    chat_id = str((message.get("chat") or {}).get("id", "")).strip()
    text = str(message.get("text", "")).strip()
    if not text or not chat_id:
        return {"ok": True, "handled": "ignored"}

    if not allowed:
        send_message(
            "Bot belum dikonfigurasi. Set TELEGRAM_CHAT_ID atau "
            "TELEGRAM_ALLOWED_CHAT_IDS di environment Vercel.",
            chat_id,
        )
        return {"ok": True, "handled": "not_configured"}

    if chat_id not in allowed:
        send_message("Akses ditolak: Chat ID Anda tidak terdaftar.", chat_id)
        return {"ok": True, "handled": "denied"}

    reply = _dispatch(text, symbol, backend, state_dir)
    send_message(reply, chat_id)
    return {"ok": True, "handled": "message"}
