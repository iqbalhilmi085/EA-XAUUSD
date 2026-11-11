---
name: trader-journal
description: Auto-Push Telegram Signal Dispatcher & Trade Performance Journal for the 15-Skill XAUUSD Bot EA. Automatically pushes formatted Entry/SL/Target/SMC cards to Telegram when an entry triggers and logs trade history to trader/journal_ledger.json.
---

# `/trader-journal` — Auto-Push Telegram Signal Dispatcher & Journal

Combines the outputs of all **15 XAUUSD Skills** into a single visual **Auto-Push Telegram Entry Alert** whenever a trade entry is triggered (`entry.state == "TRIGGERED"` and `risk_check.verdict == "PASS"`), and records every signal into `trader/journal_ledger.json`.

## Features

1. **Automatic Push to Telegram (`@theailentxauusd_bot`)**:
   - Sends the complete **Visual Entry Area, Order Block / FVG Confluence, Instant Profit-Lock (`BE+`), Target `TP2`, and Safety `SL`** map directly to your Telegram `chat_id` as soon as an entry triggers.
   - Includes deduplication (`last_pushed_hash`) so the same bar signal is never spammed twice.
2. **Structured Trade Journal (`trader/journal_ledger.json`)**:
   - Logs all 15 skill states at the moment of entry for post-trade audit.

## Usage

```bash
python trader-journal/journal.py --push-telegram
```
