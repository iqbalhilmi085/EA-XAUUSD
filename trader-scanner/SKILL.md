---
name: trader-scanner
description: Multi-timeframe technical and session setup scanner for XAUUSD (Gold) and macro correlations (DXY, US10Y). Detects Donchian trend breakouts, London/NY Opening Range Breakouts (ORB), and liquidity sweeps, outputting trader/watchlist.json.
---

# `/trader-scanner` — XAUUSD Multi-Timeframe Setup Scanner

Scans **XAUUSD (Gold)** across intraday and swing timeframes (`M1`, `M5`, `M15`, `H1`, `H4`) alongside correlated macro benchmarks (`DXY`, `US10Y`) to identify high-probability setups before any trade is planned.

## Supported Setups

1. **`DONCHIAN_TREND_BREAKOUT`**:
   - Trend filter: `EMA_Fast (20)` vs `EMA_Slow (50)` alignment on higher timeframe (`M5`/`M15`).
   - Trigger proximity: Price breaking or approaching the `N`-bar (`20`) Donchian High/Low channel on execution timeframe (`M1`/`M5`).
2. **`SESSION_ORB` (Opening Range Breakout)**:
   - Measures the Asian Session range (`00:00–07:00 UTC`), London Open range (`07:00–08:00 UTC`), or NY Open range (`13:00–14:00 UTC`).
   - Flags clean breakouts with ATR expansion.
3. **`LIQUIDITY_SWEEP_REVERSAL`**:
   - Detects stop-hunts above prior session highs or below prior session lows that reject back inside the range with strong wick ratios.

## Usage

```bash
# Scan using offline/fixture bars or default synthetic XAUUSD feed
python trader-scanner/scan.py --symbol XAUUSD --timeframe M1 --htf M5

# Scan using custom OHLCV JSON file
python trader-scanner/scan.py --bars-file tests/fixtures/xauusd_bars.json --output trader/watchlist.json

# Scan directly from live MetaTrader 5 terminal (if installed)
python trader-scanner/scan.py --source mt5 --symbol XAUUSD
```

## Output (`trader/watchlist.json`)

Writes structured setup candidates including:
- `symbol`, `timestamp`, `last_price`, `atr`, `spread_points`
- `trend_bias` (`BULLISH`, `BEARISH`, `NEUTRAL`)
- `ema_fast`, `ema_slow`, `ema_separation_pips`
- `donchian_high`, `donchian_low`
- `active_setups`: ranked list of actionable XAUUSD setups with `direction`, `setup_type`, `trigger_price`, `invalid_price`, and `score` (`0-100`).
