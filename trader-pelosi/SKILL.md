---
name: trader-pelosi
description: Smart Money, CFTC COT (Commitment of Traders) Gold Whale positioning, and US Congressional Periodic Transaction Report (PTR) tracker for Gold ETFs and miners (GLD, IAU, GDX, NEM, GOLD), writing trader/smart_money.json.
---

# `/trader-pelosi` — XAUUSD Smart Money, COT Whales & Congressional Gold Disclosures

Adapts the congressional disclosure tracker specifically for **XAUUSD (Gold)** by combining two institutional transparency feeds:

1. **CFTC Commitment of Traders (COT) — COMEX Gold (`GC`)**:
   - Tracks **Managed Money** (hedge funds & CTAs) net long contracts, weekly change, and 52-week percentile rank.
   - Tracks **Commercial Hedgers / Swap Dealers** (bullion banks) positioning to detect extreme crowding or fresh institutional accumulation.
2. **US Congressional PTR Disclosures (Gold / Precious Metals / Macro Hedges)**:
   - Filters House & Senate Periodic Transaction Reports (PTR) for Gold & precious-metal tickers: `GLD`, `IAU`, `GDX`, `NEM`, `GOLD`, `AEM`, `WPM`, `FNV`, `SLV`.

## Usage

```bash
python trader-pelosi/ptr.py --output trader/smart_money.json
python trader-pelosi/ptr.py --fixture tests/fixtures/xauusd_cot_ptr.json --output trader/smart_money.json
```

## Output (`trader/smart_money.json`)

- `smart_money_bias`: `BULLISH_ACCUMULATION`, `BEARISH_DISTRIBUTION`, `CROWDED_LONG_WARNING`, or `NEUTRAL`
- `smart_money_score`: `-100` to `+100`
- `cot_summary`: Managed Money net contracts, weekly delta, and 52-week percentile
- `congressional_gold_trades`: parsed PTR filings in Gold ETFs and major gold miners.
