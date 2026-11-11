---
name: trader-correl
description: Intermarket correlation and SMT (Smart Money Technique) divergence analyzer for XAUUSD against Silver (XAGUSD), US Dollar Index (DXY), US 10Y Treasury Yield (US10Y), and USDJPY, writing trader/correl.json.
---

# `/trader-correl` — XAUUSD Intermarket Correlation & SMT Divergence

Validates whether a Gold (`XAUUSD`) move is supported by intermarket money flow across **Silver (`XAGUSD`)**, **US Dollar (`DXY`)**, **US 10Y Yields (`US10Y`)**, and **Yen (`USDJPY`)**.

## Intermarket Rules for Gold

1. **Inverse DXY & US10Y Confirmation**:
   - When `DXY` and `US10Y` are falling (`< 0%`), `XAUUSD` BUY breakouts have maximum institutional tailwind.
2. **Precious Metals Sympathy & SMT (`XAUUSD` vs `XAGUSD`)**:
   - Checks whether Silver (`XAGUSD`) confirms the directional impulse or forms a bullish/bearish SMT divergence at key session lows/highs.
3. **USDJPY Inverse Carry Flow**:
   - Falling `USDJPY` (strengthening Yen + falling US yields) strongly correlates with Gold rallies.

## Usage

```bash
python trader-correl/correl.py --output trader/correl.json
```
