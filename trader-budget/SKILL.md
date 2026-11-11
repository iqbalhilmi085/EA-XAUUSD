---
name: trader-budget
description: Precision XAUUSD position sizing and compounding target calculator. Supports Standard (USD) and Cent (USC) MT5 accounts, computing exact lot size from SL distance and risk percentage, writing trader/order_sized.json.
---

# `/trader-budget` — XAUUSD Position Sizing & Compounding Budget

Calculates exact **MT5 lot size (`lots`)** for **XAUUSD** based on account equity, risk budget (`risk_per_trade_pct`), and the exact Stop-Loss distance from `trader/plan.json`.

## Account & Contract Calibration

- **Standard XAUUSD Contract (`contract_size = 100 oz`)**:
  - `1.00 lot` moving `$1.00` (`10 pips` / `100 points`) = **`$100.00`**.
  - `0.01 lot` moving `$1.00` (`10 pips` / `100 points`) = **`$1.00`** (`$0.10 per pip`).
- **Cent Account (`USC`) Support**:
  - Automatically scales risk calculations for `USD` vs `USC` accounts (`config.example.json`).
- **Daily / Weekly / Monthly Target Tracking**:
  - Evaluates progress against `targets.example.json` (e.g. `+2.0%` daily profit lock, `-2.0%` daily max loss cap).

## Usage

```bash
python trader-budget/size.py --plan trader/plan.json --config trader-budget/config.example.json --targets trader-budget/targets.example.json --output trader/order_sized.json
```

## Output (`trader/order_sized.json`)

Writes `lots`, `risk_amount_account_ccy`, `risk_pct_actual`, `reward_amount_account_ccy`, and daily target status.
