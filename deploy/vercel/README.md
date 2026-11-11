# Deploy XAUUSD 15-Skill Bot ke Vercel

Versi Vercel ini adalah **signal engine + Telegram bot**, bukan eksekutor order.
Vercel tidak punya Windows/MT5 dan tidak punya proses 24/7, jadi order tetap
dieksekusi manual dari MT5 atau HP.

```
Telegram ──webhook──► /api/telegram ──► 15-skill pipeline ──► balasan Telegram
External cron ──────► /api/scan     ──► sinyal + alert Telegram
Vercel Cron ────────► /api/cron     ──► laporan harian
```

## Yang bisa dan tidak bisa

| Fitur | Vercel |
|---|---|
| Bot Telegram command (`/push`, `/scan`, `/status`, `/smc`, dll) | ✅ |
| Sinyal live on-demand dari TradingView | ✅ |
| Alert otomatis tiap 5 menit (via cron eksternal) | ✅ |
| Laporan harian otomatis | ✅ |
| Scanner loop 60 detik bawaan | ❌ (serverless) |
| Eksekusi order ke MT5 / EA bridge | ❌ (tidak ada Windows/MT5) |
| Journal & ledger permanen | ⚠️ hanya `/tmp`, hilang saat cold start |
| Cron tiap menit dari Vercel | ❌ Hobby = 1×/hari |

> Vercel Hobby gratis untuk penggunaan pribadi. Jangan pakai untuk penggunaan komersial.

## 1. Siapkan Telegram

1. Buat bot di [@BotFather](https://t.me/BotFather) → simpan **bot token**.
2. Kirim pesan apa saja ke bot kamu.
3. Buka `https://api.telegram.org/bot<TOKEN>/getUpdates` → ambil `chat.id`.

## 2. Deploy

```bash
# dari root project (butuh Node.js/npm)
npx vercel login
npx vercel link          # buat project baru, pilih scope akun kamu
npx vercel --prod
```

`npx` akan mengunduh Vercel CLI otomatis, jadi tidak perlu install global.
Kalau lebih suka lewat dashboard: push folder ini ke GitHub, lalu
**Vercel → Add New → Project → Import** repo tersebut. Vercel otomatis
mendeteksi folder `api/` sebagai Python Functions.

> `telegram.json`, folder `trader/`, dan file MQL5 sudah dikecualikan lewat
> `.vercelignore`, jadi tidak ikut ter-upload.
>
> Deployment pertama akan jalan, tapi bot belum aktif sampai environment
> variables di langkah 3 diisi dan di-redeploy.

## 3. Environment variables

Set di **Vercel Dashboard → Project → Settings → Environment Variables**
(atau lewat CLI: `npx vercel env add NAMA production`).

| Variable | Wajib | Contoh | Keterangan |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | `123456:AA...` | Token dari BotFather |
| `TELEGRAM_CHAT_ID` | ✅ | `5769035950` | Chat ID owner |
| `TELEGRAM_ALLOWED_CHAT_IDS` | – | `5769035950,111` | Daftar chat yang boleh akses |
| `TELEGRAM_WEBHOOK_SECRET` | ⭐ | string acak | Verifikasi header Telegram |
| `SCAN_SECRET` | ✅ | string acak | Kunci `/api/scan` |
| `CRON_SECRET` | ⭐ | string acak | Verifikasi Vercel Cron |
| `SYMBOL` | – | `XAUUSD` | Default `XAUUSD` |
| `BACKEND` | – | `paper` | Default `paper` |
| `DEFAULT_MODE` | – | `semi` | Default `semi` |
| `UPSTASH_REDIS_REST_URL` | – | `https://...` | Dedupe alert lintas cold start |
| `UPSTASH_REDIS_REST_TOKEN` | – | `AX...` | Token Upstash |

Generate secret acak:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Atau isi semuanya otomatis (setelah `npx vercel login` + `npx vercel link`):

```powershell
powershell -ExecutionPolicy Bypass -File deploy/vercel/setup_env.ps1
```

Script ini membaca token/chat ID dari `telegram.json`, membuat secret acak,
mengirim semua variable ke environment `production`, dan menyimpan secret
lokal ke `.vercel-env.local.json` (git-ignored).

Setelah mengubah env, **redeploy** (`npx vercel --prod`) agar berlaku.

## 4. Set webhook Telegram

```bash
python deploy/vercel/setup_webhook.py --url https://<project>.vercel.app
```

Script ini memanggil `setWebhook` + `setMyCommands`. Cek hasilnya:

```bash
python deploy/vercel/setup_webhook.py --info
```

Pastikan `url` mengarah ke `https://<project>.vercel.app/api/telegram` dan
`last_error_message` kosong.

## 5. Tes

Buka Telegram, kirim:

- `/status` → ringkasan 15 skill
- `/push` → kartu sinyal lengkap
- `/scan` → scan teknikal
- `/smc`, `/session`, `/correl`, `/berita` → per skill

`/confirm` dan `/auto` sengaja diblokir karena Vercel tidak bisa mengeksekusi order.

## 6. Alert otomatis tiap 5 menit (opsional)

Karena cron Vercel Hobby hanya 1×/hari, pakai cron eksternal gratis seperti
[cron-job.org](https://cron-job.org) atau UptimeRobot:

```
https://<project>.vercel.app/api/scan?key=<SCAN_SECRET>&push=1
```

Interval 5 menit. Setiap kali ada sinyal baru (`TRIGGERED` + risk `PASS`),
bot mengirim satu alert. Duplikat dicegah lewat lock 15 menit.

Tanpa Upstash, lock disimpan di `/tmp` dan hanya bertahan selama instance
masih hangat. Untuk dedupe yang benar-benar konsisten, buat database Redis
gratis di [Upstash](https://upstash.com) lalu isi dua env di atas.

## 7. Laporan harian

`vercel.json` sudah menjadwalkan `/api/cron` setiap `12:00 UTC` (19:00 WIB).
Ubah jamnya di `vercel.json`:

```json
{ "crons": [{ "path": "/api/cron", "schedule": "0 12 * * *" }] }
```

Hobby hanya mengizinkan **1× per hari**. Jadwal lebih sering akan gagal deploy.

## Troubleshooting

| Gejala | Penyebab | Solusi |
|---|---|---|
| Bot tidak membalas | Webhook belum diset / token salah | Jalankan `setup_webhook.py --info` |
| `401 invalid webhook secret` | Secret tidak sama | Samakan `TELEGRAM_WEBHOOK_SECRET` di Vercel dan saat set webhook |
| `409 Conflict` | Masih ada bot long-polling lain | Matikan `telegram_bot.py` di laptop |
| `/api/scan` 503 | `SCAN_SECRET` belum diisi | Set env lalu redeploy |
| Pipeline error / timeout | Sumber data lambat | Cek logs di Vercel → Functions |
| Alert dobel | Tanpa Upstash + cold start | Aktifkan Upstash |
| `/validasi` kosong | Report tidak ikut ter-upload | Cek `.vercelignore` |

## Keamanan

- Jangan commit `telegram.json` (sudah ada di `.gitignore` dan `.vercelignore`).
- Selalu isi `TELEGRAM_WEBHOOK_SECRET`, `SCAN_SECRET`, dan `CRON_SECRET`.
- Batasi `TELEGRAM_ALLOWED_CHAT_IDS` hanya ke chat kamu.
- Siapa pun yang punya `SCAN_SECRET` bisa memicu pipeline (biaya invocations).
- Ini bukan sistem eksekusi order. Jangan menganggap sinyal sebagai jaminan profit.
