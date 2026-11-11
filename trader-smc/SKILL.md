---
name: trader-smc
description: Smart Money Concepts (SMC) institutional mapper for XAUUSD. Detects Bullish/Bearish Order Blocks (OB), Fair Value Gaps (FVG / Imbalance), and Break of Structure (BOS) / Change of Character (CHoCH), writing trader/smc.json.
---

# `/trader-smc` — XAUUSD Smart Money Concepts (OB, FVG & BOS Mapper)

Analyzes **XAUUSD** price action to locate institutional footprints so every entry has precise **Order Block (OB)** and **Fair Value Gap (FVG)** support/resistance zones.

## Key Capabilities

1. **Bullish & Bearish Order Blocks (`demand_ob` / `supply_ob`)**:
   - Identifies the last opposing candle before an impulsive displacement move (`body >= 0.55 * ATR`) that breaks structure.
2. **Fair Value Gaps (`fvg_zones`)**:
   - Detects 3-candle price imbalances (`bar[i-2].high < bar[i].low` for Bullish FVG, `bar[i-2].low > bar[i].high` for Bearish FVG).
3. **Structure State (`structure_state`)**:
   - Tracks `BOS_BULLISH`, `BOS_BEARISH`, `CHOCH_BULLISH`, or `CHOCH_BEARISH`.

## Usage

```bash
python trader-smc/smc.py --bars-file tests/fixtures/xauusd_bars.json --output trader/smc.json
```

## Output (`trader/smc.json`)

Writes `structure_state`, `smc_bias`, `smc_score`, `nearest_demand_ob`, `nearest_supply_ob`, and `active_fvgs`.
