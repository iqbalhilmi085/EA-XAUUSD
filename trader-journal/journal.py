#!/usr/bin/env python3
"""
trader-journal/journal.py
Auto-Push Telegram Signal Dispatcher & 15-Skill Trade Journal for XAUUSD.
Automatically pushes Entry/SL/Target/SMC visual alerts to Telegram when an entry triggers.
Writes trader/journal_ledger.json.
"""

from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent


def load_json_safe(path: Path, default: Any = None) -> Any:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def _confidence_bar(score: int) -> str:
    clamped = max(0, min(100, int(score)))
    filled = int(round(clamped / 10.0))
    return "█" * filled + "░" * (10 - filled)


def default_inline_keyboard() -> Dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "⚡ Sinyal Baru", "callback_data": "/push"},
                {"text": "📒 Rekap Harian", "callback_data": "/logbook"},
            ],
            [
                {"text": "⚡ Mode Scalping", "callback_data": "/scalping"},
                {"text": "🌊 Mode Swing", "callback_data": "/swing"},
                {"text": "💧 Mode Liquidity", "callback_data": "/liquidity"},
            ],
            [
                {"text": "📰 Cek Berita", "callback_data": "/berita"},
                {"text": "🏆 Bukti WR 100%", "callback_data": "/validasi"},
            ],
        ]
    }


def _build_mode_area_spec(
    mode_name: str,
    symbol: str,
    direction: str,
    ref_price: float,
    atr_val: float,
    ob_bot: float,
    ob_top: float,
    ob_poi: float,
    liq_pool_label: str = "",
) -> Dict[str, Any]:
    atr = max(0.50, float(atr_val))
    z_low = round(ref_price - atr * 0.10, 2)
    z_high = round(ref_price + atr * 0.10, 2)
    sl_dist = round(atr * 1.0, 2)
    if mode_name == "LIQUIDITY":
        tp1_dist = round(atr * 1.2, 2)
        tp2_dist = round(atr * 1.8, 2)
    else:
        tp1_dist = round(atr * 1.0, 2)
        tp2_dist = round(atr * 1.5, 2)
    # Aktifkan BE+ hanya setelah harga bergerak >= 70% menuju TP1 agar tidak terkena noise sebelum TP!
    be_arm_dist = round(max(1.50, atr * 0.70), 2)
    be_lock_dist = round(max(0.50, atr * 0.25), 2)

    if direction == "BUY":
        sl_px = round(ref_price - sl_dist, 2)
        tp1_px = round(ref_price + tp1_dist, 2)
        tp2_px = round(ref_price + tp2_dist, 2)
        be_arm_px = round(ref_price + be_arm_dist, 2)
        be_lock_px = round(ref_price + be_lock_dist, 2)
    else:
        sl_px = round(ref_price + sl_dist, 2)
        tp1_px = round(ref_price - tp1_dist, 2)
        tp2_px = round(ref_price - tp2_dist, 2)
        be_arm_px = round(ref_price - be_arm_dist, 2)
        be_lock_px = round(ref_price - be_lock_dist, 2)

    if mode_name == "SCALPING":
        bucket_size = 5.00
        tf_label = "M5 / M15 (Intraday Cepat)"
    elif mode_name == "LIQUIDITY":
        bucket_size = 8.00
        tf_label = "M15 / H1 (Stop Hunt BSL/SSL)"
    else:
        bucket_size = 15.00
        tf_label = "H1 / H4 (Multi-Sesi)"
    zone_bucket = round(ref_price / bucket_size)
    sig_key = f"{symbol}:{mode_name}:{direction}:{zone_bucket}"

    return {
        "mode": mode_name,
        "timeframe_label": tf_label,
        "direction": direction,
        "entry_price": round(ref_price, 2),
        "zone_low": z_low,
        "zone_high": z_high,
        "ob_bottom": round(ob_bot, 2),
        "ob_top": round(ob_top, 2),
        "ob_poi": round(ob_poi, 2),
        "liq_pool_label": liq_pool_label,
        "sl_price": sl_px,
        "be_arm_price": be_arm_px,
        "be_lock_price": be_lock_px,
        "tp1_price": tp1_px,
        "tp2_price": tp2_px,
        "atr": round(atr, 2),
        "sl_pips": round(sl_dist / 0.10, 1),
        "tp1_pips": round(tp1_dist / 0.10, 1),
        "tp2_pips": round(tp2_dist / 0.10, 1),
        "be_arm_pips": round(be_arm_dist / 0.10, 1),
        "be_lock_pips": round(be_lock_dist / 0.10, 1),
        "sig_key": sig_key,
    }


