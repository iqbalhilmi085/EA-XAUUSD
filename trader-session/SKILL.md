---
name: trader-session
description: Institutional Gold Killzone and liquidity session clock for XAUUSD (Asian Range, London Open Killzone, London-NY Overlap, LBMA Gold Fix, and Rollover Filter), writing trader/session.json.
---

# `/trader-session` — XAUUSD Killzone & Liquidity Clock

Gold (`XAUUSD`) exhibits distinct volatility and breakout reliability across global banking sessions. `session.py` identifies the active institutional Killzone and blocks dangerous rollover hours.

## XAUUSD Institutional Sessions (UTC)

- **`ASIAN_ACCUMULATION` (`00:00 – 06:59 UTC`)**: Range-bound liquidity building; ideal for marking Asian High/Low sweep levels.
- **`LONDON_OPEN_KILLZONE` (`07:00 – 10:59 UTC`)**: High-probability European bullion flow & LBMA AM Fix (`10:30 UTC`).
- **`NY_OPEN_OVERLAP_KILLZONE` (`12:00 – 16:59 UTC`)**: Peak COMEX Gold volume + LBMA PM Fix (`15:00 UTC`). Highest breakout follow-through.
- **`NY_AFTERNOON` (`17:00 – 19:59 UTC`)**: Secondary trend continuation.
- **`ROLLOVER_DANGER_ZONE` (`20:00 – 23:59 UTC`)**: Wide spreads and thin liquidity. Blocked by **WR 100% Precision Mode**.

## Usage

```bash
python trader-session/session.py --output trader/session.json
```
