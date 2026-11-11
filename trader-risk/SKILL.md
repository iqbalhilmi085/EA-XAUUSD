---
name: trader-risk
description: Pre-trade safety gatekeeper for XAUUSD. Audits 10 strict discipline rules (daily profit lock, daily loss cut-switch, global peak drawdown kill-switch, post-SL cooldown, max daily entries, spread limit, news blackout, TimeMachine EV, max risk %, and min R:R), outputting PASS or BLOCK to trader/risk_check.json.
---

# `/trader-risk` — XAUUSD 10-Point Risk Gatekeeper

Acts as the non-negotiable firewall between `trader-budget` and `trader-broker`. No XAUUSD order can be submitted unless `check.py` returns `"verdict": "PASS"`.

## The 10 XAUUSD Safety Checks

1. **`global_kill_dd_check`**: Equity drawdown from peak equity must be `< global_kill_drawdown_pct` (`25.0%`).
2. **`daily_loss_lock_check`**: Today's PnL must not breach `-daily_max_loss_pct` (`-2.0%`).
3. **`daily_profit_lock_check`**: Today's PnL must not have already locked at `+daily_profit_lock_pct` (`+2.0%`).
4. **`max_entries_per_day_check`**: Entries today `< max_entries_per_day` (`10`).
5. **`post_sl_cooldown_check`**: At least `cooldown_minutes_after_sl` (`5` min) elapsed since last Stop-Loss hit.
6. **`max_risk_per_trade_check`**: Actual risk of sized lot `<= max_risk_per_trade_pct` (`1.0%`) and fits remaining daily loss buffer.
7. **`min_rr_check`**: Reward-to-Risk ratio `>= min_rr_ratio` (`1.2`).
8. **`spread_ceiling_check`**: Current spread `<= max_spread_points` (`20.0` points).
9. **`news_blackout_check`**: `trader/news.json` status is not `BLACKOUT`.
10. **`timemachine_edge_check`**: `trader/timemachine.json` Expected Value `EV >= 0.0R` (`verdict != "NEGATIVE_EDGE"`).

## Usage

```bash
python trader-risk/check.py --order trader/order_sized.json --output trader/risk_check.json
```

## Output (`trader/risk_check.json`)

Writes `verdict` (`PASS` or `BLOCK`), `passed_count`, `failed_count`, `blocking_reasons`, and detailed per-rule status.