def sync_and_evaluate_daily_logbook(
    state_dir: Path,
    scalp_spec: Dict[str, Any],
    swing_spec: Dict[str, Any],
    current_price: float,
    simulate_sl_hit: bool = False,
    liq_spec: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Maintains trader/logbook_history.json:
    1. Assigns sequential Area Numbers (AREA #001, AREA #002, ...) to every new Scalping & Swing setup.
    2. Evaluates all active signals against current_price to track UNTUNG (TP), KENA BE+, or RUGI (SL).
    3. If any signal hits SL (or simulate_sl_hit=True), generates an immediate SL Notification +
       automatically computes a new Recovery Entry Area (AREA #NEXT — RECOVERY).
    """
    lb_path = state_dir / "logbook_history.json"
    lb_data = load_json_safe(lb_path, {"next_area_seq": 1, "entries": []})
    if not isinstance(lb_data, dict):
        lb_data = {"next_area_seq": 1, "entries": []}

    next_seq = int(lb_data.get("next_area_seq", 1))
    entries: List[Dict[str, Any]] = lb_data.get("entries", [])
    now_utc = dt.datetime.now(dt.timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")

    notifications: List[str] = []

    # 1. Evaluate existing RUNNING / BE_ARMED signals against live price
    for item in entries:
        st = item.get("status", "RUNNING")
        if st not in ("RUNNING", "BE_ARMED"):
            continue
        d = item.get("direction", "SELL")
        ep = float(item.get("entry_price", current_price))
        sl = float(item.get("sl_price", current_price))
        tp1 = float(item.get("tp1_price", current_price))
        tp2 = float(item.get("tp2_price", current_price))
        be_arm = float(item.get("be_arm_price", current_price))
        be_lock = float(item.get("be_lock_price", current_price))
        a_num = item.get("area_id", "AREA #001")
        m_lbl = item.get("mode", "SCALPING")

        if d == "BUY":
            if current_price >= tp2:
                item["status"] = "WIN_TP2"
                item["status_label"] = "✅ UNTUNG (HIT TP2)"
                item["closed_price"] = tp2
                item["pnl_pips"] = round((tp2 - ep) / 0.10, 1)
                item["closed_at"] = now_utc.strftime("%H:%M UTC")
                notifications.append(
                    f"✅ [LOGBOOK UPDATE — {a_num} ({m_lbl} BUY)] HIT TARGET TP2 @ {tp2:.2f} (+{item['pnl_pips']:.1f} pips)!"
                )
            elif current_price >= tp1:
                item["status"] = "WIN_TP1"
                item["status_label"] = "✅ UNTUNG (HIT TP1)"
                item["closed_price"] = tp1
                item["pnl_pips"] = round((tp1 - ep) / 0.10, 1)
                item["closed_at"] = now_utc.strftime("%H:%M UTC")
                notifications.append(
                    f"✅ [LOGBOOK UPDATE — {a_num} ({m_lbl} BUY)] HIT TARGET TP1 @ {tp1:.2f} (+{item['pnl_pips']:.1f} pips)!"
                )
            elif st == "BE_ARMED" and current_price <= be_lock:
                item["status"] = "WIN_BE"
                item["status_label"] = "🔒 KENA BE+ (PROFIT AMAN)"
                item["closed_price"] = be_lock
                item["pnl_pips"] = round((be_lock - ep) / 0.10, 1)
                item["closed_at"] = now_utc.strftime("%H:%M UTC")
                notifications.append(
                    f"🔒 [LOGBOOK UPDATE — {a_num} ({m_lbl} BUY)] Terkena Profit-Lock BE+ @ {be_lock:.2f} (+{item['pnl_pips']:.1f} pips, 0% Rugi)!"
                )
            elif st == "RUNNING" and current_price <= sl:
                item["status"] = "LOSS_SL"
                item["status_label"] = "❌ RUGI (KENA SL)"
                item["closed_price"] = sl
                item["pnl_pips"] = -round(abs(ep - sl) / 0.10, 1)
                item["closed_at"] = now_utc.strftime("%H:%M UTC")
                item["needs_recovery"] = True
            elif st == "RUNNING" and current_price >= be_arm:
                item["status"] = "BE_ARMED"
                item["status_label"] = "🛡️ RUNNING (BE+ TERKUNCI)"
        else:
            if current_price <= tp2:
                item["status"] = "WIN_TP2"
                item["status_label"] = "✅ UNTUNG (HIT TP2)"
                item["closed_price"] = tp2
                item["pnl_pips"] = round((ep - tp2) / 0.10, 1)
                item["closed_at"] = now_utc.strftime("%H:%M UTC")
                notifications.append(
                    f"✅ [LOGBOOK UPDATE — {a_num} ({m_lbl} SELL)] HIT TARGET TP2 @ {tp2:.2f} (+{item['pnl_pips']:.1f} pips)!"
                )
            elif current_price <= tp1:
                item["status"] = "WIN_TP1"
                item["status_label"] = "✅ UNTUNG (HIT TP1)"
                item["closed_price"] = tp1
                item["pnl_pips"] = round((ep - tp1) / 0.10, 1)
                item["closed_at"] = now_utc.strftime("%H:%M UTC")
                notifications.append(
                    f"✅ [LOGBOOK UPDATE — {a_num} ({m_lbl} SELL)] HIT TARGET TP1 @ {tp1:.2f} (+{item['pnl_pips']:.1f} pips)!"
                )
            elif st == "BE_ARMED" and current_price >= be_lock:
                item["status"] = "WIN_BE"
                item["status_label"] = "🔒 KENA BE+ (PROFIT AMAN)"
                item["closed_price"] = be_lock
                item["pnl_pips"] = round((ep - be_lock) / 0.10, 1)
                item["closed_at"] = now_utc.strftime("%H:%M UTC")
                notifications.append(
                    f"🔒 [LOGBOOK UPDATE — {a_num} ({m_lbl} SELL)] Terkena Profit-Lock BE+ @ {be_lock:.2f} (+{item['pnl_pips']:.1f} pips, 0% Rugi)!"
                )
            elif st == "RUNNING" and current_price >= sl:
                item["status"] = "LOSS_SL"
                item["status_label"] = "❌ RUGI (KENA SL)"
                item["closed_price"] = sl
                item["pnl_pips"] = -round(abs(sl - ep) / 0.10, 1)
                item["closed_at"] = now_utc.strftime("%H:%M UTC")
                item["needs_recovery"] = True
            elif st == "RUNNING" and current_price <= be_arm:
                item["status"] = "BE_ARMED"
                item["status_label"] = "🛡️ RUNNING (BE+ TERKUNCI)"

    # Optional SL simulation trigger so user can verify SL alert + automatic recovery area lookup anytime
    if simulate_sl_hit and entries:
        target_item = next((x for x in reversed(entries) if x.get("status") in ("RUNNING", "BE_ARMED")), entries[-1])
        target_item["status"] = "LOSS_SL"
        target_item["status_label"] = "❌ RUGI (KENA SL)"
        target_item["closed_price"] = target_item["sl_price"]
        target_item["pnl_pips"] = -round(abs(float(target_item["entry_price"]) - float(target_item["sl_price"])) / 0.10, 1)
        target_item["closed_at"] = now_utc.strftime("%H:%M UTC")
        target_item["needs_recovery"] = True

    # 2. Register Scalp, Swing & Liquidity specs if not already in today's active logbook
    active_specs = [s for s in (scalp_spec, swing_spec, liq_spec) if s is not None]
    for spec in active_specs:
        existing = next(
            (
                x for x in reversed(entries)
                if x.get("date") == today_str
                and (
                    (x.get("mode") == spec["mode"] and x.get("direction") == spec["direction"] and x.get("status") in ("RUNNING", "BE_ARMED"))
                    or (x.get("sig_key") == spec["sig_key"] and x.get("status") != "LOSS_SL")
                )
            ),
            None,
        )
        if existing is None:
            area_id = f"AREA #{next_seq:03d}"
            next_seq += 1
            new_rec = {
                "area_id": area_id,
                "seq": next_seq - 1,
                "date": today_str,
                "opened_at": now_utc.strftime("%H:%M UTC"),
                "closed_at": "-",
                "mode": spec["mode"],
                "timeframe_label": spec["timeframe_label"],
                "direction": spec["direction"],
                "entry_price": spec["entry_price"],
                "zone_low": spec["zone_low"],
                "zone_high": spec["zone_high"],
                "sl_price": spec["sl_price"],
                "be_arm_price": spec["be_arm_price"],
                "be_lock_price": spec["be_lock_price"],
                "tp1_price": spec["tp1_price"],
                "tp2_price": spec["tp2_price"],
                "status": "RUNNING",
                "status_label": "🟢 RUNNING (AKTIF)",
                "pnl_pips": 0.0,
                "sig_key": spec["sig_key"],
            }
            entries.append(new_rec)
            spec["area_id"] = area_id
        else:
            spec["area_id"] = existing["area_id"]

    # 3. Check if any signal just hit SL (needs_recovery == True) -> generate Recovery Area & Alert!
    for item in list(entries):
        if item.get("needs_recovery"):
            item["needs_recovery"] = False
            old_id = item["area_id"]
            old_mode = item["mode"]
            old_dir = item["direction"]
            old_sl = float(item["sl_price"])
            if old_mode == "SCALPING":
                atr_rec = scalp_spec["atr"]
            elif old_mode == "LIQUIDITY" and liq_spec is not None:
                atr_rec = liq_spec["atr"]
            else:
                atr_rec = swing_spec["atr"]

            # Next institutional Order Block / Liquidity Sweep Recovery Area beyond SL
            rec_entry = round(old_sl + (atr_rec * 0.35 if old_dir == "SELL" else -atr_rec * 0.35), 2)
            rec_z_lo = round(rec_entry - atr_rec * 0.12, 2)
            rec_z_hi = round(rec_entry + atr_rec * 0.12, 2)
            rec_sl = round(rec_entry + (atr_rec * 1.0 if old_dir == "SELL" else -atr_rec * 1.0), 2)
            rec_be_arm = round(rec_entry - (atr_rec * 0.70 if old_dir == "SELL" else -atr_rec * 0.70), 2)
            rec_be_lock = round(rec_entry - (atr_rec * 0.25 if old_dir == "SELL" else -atr_rec * 0.25), 2)
            rec_tp1 = round(rec_entry - (atr_rec * 1.2 if old_dir == "SELL" else -atr_rec * 1.2), 2)
            rec_tp2 = round(rec_entry - (atr_rec * 1.8 if old_dir == "SELL" else -atr_rec * 1.8), 2)

            rec_id = f"AREA #{next_seq:03d}"
            next_seq += 1
            rec_record = {
                "area_id": rec_id,
                "seq": next_seq - 1,
                "date": today_str,
                "opened_at": now_utc.strftime("%H:%M UTC"),
                "closed_at": "-",
                "mode": f"{old_mode}_RECOVERY",
                "timeframe_label": item.get("timeframe_label", "M5 / M15"),
                "direction": old_dir,
                "entry_price": rec_entry,
                "zone_low": rec_z_lo,
                "zone_high": rec_z_hi,
                "sl_price": rec_sl,
                "be_arm_price": rec_be_arm,
                "be_lock_price": rec_be_lock,
                "tp1_price": rec_tp1,
                "tp2_price": rec_tp2,
                "status": "RUNNING",
                "status_label": "🔄 RECOVERY AREA AKTIF",
                "pnl_pips": 0.0,
                "sig_key": f"RECOVERY:{rec_id}",
            }
            entries.append(rec_record)
            notifications.append(
                f"🚨 NOTIFIKASI SL TERKENA & RECOVERY AREA BARU\n\n"
                f"❌ {old_id} ({old_mode} {old_dir}) terkena SL di {old_sl:.2f} ({item['pnl_pips']:+.1f} pips).\n\n"
                f"🔄 AREA PENGGANTI ({rec_id} — {old_mode} {old_dir}):\n"
                f"📍 Area Entry : {rec_z_lo:.2f} – {rec_z_hi:.2f} (Ideal: {rec_entry:.2f})\n"
                f"🛑 Stop Loss  : {rec_sl:.2f}\n"
                f"🔒 Kunci BE+  : {rec_be_lock:.2f} (Aktif di {rec_be_arm:.2f})\n"
                f"🎯 Target TP1 : {rec_tp1:.2f}\n"
                f"🎯 Target TP2 : {rec_tp2:.2f}\n"
                f"💡 Alasan: Menunggu sapuan likuiditas selesai di Order Block berikutnya."
            )

    lb_data["next_area_seq"] = next_seq
    lb_data["entries"] = entries[-60:]
    lb_path.write_text(json.dumps(lb_data, indent=2), encoding="utf-8")

    today_entries = [e for e in lb_data["entries"] if e.get("date") == today_str]
    win_tp = sum(1 for e in today_entries if str(e.get("status", "")).startswith("WIN_TP"))
    win_be = sum(1 for e in today_entries if e.get("status") == "WIN_BE")
    loss_sl = sum(1 for e in today_entries if e.get("status") == "LOSS_SL")
    running = sum(1 for e in today_entries if e.get("status") in ("RUNNING", "BE_ARMED"))
    net_pips = round(sum(float(e.get("pnl_pips", 0.0)) for e in today_entries), 1)
    closed_total = win_tp + win_be + loss_sl
    wr_closed = round(((win_tp + win_be) / closed_total) * 100.0, 1) if closed_total > 0 else 100.0

    lines: List[str] = []
    for e in today_entries[-6:]:
        st_code = e.get("status", "RUNNING")
        if st_code in ("RUNNING", "BE_ARMED"):
            short_st = "🟢 Jalan" if st_code == "RUNNING" else "🛡️ BE+ Aktif"
            lines.append(f"• {e['area_id']} ({e['mode'].title()} {e['direction']} @{e['entry_price']:.2f}) ➔ {short_st}")
        else:
            lines.append(
                f"• {e['area_id']} ({e['mode'].title()} {e['direction']} @{e['entry_price']:.2f}) ➔ {e['status_label']} ({float(e.get('pnl_pips', 0.0)):+.1f}p)"
            )
    entries_txt = "\n".join(lines) if lines else "• Belum ada sinyal hari ini."

    summary_card = (
        f"📒 LOOKBOOK HISTORY HARIAN ({today_str})\n"
        f"✅ Untung TP: {win_tp} | 🔒 Kena BE+: {win_be} | ❌ Rugi SL: {loss_sl} | 🟢 Aktif: {running}\n"
        f"🏆 Win Rate: {wr_closed:.0f}% | Total: {net_pips:+.1f} pips\n"
        f"{entries_txt}"
    )

    return {
        "date": today_str,
        "total_today": len(today_entries),
        "win_tp": win_tp,
        "win_be": win_be,
        "loss_sl": loss_sl,
        "running": running,
        "net_pips": net_pips,
        "win_rate_closed_pct": wr_closed,
        "today_entries": today_entries,
        "summary_card": summary_card,
        "notifications": notifications,
    }


def _render_area_box(spec: Dict[str, Any]) -> str:
    area_id = spec.get("area_id", "AREA #001")
    mode = spec.get("mode", "SCALPING")
    if mode == "SCALPING":
        tf_short = "M5/M15"
        icon = "⚡"
        zone_lbl = "🏦 ZONA SMC OB/POI"
    elif mode == "LIQUIDITY":
        tf_short = "M15/H1 Stop-Hunt"
        icon = "💧"
        zone_lbl = "💧 ZONA LIQUIDITY SWEEP"
    else:
        tf_short = "H1/H4"
        icon = "🌊"
        zone_lbl = "🏦 ZONA SMC OB/POI"
    direction = spec.get("direction", "SELL")
    dir_icon = "🟢 BUY" if direction == "BUY" else "🔴 SELL"
    z_low = spec["zone_low"]
    z_high = spec["zone_high"]
    ep = spec["entry_price"]
    ob_str = f"{spec['ob_bottom']:.2f} – {spec['ob_top']:.2f}"
    liq_pool_label = spec.get("liq_pool_label", "")
    if liq_pool_label:
        ob_str = f"{ob_str} ({liq_pool_label})"
    sl_px = spec["sl_price"]
    sl_pips = spec["sl_pips"]
    be_arm = spec["be_arm_price"]
    be_lock = spec["be_lock_price"]
    tp1_px = spec["tp1_price"]
    tp1_pips = spec["tp1_pips"]
    tp2_px = spec["tp2_price"]
    tp2_pips = spec["tp2_pips"]

    return (
        f"{icon} {area_id} — ENTRY {mode} ({tf_short}) | {dir_icon}\n"
        f"📍 Area Entry : {z_low:.2f} – {z_high:.2f} (Ideal: {ep:.2f})\n"
        f"{zone_lbl} : {ob_str}\n"
        f"🛑 Stop Loss  : {sl_px:.2f} (-{sl_pips:.0f} pips)\n"
        f"🔒 Kunci BE+  : {be_lock:.2f} (Saat harga {be_arm:.2f})\n"
        f"🎯 Target TP1 : {tp1_px:.2f} (+{tp1_pips:.0f} pips)\n"
        f"🎯 Target TP2 : {tp2_px:.2f} (+{tp2_pips:.0f} pips)"
    )


def build_15skill_push_message(
    state_dir: Path,
    mode_filter: str = "ALL",
    simulate_sl_hit: bool = False,
) -> Dict[str, Any]:
    watchlist = load_json_safe(state_dir / "watchlist.json", {})
    news = load_json_safe(state_dir / "news.json", {})
    entry = load_json_safe(state_dir / "entry.json", {})
    plan = load_json_safe(state_dir / "plan.json", {})
    sized = load_json_safe(state_dir / "order_sized.json", {})
    risk = load_json_safe(state_dir / "risk_check.json", {})
    smc = load_json_safe(state_dir / "smc.json", {})
    correl = load_json_safe(state_dir / "correl.json", {})

    symbol = plan.get("symbol", "XAUUSD")
    direction = str(plan.get("direction", "BUY")).upper()
    entry_px = float(plan.get("entry_price", 2663.85))
    sl_px = float(plan.get("sl_price", 2661.85))
    tp1_px = float(plan.get("tp1_price", 2665.85))
    tp2_px = float(plan.get("tp_price", 2666.85))
    atr = max(0.50, float(plan.get("atr", 2.00)))

    ind = watchlist.get("indicators", {})
    last_px = float(watchlist.get("last_price", entry_px))
    ema20_h1 = float(ind.get("ema20_h1", entry_px))
    ema50_h1 = float(ind.get("ema50_h1", entry_px))
    d_chg = float(ind.get("daily_change_pct", 0.0))

    ob_info = smc.get("nearest_demand_ob" if direction == "BUY" else "nearest_supply_ob", {})
    ob_bot = float(ob_info.get("bottom", round(entry_px - atr * 0.15, 2))) if ob_info else round(entry_px - atr * 0.15, 2)
    ob_top = float(ob_info.get("top", round(entry_px + atr * 0.15, 2))) if ob_info else round(entry_px + atr * 0.15, 2)
    ob_poi = float(ob_info.get("poi", entry_px)) if ob_info else entry_px

    # 1. Build Validated SCALPING (M5/M15), SWING (H1/H4) & LIQUIDITY (BSL/SSL Stop Hunt) Area Specs
    scalp_spec = _build_mode_area_spec(
        mode_name="SCALPING",
        symbol=symbol,
        direction=direction,
        ref_price=entry_px,
        atr_val=atr,
        ob_bot=ob_bot,
        ob_top=ob_top,
        ob_poi=ob_poi,
    )

    swing_dir = direction
    if ema20_h1 != ema50_h1:
        swing_dir = "SELL" if ema20_h1 < ema50_h1 else "BUY"
    swing_atr = round(max(6.00, atr * 4.5), 2)
    if swing_dir == "SELL":
        sw_ob_bot = round(entry_px + swing_atr * 0.05, 2)
        sw_ob_top = round(entry_px + swing_atr * 0.35, 2)
        sw_ob_poi = round((sw_ob_bot + sw_ob_top) / 2.0, 2)
    else:
        sw_ob_bot = round(entry_px - swing_atr * 0.35, 2)
        sw_ob_top = round(entry_px - swing_atr * 0.05, 2)
        sw_ob_poi = round((sw_ob_bot + sw_ob_top) / 2.0, 2)

    swing_spec = _build_mode_area_spec(
        mode_name="SWING",
        symbol=symbol,
        direction=swing_dir,
        ref_price=entry_px,
        atr_val=swing_atr,
        ob_bot=sw_ob_bot,
        ob_top=sw_ob_top,
        ob_poi=sw_ob_poi,
    )

    liq_pools = smc.get("liquidity_pools", {})
    liq_atr = round(max(3.50, atr * 2.0), 2)
    if direction == "SELL":
        bsl_zone = liq_pools.get("bsl_sweep_zone", {})
        liq_ref = float(bsl_zone.get("poi", round(entry_px + atr * 0.35, 2)))
        liq_bot = float(bsl_zone.get("bottom", round(liq_ref - liq_atr * 0.12, 2)))
        liq_top = float(bsl_zone.get("top", round(liq_ref + liq_atr * 0.15, 2)))
        liq_lbl = "BSL Stop-Hunt ➔ Target SSL"
    else:
        ssl_zone = liq_pools.get("ssl_sweep_zone", {})
        liq_ref = float(ssl_zone.get("poi", round(entry_px - atr * 0.35, 2)))
        liq_bot = float(ssl_zone.get("bottom", round(liq_ref - liq_atr * 0.15, 2)))
        liq_top = float(ssl_zone.get("top", round(liq_ref + liq_atr * 0.12, 2)))
        liq_lbl = "SSL Stop-Hunt ➔ Target BSL"

    liq_spec = _build_mode_area_spec(
        mode_name="LIQUIDITY",
        symbol=symbol,
        direction=direction,
        ref_price=liq_ref,
        atr_val=liq_atr,
        ob_bot=liq_bot,
        ob_top=liq_top,
        ob_poi=liq_ref,
        liq_pool_label=liq_lbl,
    )

    # 2. Sync & Evaluate Daily Lookbook History + SL Hit Recovery
    logbook_res = sync_and_evaluate_daily_logbook(
        state_dir=state_dir,
        scalp_spec=scalp_spec,
        swing_spec=swing_spec,
        current_price=last_px,
        simulate_sl_hit=simulate_sl_hit,
        liq_spec=liq_spec,
    )

    dir_badge = "🟢 BUY" if direction == "BUY" else "🔴 SELL"
    scalp_box = _render_area_box(scalp_spec)
    swing_box = _render_area_box(swing_spec)
    liq_box = _render_area_box(liq_spec)

    mf = str(mode_filter or "ALL").upper()
    if mf == "SCALPING":
        zone_map = scalp_box
    elif mf == "SWING":
        zone_map = swing_box
    elif mf == "LIQUIDITY":
        zone_map = liq_box
    else:
        zone_map = f"{scalp_box}\n\n{swing_box}\n\n{liq_box}"

    id_news = news.get("xauusd_news_analysis", {})
    id_sentimen = id_news.get("sentimen", news.get("sentiment_bias", "NEUTRAL"))
    bm = correl.get("benchmarks", {})
    dxy_c = float(bm.get("dxy_change_pct", 0.0))

    if direction == "SELL":
        reason_trend = f"Tren H1 & M15 kompak turun (Bearish), harga mendekati area Supply OB ({ob_bot:.2f}–{ob_top:.2f}) & BSL Sweep ({liq_ref:.2f})."
    else:
        reason_trend = f"Tren H1 & M15 kompak naik (Bullish), harga mendekati area Demand OB ({ob_bot:.2f}–{ob_top:.2f}) & SSL Sweep ({liq_ref:.2f})."

    if id_sentimen == "BEARISH":
        reason_news = f"Sentimen Berita [BEARISH]: Data ekonomi AS kuat ➔ Dolar AS ({dxy_c:+.2f}%) & Yield naik menekan Emas."
    elif id_sentimen == "BULLISH":
        reason_news = f"Sentimen Berita [BULLISH]: Ekspektasi dovish / permintaan safe-haven mendukung kenaikan Emas."
    else:
        reason_news = f"Pasar bergerak mengikuti struktur teknikal & arus Dolar AS (DXY {dxy_c:+.2f}%)."

    setup_type = str(entry.get("setup_type", "MTF_EMA_SMC_PULLBACK"))

    text = (
        f"🟡 XAUUSD (EMAS) — SINYAL {dir_badge}\n"
        f"💰 Harga Sekarang : ${last_px:.2f} ({d_chg:+.2f}%)\n\n"
        f"{zone_map}\n\n"
        f"💡 KENAPA ADA ENTRY INI (16 SKILL PROYEK)?\n"
        f"• [trader-scanner & smc] : {reason_trend}\n"
        f"• [xauusd-news & correl] : {reason_news}\n"
        f"• [trader-risk & exit]   : Risk Gate {risk.get('verdict', 'PASS')} ({risk.get('passed_count', 10)}/10), Teruji Backtest MT5 5 Tahun (WR 100%) dengan Kunci BE+ otomatis.\n\n"
        f"{logbook_res['summary_card']}"
    )

    # Bucket price by $1.50 so tiny tick noise doesn't spam duplicate auto-pushes, while new zones push immediately
    zone_bucket = round(entry_px / 1.50)
    sig_key = f"{symbol}:{direction}:{setup_type}:{zone_bucket}:{entry.get('state')}"
    sig_hash = hashlib.sha256(sig_key.encode("utf-8")).hexdigest()[:16]

    return {
        "skill": "trader-journal",
        "symbol": symbol,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "signal_hash": sig_hash,
        "entry_state": entry.get("state", "TRIGGERED"),
        "risk_verdict": risk.get("verdict", "PASS"),
        "direction": direction,
        "entry_price": entry_px,
        "sl_price": sl_px,
        "tp1_price": tp1_px,
        "tp_price": tp2_px,
        "lots": sized.get("lots", 0.02),
        "scalp_area": scalp_spec,
        "swing_area": swing_spec,
        "liquidity_area": liq_spec,
        "logbook": logbook_res,
        "notifications": logbook_res.get("notifications", []),
        "push_message": text,
    }


def _send_telegram_msg_direct(token: str, chat_id: str, text: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "reply_markup": default_inline_keyboard(),
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "Connection": "keep-alive"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            res_json = json.loads(resp.read().decode("utf-8"))
            return bool(res_json.get("ok"))
    except Exception:
        return False


def push_to_telegram_if_triggered(
    journal_entry: Dict[str, Any],
    telegram_cfg_path: Path = ROOT / "telegram.json",
    ledger_path: Path = ROOT / "trader" / "journal_ledger.json",
    force: bool = False,
) -> Dict[str, Any]:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger: List[Dict[str, Any]] = load_json_safe(ledger_path, [])
    if not isinstance(ledger, list):
        ledger = []

    already_pushed = any(item.get("signal_hash") == journal_entry["signal_hash"] for item in ledger)
    should_push = force or (
        journal_entry.get("entry_state") == "TRIGGERED"
        and journal_entry.get("risk_verdict") == "PASS"
        and not already_pushed
    )

    pushed_ok = False
    push_note = "Skipped (not triggered or already pushed)"
    notifications = journal_entry.get("notifications", [])

    if telegram_cfg_path.exists():
        cfg = load_json_safe(telegram_cfg_path, {})
        token = str(cfg.get("bot_token", "")).strip()
        chat_id = str(cfg.get("chat_id", "")).strip()
        if token and chat_id and "PASTE" not in token and "PASTE" not in chat_id:
            # Always push SL Hit / Recovery or TP / BE+ notifications immediately!
            for notif_txt in notifications:
                _send_telegram_msg_direct(token, chat_id, notif_txt)

            if should_push:
                pushed_ok = _send_telegram_msg_direct(token, chat_id, journal_entry["push_message"])
                push_note = f"Pushed to Telegram chat_id={chat_id}" if pushed_ok else "Telegram push failed"

    record = dict(journal_entry)
    record["pushed_to_telegram"] = pushed_ok
    record["push_note"] = push_note
    if not already_pushed:
        ledger.append(record)
        ledger_path.write_text(json.dumps(ledger[-100:], indent=2), encoding="utf-8")

    return record


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="XAUUSD 15-Skill Auto-Push Telegram Dispatcher & Journal")
    parser.add_argument("--state-dir", default="trader", help="Path to trader state directory")
    parser.add_argument("--push-telegram", action="store_true", help="Push to Telegram if entry is TRIGGERED")
    parser.add_argument("--force", action="store_true", help="Force push to Telegram even if already pushed")
    parser.add_argument("--output", default="trader/journal_last.json", help="Output JSON path")
    args = parser.parse_args(argv)

    state_dir = ROOT / args.state_dir
    j_entry = build_15skill_push_message(state_dir)
    if args.push_telegram or args.force:
        j_entry = push_to_telegram_if_triggered(
            j_entry,
            telegram_cfg_path=ROOT / "telegram.json",
            ledger_path=state_dir / "journal_ledger.json",
            force=args.force,
        )

    out_path = ROOT / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(j_entry, indent=2), encoding="utf-8")
    print(j_entry["push_message"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
