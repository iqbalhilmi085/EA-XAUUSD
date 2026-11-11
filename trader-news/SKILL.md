---
name: trader-news
description: Economic calendar blackout filter and Gold/USD news catalyst analyzer for XAUUSD. Protects against FOMC, NFP, CPI, Powell speeches, and geopolitical volatility spikes, writing trader/news.json.
---

# `/trader-news` — XAUUSD Economic Calendar & Catalyst Filter

Monitors high-impact macroeconomic releases (`USD` red-folder events: FOMC, Non-Farm Payrolls, CPI, Core PCE, ISM, Jobless Claims) and breaking geopolitical/central-bank headlines affecting **XAUUSD**.

## Key Capabilities

1. **News Blackout Window (`BLACKOUT` / `CAUTION` / `SAFE`)**:
   - Flags `BLACKOUT` if current time is within `--pre-minutes` (default `30` min) before or `--post-minutes` (default `30` min) after a High-Impact USD event.
   - Prevents the EA or human trader from opening positions right into a 50-pip slippage spike.
2. **Headline Sentiment Scoring**:
   - Scores Gold/USD headlines for safe-haven demand, central bank buying, Treasury yield moves, and Fed hawkish/dovish tone.

## Usage

```bash
# Evaluate news blackout status and sentiment using calendar/news feed
python trader-news/news.py --symbol XAUUSD --output trader/news.json

# Test with custom news fixture
python trader-news/news.py --events-file tests/fixtures/xauusd_news.json --now "2026-11-11T12:00:00+00:00"
```

## Output (`trader/news.json`)

- `status`: `SAFE`, `CAUTION`, or `BLACKOUT`
- `trade_allowed`: boolean (`true` unless `status == "BLACKOUT"`)
- `sentiment_bias`: `BULLISH_GOLD`, `BEARISH_GOLD`, or `NEUTRAL`
- `sentiment_score`: `-100` to `+100`
- `upcoming_high_impact`: list of scheduled high-impact USD events and minutes until release.
