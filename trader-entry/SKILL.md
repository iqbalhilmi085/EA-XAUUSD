---
name: trader-entry
description: Bar-by-bar XAUUSD entry trigger engine. Confirms candle close breakouts, EMA trend alignment, live spread ceilings, and confluence from macro/smart-money filters before emitting TRIGGERED or WAIT to trader/entry.json.
---

# `/trader-entry` — XAUUSD Precision Entry Trigger

Evaluates the top setup from `trader/watchlist.json` (or live OHLCV bars) to verify whether an exact **bar-close entry trigger** has fired on **XAUUSD**.

## Entry Validation Checklist

1. **Candle Close Confirmation**: Does not enter on intrabar wicks; requires completed bar close above `trigger_price` (`BUY`) or below `trigger_price` (`SELL`).
2. **Trend Filter (`EMA 20 > EMA 50`)**: Ensures execution aligns with the higher-timeframe trend separation (`min_sep_pips`).
3. **Spread Filter (`max_spread_points`)**: Rejects entries when XAUUSD spread widens above threshold (default `20.0` points).
4. **Macro & Smart Money Confluence Bonus**: Reads `trader/analyst_facts.json` and `trader/smart_money.json` if present to adjust entry confidence.

## Usage

```bash
python trader-entry/entry.py --watchlist trader/watchlist.json --output trader/entry.json
python trader-entry/entry.py --bars-file tests/fixtures/xauusd_bars.json --max-spread 20
```

## Output (`trader/entry.json`)

- `state`: `TRIGGERED` or `WAIT`
- `direction`: `BUY`, `SELL`, or `NONE`
- `entry_price`, `trigger_price`, `atr`, `spread_points`
- `confidence`: `0-100`
- `reasons`: list of passed/failed trigger checks.
