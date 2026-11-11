---
name: trader-analyst
description: Macroeconomic and quantitative fundamental analyst for XAUUSD (Gold). Evaluates US 10Y Real Yields (TIPS), DXY Dollar Index, Fed rate expectations, CPI/PCE inflation, and SPDR Gold Trust (GLD) ETF tonnage flows, writing trader/analyst_facts.json.
---

# `/trader-analyst` — XAUUSD Macro & Fundamental Analyst

Replaces equity balance-sheet scraping with the **5 core macroeconomic pillars that drive Gold (XAUUSD)**:

1. **US 10Y Real Yield (TIPS)**: Gold has a strong inverse relationship with real interest rates (`real_yield_10y_change_bps`). Falling real yields are strongly bullish for XAUUSD.
2. **US Dollar Index (`DXY`)**: Measures USD strength (`dxy_index`, `dxy_24h_change_pct`).
3. **Fed Monetary Policy & Inflation (`fed_funds_rate`, `cpi_yoy_pct`, `rate_cut_prob_pct`)**: Dovish Fed shifts or sticky inflation with dovish policy boost Gold.
4. **Physical & ETF Flows (`gld_tonnage_change_7d_tons`, `central_bank_net_buying_tons`)**: Institutional accumulation in SPDR Gold Shares (`GLD`) and Sovereign Central Banks.
5. **Volatility & Gold/Silver Ratio (`gvz_gold_vix`, `gold_silver_ratio`)**: Gauges regime stability.

## Usage

```bash
python trader-analyst/facts.py --metrics trader-analyst/metrics.example.json --output trader/analyst_facts.json
```

## Output (`trader/analyst_facts.json`)

- `macro_score`: `-100` to `+100`
- `macro_bias`: `STRONG_BULLISH`, `BULLISH`, `NEUTRAL`, `BEARISH`, `STRONG_BEARISH`
- `regime`: `TREND_EXPANSION`, `LOW_VOL_RANGE`, or `HIGH_VOL_STRESS`
- `pillar_breakdown`: itemized scores and factual explanations.
