---
name: trader-timemachine
description: Monte Carlo and historical bar-replay simulator for XAUUSD trade plans. Replays entry, SL, and TP across 10,000 simulated sessions to compute win rate, Expected Value in R (EV), Profit Factor, and Kelly fraction, writing trader/timemachine.json.
---

# `/trader-timemachine` — 10,000-Run XAUUSD Trade Plan Simulator

Before risking real equity on **XAUUSD**, `timemachine.py` takes the proposed `trader/plan.json` (entry, SL, TP, spread cost, max hold bars) and replays it across **10,000 Monte Carlo paths** calibrated to current Gold volatility and trend drift, plus historical bar windows.

## Metrics Computed

- **`win_rate_pct`**: Percentage of paths hitting `tp_price` before `sl_price`.
- **`loss_rate_pct`**: Percentage of paths hitting `sl_price` first.
- **`timeout_rate_pct`**: Percentage of paths expiring at `max_hold_bars` without hitting TP or SL.
- **`expected_value_r` (`EV`)**: Average net outcome in units of Risk (`R`), accounting for XAUUSD spread friction.
- **`profit_factor`**: Gross simulated R won divided by gross simulated R lost.
- **`verdict`**: `POSITIVE_EDGE` (`EV >= +0.15R`), `MARGINAL` (`0.0R <= EV < 0.15R`), or `NEGATIVE_EDGE` (`EV < 0.0R`).

## Usage

```bash
python trader-timemachine/timemachine.py --plan trader/plan.json --runs 10000 --output trader/timemachine.json
```

## Output (`trader/timemachine.json`)

Used by `trader-risk/check.py` to block low-expectancy trades automatically.
