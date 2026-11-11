---
name: trader-broker
description: XAUUSD order ticket generator and execution bridge. Supports Semi-Auto (human confirmation 'yes') and Full-Auto modes across MetaTrader 5 Python API, MQL5 EA File Bridge (xauusd_trader_bridge.json), and local Paper Ledger.
---

# `/trader-broker` — XAUUSD Order Ticket & MT5 Execution Bridge

Formats the final plain-text and JSON **XAUUSD Order Ticket** and dispatches orders only when `trader/risk_check.json` has `"verdict": "PASS"`.

## Supported Execution Modes

1. **Semi-Auto Mode (`--mode semi`)**:
   - Displays the complete order ticket preview and requires explicit `--confirm yes` before routing the order.
2. **Full-Auto Mode (`--mode auto`)**:
   - Automatically executes the order as soon as `risk_check.json` is `PASS` and `entry.json` is `TRIGGERED`.

## Supported Broker Backends (`--backend`)

- **`bridge`** *(Default for Hybrid MQL5 EA integration)*: Writes `trader/xauusd_trader_bridge.json` (and optionally copies to MT5's `Common/Files/xauusd_trader_bridge.json`) so `XAUUSD_TraderSkill_EA.mq5` executes the exact ticket inside MetaTrader 5.
- **`mt5`**: Connects directly via the `MetaTrader5` Python library (`mt5.order_send`).
- **`paper`**: Records fills into `trader/paper_ledger.json` for local testing.

## Usage

```bash
# Preview ticket only
python trader-broker/ticket.py --mode semi

# Execute with human confirmation in Semi-Auto mode
python trader-broker/ticket.py --mode semi --confirm yes --backend bridge

# Execute automatically in Full-Auto mode
python trader-broker/ticket.py --mode auto --backend bridge
```
