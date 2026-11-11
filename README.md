# EA XAUUSD — 15-Skill Trading Bot

Bot sinyal dan eksekusi XAUUSD (Gold) yang menggabungkan **Python signal engine**
dengan **MetaTrader 5 Expert Advisor**. Setiap keputusan trading melewati 15
skill/modul: scanner, news, macro, smart money, entry, exit, Monte Carlo,
position sizing, risk gatekeeper, alerts, broker, SMC, session, correlation,
dan journal.

> **Disclaimer:** ini bukan jaminan profit. Backtest bukan hasil masa depan.
> Uji dulu di akun demo. Gunakan risiko yang kamu mampu tanggung.

## Arsitektur

```
TradingView / MT5 / fixture bars
              │
              ▼
   xauusd_bot.py  (15 skill Python)
              │
              ├──► trader/*.json          (state & laporan)
              ├──► Telegram (alert)       (opsional)
              └──► trader/xauusd_trader_bridge.json
                              │
                              ▼
              XAUUSD_TraderSkill_EA.mq5  (MetaTrader 5)
                              │
                              ▼
                          Broker
```

## Struktur

| Path | Isi |
|---|---|
| `xauusd_bot.py` | Orchestrator 15 skill |
| `telegram_bot.py` | Bot Telegram (command + auto-scan) |
| `tradingview_webhook.py` | Webhook TradingView → pipeline → MT5/Telegram |
| `trader-*/` | Modul per skill + `SKILL.md` |
| `XAUUSD_TraderSkill_EA.mq5` | EA utama untuk MT5 |
| `Project5_Trend_v3.mq5` | EA trend breakout |
| `tests/` | Unit test offline (17 test) |
| `backtest_results/` | Bukti backtest MT5 5 tahun |
| `api/`, `lib/`, `deploy/vercel/` | Deployment Vercel (signal engine) |

## Jalankan lokal

```bash
python --version          # 3.12+
python xauusd_bot.py --runs 3000
```

Opsi penting:

```bash
python xauusd_bot.py --source fixture     # data offline
python xauusd_bot.py --source mt5         # butuh MetaTrader5 Python package
python xauusd_bot.py --confirm yes        # eksekusi tiket (semi-auto)
python xauusd_bot.py --mode auto          # full-auto
```

Hasil ditulis ke folder `trader/`.

## Telegram

```bash
copy telegram.example.json telegram.json
# isi bot_token dan chat_id
python telegram_bot.py
```

Command: `/push`, `/scalping`, `/swing`, `/liquidity`, `/status`, `/plan`,
`/scan`, `/smc`, `/session`, `/correl`, `/news`, `/macro`, `/logbook`,
`/validasi`, `/simulasi_sl`, `/confirm`, `/auto`.

## MetaTrader 5

1. Copy `XAUUSD_TraderSkill_EA.ex5` ke `MQL5/Experts`.
2. Attach ke chart XAUUSD, aktifkan **Algo Trading**.
3. Mode default `EXEC_HYBRID_BRIDGE` membaca
   `MQL5/Files/xauusd_trader_bridge.json`.
4. Python menulis bridge ke `trader/`; salin ke `MQL5/Files` atau gunakan
   `tradingview_webhook.py` yang menyalin otomatis.

## Test

```bash
python -m unittest discover -s tests -v
```

## Deploy ke Vercel

Versi Vercel hanya menjalankan **signal engine + Telegram bot** (tanpa MT5).
Panduan lengkap: [`deploy/vercel/README.md`](deploy/vercel/README.md).

```bash
npx vercel login
npx vercel link
npx vercel --prod
```

Environment variables yang wajib: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`,
`SCAN_SECRET`. Opsional: `TELEGRAM_WEBHOOK_SECRET`, `CRON_SECRET`,
`UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`.

## Lisensi

Belum ditentukan. Hubungi pemilik repo untuk penggunaan ulang.
