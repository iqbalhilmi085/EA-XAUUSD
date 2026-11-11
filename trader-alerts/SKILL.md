---
name: trader-alerts
description: Multi-condition XAUUSD price, volatility, breakout, and drawdown alert engine. Evaluates alerts.example.json against live/scanner state and writes triggered notifications to trader/alerts_triggered.json.
---

# `/trader-alerts` — XAUUSD Price, Volatility & Risk Alert Engine

Monitors **XAUUSD** for key price levels, ATR volatility spikes, Donchian channel breakouts, news blackouts, and daily drawdown thresholds.

## Supported Alert Types

1. **`PRICE_ABOVE` / `PRICE_BELOW`**: Triggers when XAUUSD crosses psychological or structural levels (e.g. `2660.00`, `2640.00`).
2. **`ATR_SPIKE`**: Triggers when M1/M5 ATR exceeds `threshold` (e.g. `3.50` USD).
3. **`SPREAD_WIDENING`**: Warns when broker spread exceeds `threshold` points.
4. **`ENTRY_TRIGGERED`**: Fires immediately when `trader/entry.json` enters `TRIGGERED` state.
5. **`RISK_BLOCK`**: Fires when `trader/risk_check.json` blocks a trade or locks the day.

## Usage

```bash
python trader-alerts/alerts.py --config trader-alerts/alerts.example.json --output trader/alerts_triggered.json
```
