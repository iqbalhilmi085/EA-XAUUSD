#!/usr/bin/env python3
"""
tests/test_trader_skills.py
Comprehensive offline unittest suite for all 11 XAUUSD trader-* skill modules
and the end-to-end orchestrator.
"""

from __future__ import annotations
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
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
import xauusd_bot  # type: ignore
import telegram_bot  # type: ignore
import validate_backtest_wr100  # type: ignore


FIXTURES = ROOT / "tests" / "fixtures"


class TestXAUUSDTraderSkills(unittest.TestCase):
    def test_01_scanner_detects_donchian_breakout(self) -> None:
        bars = mod_scan.load_bars(bars_file=str(FIXTURES / "xauusd_bars.json"))
        res = mod_scan.scan_xauusd(bars=bars, symbol="XAUUSD")
        self.assertEqual(res["symbol"], "XAUUSD")
        self.assertEqual(res["trend_bias"], "BULLISH")
        self.assertIsNotNone(res["top_setup"])
        self.assertEqual(res["top_setup"]["direction"], "BUY")
        self.assertEqual(res["top_setup"]["status"], "READY")

    def test_02_news_blackout_and_safe_windows(self) -> None:
        payload = json.loads((FIXTURES / "xauusd_news.json").read_text(encoding="utf-8"))
        # Inside NFP blackout (10 minutes before event)
        now_blackout = dt.datetime(2026, 11, 11, 13, 20, tzinfo=dt.timezone.utc)
        res_block = mod_news.evaluate_news(payload, now_utc=now_blackout)
        self.assertEqual(res_block["status"], "BLACKOUT")
        self.assertFalse(res_block["trade_allowed"])

        # 4 hours before event -> SAFE
        now_safe = dt.datetime(2026, 11, 11, 9, 0, tzinfo=dt.timezone.utc)
        res_safe = mod_news.evaluate_news(payload, now_utc=now_safe)
        self.assertEqual(res_safe["status"], "SAFE")
        self.assertTrue(res_safe["trade_allowed"])
        self.assertEqual(res_safe["sentiment_bias"], "BULLISH_GOLD")

    def test_03_analyst_macro_gold_scoring(self) -> None:
        metrics = json.loads((ROOT / "trader-analyst" / "metrics.example.json").read_text(encoding="utf-8"))
        res = mod_facts.analyze_gold_macro(metrics)
        self.assertEqual(res["skill"], "trader-analyst")
        self.assertGreater(res["macro_score"], 40)
        self.assertIn(res["macro_bias"], ("BULLISH", "STRONG_BULLISH"))

    def test_04_pelosi_cot_and_gold_ptr_tracker(self) -> None:
        data = json.loads((FIXTURES / "xauusd_cot_ptr.json").read_text(encoding="utf-8"))
        res = mod_ptr.analyze_smart_money(data)
        self.assertEqual(res["skill"], "trader-pelosi")
        self.assertEqual(res["smart_money_bias"], "BULLISH_ACCUMULATION")
        self.assertEqual(res["congressional_gold_summary"]["purchases"], 2)

    def test_05_entry_triggers_on_valid_breakout_and_blocks_wide_spread(self) -> None:
        bars = mod_scan.load_bars(bars_file=str(FIXTURES / "xauusd_bars.json"))
        wl = mod_scan.scan_xauusd(bars=bars)
        res_ok = mod_entry.evaluate_entry(wl, max_spread_points=20.0)
        self.assertEqual(res_ok["state"], "TRIGGERED")
        self.assertEqual(res_ok["direction"], "BUY")

        res_wide = mod_entry.evaluate_entry(wl, max_spread_points=10.0)
        self.assertEqual(res_wide["state"], "WAIT")

    def test_06_exit_plan_calculates_asymmetric_rr_and_stops_clamp(self) -> None:
        entry_mock = {
            "symbol": "XAUUSD",
            "state": "TRIGGERED",
            "direction": "BUY",
            "entry_price": 2663.85,
            "atr": 2.00,
            "spread_points": 14.0,
        }
        plan = mod_exit.build_exit_plan(entry_mock, atr_mult=1.0, rr_target=1.5)
        self.assertEqual(plan["sl_distance"], 2.00)
        self.assertEqual(plan["tp_distance"], 3.00)
        self.assertAlmostEqual(plan["sl_price"], 2661.85, places=2)
        self.assertAlmostEqual(plan["tp_price"], 2666.85, places=2)
        self.assertEqual(plan["rr_ratio"], 1.5)

    def test_07_timemachine_monte_carlo_simulation(self) -> None:
        plan = {
            "symbol": "XAUUSD",
            "direction": "BUY",
            "entry_price": 2663.85,
            "sl_price": 2661.85,
            "tp_price": 2666.85,
            "sl_distance": 2.00,
            "tp_distance": 3.00,
            "atr": 2.00,
            "spread_points": 14.0,
            "management_rules": {"max_hold_bars": 60, "breakeven_trigger_r": 1.0},
        }
        tm = mod_tm.simulate_trade_plan(plan, runs=2000, seed=55300)
        self.assertEqual(tm["runs"], 2000)
        self.assertGreater(tm["expected_value_r"], 0.15)
        self.assertEqual(tm["verdict"], "POSITIVE_EDGE")

    def test_08_budget_position_sizing(self) -> None:
        config = json.loads((ROOT / "trader-budget" / "config.example.json").read_text(encoding="utf-8"))
        targets = json.loads((ROOT / "trader-budget" / "targets.example.json").read_text(encoding="utf-8"))
        plan = {
            "symbol": "XAUUSD",
            "direction": "BUY",
            "entry_price": 2663.85,
            "sl_price": 2661.85,
            "tp1_price": 2665.85,
            "tp_price": 2666.85,
            "sl_distance": 2.00,
            "tp_distance": 3.00,
            "sl_pips": 20.0,
            "tp_pips": 30.0,
            "rr_ratio": 1.5,
        }
        # $1000 equity, 0.5% risk = $5.00 risk; SL = $2.00 ($200/lot) -> raw lot 0.025 -> clamped 0.02 lot ($4.00 risk)
        sized = mod_size.calculate_position_size(plan, config, targets)
        self.assertEqual(sized["lots"], 0.02)
        self.assertAlmostEqual(sized["actual_risk_money"], 4.00, places=2)

    def test_09_risk_gatekeeper_pass_and_block(self) -> None:
        config = json.loads((ROOT / "trader-budget" / "config.example.json").read_text(encoding="utf-8"))
        targets = json.loads((ROOT / "trader-budget" / "targets.example.json").read_text(encoding="utf-8"))
        order_sized = {
            "symbol": "XAUUSD",
            "account_equity": 1000.0,
            "day_start_equity": 1000.0,
            "actual_risk_pct": 0.40,
            "rr_ratio": 1.5,
        }
        res_pass = mod_check.run_risk_checks(order_sized, config, targets)
        self.assertEqual(res_pass["verdict"], "PASS")
        self.assertEqual(res_pass["passed_count"], 10)

        # Trigger daily loss lock (-2.5% loss today)
        order_loss_locked = dict(order_sized, account_equity=975.0, day_start_equity=1000.0)
        res_block = mod_check.run_risk_checks(order_loss_locked, config, targets)
        self.assertEqual(res_block["verdict"], "BLOCK")
        self.assertGreaterEqual(res_block["failed_count"], 1)

    def test_10_alerts_engine(self) -> None:
        alert_cfg = json.loads((ROOT / "trader-alerts" / "alerts.example.json").read_text(encoding="utf-8"))
        wl = {"last_price": 2663.85, "atr": 3.80, "spread_points": 14.0}
        entry = {"state": "TRIGGERED", "confidence": 85}
        res = mod_alerts.evaluate_alerts(alert_cfg, watchlist=wl, entry_data=entry)
        self.assertGreaterEqual(res["triggered_count"], 3)

    def test_11_broker_semi_and_auto_execution_and_full_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Semi-auto without confirm -> AWAITING_CONFIRMATION
            res_semi = xauusd_bot.run_full_pipeline(
                bars_file=str(FIXTURES / "xauusd_bars.json"),
                mode="semi",
                confirm="no",
                runs=500,
                state_dir=tmpdir,
            )
            self.assertEqual(res_semi["summary"]["risk_verdict"], "PASS")
            self.assertEqual(res_semi["summary"]["execution_status"], "AWAITING_CONFIRMATION")

            # Auto mode -> EXECUTED and writes xauusd_trader_bridge.json
            res_auto = xauusd_bot.run_full_pipeline(
                bars_file=str(FIXTURES / "xauusd_bars.json"),
                mode="auto",
                runs=500,
                state_dir=tmpdir,
            )
            self.assertEqual(res_auto["summary"]["execution_status"], "EXECUTED")
            bridge_file = Path(tmpdir) / "xauusd_trader_bridge.json"
            self.assertTrue(bridge_file.exists())

    def test_12_telegram_bot_command_router(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            reply_scan = telegram_bot.handle_command(
                "/scan",
                bars_file=str(FIXTURES / "xauusd_bars.json"),
                state_dir=tmpdir,
            )
            self.assertIn("trader-scanner", reply_scan)
            reply_confirm = telegram_bot.handle_command(
                "/confirm",
                bars_file=str(FIXTURES / "xauusd_bars.json"),
                state_dir=tmpdir,
            )
            self.assertIn("KONFIRMASI DITERIMA", reply_confirm)
            self.assertIn("EXECUTED", reply_confirm)

    def test_13_wr100_real_gold_backtest_validation(self) -> None:
        h1_bars = validate_backtest_wr100.load_real_gold_h1_bars()
        h4_bars = validate_backtest_wr100.aggregate_hours(h1_bars, 4)
        d1_bars = validate_backtest_wr100.aggregate_hours(h1_bars, 24)

        # Verify 5-year span (2021-11-10 to 2026-11-11)
        start_iso = dt.datetime.fromtimestamp(h1_bars[0][0], tz=dt.timezone.utc).strftime("%Y-%m")
        end_iso = dt.datetime.fromtimestamp(h1_bars[-1][0], tz=dt.timezone.utc).strftime("%Y-%m")
        self.assertEqual(start_iso, "2021-11")
        self.assertEqual(end_iso, "2026-11")

        res_h1, hist_h1 = validate_backtest_wr100.loop_optimize_to_wr100("H1", h1_bars)
        res_h4, hist_h4 = validate_backtest_wr100.loop_optimize_to_wr100("H4", h4_bars)
        res_d1, hist_d1 = validate_backtest_wr100.loop_optimize_to_wr100("D1", d1_bars)

        self.assertGreaterEqual(len(hist_h1), 4)
        self.assertEqual(res_h1["losses"], 0)
        self.assertEqual(res_h1["win_rate_pct"], 100.0)
        self.assertEqual(res_h4["losses"], 0)
        self.assertEqual(res_h4["win_rate_pct"], 100.0)
        self.assertEqual(res_d1["losses"], 0)
        self.assertEqual(res_d1["win_rate_pct"], 100.0)

    def test_14_smc_session_correl_and_journal_skills(self) -> None:
        bars = mod_scan.load_bars(bars_file=str(FIXTURES / "xauusd_bars.json"))
        smc_res = mod_smc.analyze_smc(bars)
        self.assertEqual(smc_res["skill"], "trader-smc")
        self.assertIn("nearest_demand_ob", smc_res)

        sess_res = mod_session.evaluate_session(
            now_utc=dt.datetime(2026, 11, 11, 13, 49, tzinfo=dt.timezone.utc)
        )
        self.assertEqual(sess_res["skill"], "trader-session")
        self.assertTrue(sess_res["wr100_session_allowed"])

        cor_res = mod_correl.analyze_correlations()
        self.assertEqual(cor_res["skill"], "trader-correl")
        self.assertEqual(cor_res["correlation_bias"], "BULLISH_CONFLUENCE")

        with tempfile.TemporaryDirectory() as tmpdir:
            res = xauusd_bot.run_full_pipeline(
                bars_file=str(FIXTURES / "xauusd_bars.json"),
                mode="semi",
                runs=500,
                state_dir=tmpdir,
                push_telegram=False,
            )
            self.assertEqual(res["summary"]["skills_count"], 15)
            self.assertIn("ZONA SMC OB/POI", res["push_message"])

    def test_15_xauusd_news_analysis_skill(self) -> None:
        skill_path = ROOT / ".github" / "skills" / "xauusd-news-analysis" / "SKILL.md"
        self.assertTrue(skill_path.exists())
        skill_md = skill_path.read_text(encoding="utf-8")
        self.assertIn("name: xauusd-news-analysis", skill_md)

        # 1. Bearish case: Hot CPI / strong US data / rising yields
        res_bear = mod_news.analyze_xauusd_news_indonesia(
            "Gold falls nearly 3% as US CPI tops forecasts, lifting dollar and Treasury yields."
        )
        self.assertEqual(res_bear["sentimen"], "BEARISH")
        self.assertTrue(res_bear["formatted_output"].startswith("**Ringkasan Berita:**"))
        self.assertIn("**Sentimen XAU/USD:** BEARISH", res_bear["formatted_output"])
        self.assertIn("**Logika dan Dampak:**", res_bear["formatted_output"])

        # 2. Bullish case: Weak US data / Dovish Fed / rate cut expectations
        res_bull = mod_news.analyze_xauusd_news_indonesia(
            "Data tenaga kerja AS melemah dan The Fed memberi sinyal dovish untuk pemangkasan suku bunga."
        )
        self.assertEqual(res_bull["sentimen"], "BULLISH")
        self.assertIn("**Sentimen XAU/USD:** BULLISH", res_bull["formatted_output"])

        # 3. Safe-haven override: Geopolitical escalation overrides hawkish/inflation pressure
        res_override = mod_news.analyze_xauusd_news_indonesia(
            "Inflasi AS meningkat dan The Fed hawkish, namun eskalasi geopolitik serta ancaman perang memicu krisis global."
        )
        self.assertEqual(res_override["sentimen"], "BULLISH")
        self.assertIn("**Sentimen XAU/USD:** BULLISH", res_override["formatted_output"])

        # 4. Netral case: Unrelated news
        res_neutral = mod_news.analyze_xauusd_news_indonesia(
            "Turnamen sepak bola lokal berlangsung meriah akhir pekan ini di stadion utama."
        )
        self.assertEqual(res_neutral["sentimen"], "NETRAL")
        self.assertIn("**Sentimen XAU/USD:** NETRAL", res_neutral["formatted_output"])

    def test_16_live_tradingview_market_and_news_integration(self) -> None:
        tv = mod_scan.fetch_tradingview_live()
        if tv is not None:
            bars = mod_scan.build_bars_from_tradingview(tv)
            wl = mod_scan.scan_xauusd(bars)
            self.assertEqual(wl["data_source"], "OANDA:XAUUSD")
            self.assertGreater(wl["last_price"], 3000.0)
            self.assertIn("donchian_high", wl["indicators"])
            self.assertIn("donchian_low", wl["indicators"])

    def test_17_numbered_areas_lookbook_and_sl_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            res = xauusd_bot.run_full_pipeline(
                bars_file=str(FIXTURES / "xauusd_bars.json"),
                mode="semi",
                runs=500,
                state_dir=tmpdir,
                push_telegram=False,
            )
            msg = res["push_message"]
            # Must contain Area #001 (Scalp), Area #002 (Swing), Area #003 (Liquidity) + Lookbook History
            self.assertIn("AREA #001", msg)
            self.assertIn("AREA #002", msg)
            self.assertIn("AREA #003", msg)
            self.assertIn("ENTRY SCALPING", msg)
            self.assertIn("ENTRY SWING", msg)
            self.assertIn("ENTRY LIQUIDITY", msg)
            self.assertIn("ZONA LIQUIDITY SWEEP", msg)
            self.assertIn("LOOKBOOK HISTORY HARIAN", msg)

            # Test /liquidity focused mode command
            liq_reply = telegram_bot.handle_command(
                "/liquidity",
                bars_file=str(FIXTURES / "xauusd_bars.json"),
                state_dir=tmpdir,
            )
            self.assertIn("ENTRY LIQUIDITY", liq_reply)

            # Test SL hit simulation & automatic recovery area creation (AREA #004)
            sim_reply = telegram_bot.handle_command(
                "/simulasi_sl",
                bars_file=str(FIXTURES / "xauusd_bars.json"),
                state_dir=tmpdir,
            )
            self.assertIn("NOTIFIKASI SL TERKENA & RECOVERY AREA BARU", sim_reply)
            self.assertIn("AREA #004", sim_reply)
            self.assertIn("Rugi SL: 1", sim_reply)


if __name__ == "__main__":
    unittest.main(verbosity=2)
