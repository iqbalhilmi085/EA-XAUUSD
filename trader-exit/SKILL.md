---
name: trader-exit
description: Pre-trade XAUUSD exit planner. Computes ATR-based Stop-Loss with spread floor & broker stops-level clamp, asymmetric Risk-Reward Take-Profit (1.5R default), breakeven lock, trailing stop, and max-hold time exit, writing trader/plan.json.
---

# `/trader-exit` — XAUUSD Pre-Trade Exit & R:R Planner

Constructs the complete exit blueprint **before** capital is committed, matching the asymmetric trend-following discipline of `Project5_Trend_v3` plus institutional trade management.

## Exit Architecture

1. **Dynamic Stop-Loss (`sl_price`)**:
   - `sl_dist = max(atr_mult * ATR, spread_dist * 3.0, broker_stops_level, 1 pip)`
   - Protects against premature stop-outs caused by XAUUSD spread widening while capping dollar risk.
2. **Asymmetric Take-Profit (`tp_price` & `tp1_price`)**:
   - Primary target `tp_price` at `rr_target * sl_dist` (default `1.5R`).
   - Partial/scale-out reference `tp1_price` at `1.0R`.
3. **Breakeven & Trailing Stop Rules**:
   - Moves SL to Breakeven (`+0.5 pip` buffer) once price reaches `1.0R`.
   - Trails behind price by `trail_atr_mult * ATR` beyond `1.2R`.
4. **Time-Stop (`max_hold_bars`)**:
   - Exits stale intraday trades if neither SL nor TP is hit within `max_hold_bars` (default `60` M1 bars).

## Usage

```bash
python trader-exit/exit.py --entry trader/entry.json --atr-mult 1.0 --rr 1.5 --output trader/plan.json
```

## Output (`trader/plan.json`)

Writes `entry_price`, `sl_price`, `tp_price`, `tp1_price`, `sl_distance`, `tp_distance`, `sl_pips`, `tp_pips`, `rr_ratio`, `breakeven_trigger_price`, and `max_hold_bars`.
