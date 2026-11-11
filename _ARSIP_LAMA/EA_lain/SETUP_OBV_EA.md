# Integrasi OBV Signal Confluence → EA MT5 (XAUUSD)

Panduan lengkap menghubungkan indikator TradingView **OBV Signal Confluence [MarkitTick]** dengan
EA MetaTrader 5 agar sinyal BUY/SELL/TP dieksekusi otomatis.

```
TradingView (alert JSON) ──webhook──▶ tv_webhook_bridge.py ──file JSON──▶ MQL5\Files\OBV_Signals ──▶ OBV_SignalEA.mq5
```

File yang disediakan:

| File | Fungsi |
|---|---|
| `OBV_Confluence_Native.mq5` | **REKOMENDASI (akun gratis)** — logika indikator dihitung langsung di MT5, tanpa TradingView |
| `OBV_SignalEA.mq5` | EA pembaca sinyal JSON + eksekusi order (butuh webhook = TV Pro) |
| `tv_webhook_bridge.py` | Server webhook lokal → file JSON (butuh webhook = TV Pro) |

---

## 0. MODE NATIVE — untuk TradingView GRATIS (tanpa webhook)

Akun gratis tidak punya fitur webhook. Solusinya: seluruh logika indikator
(OBV, MA cross, filter HTF/ADX/Volume, level ATR) sudah ditulis ulang langsung
di dalam `OBV_Confluence_Native.mq5`. Tidak butuh TradingView sama sekali.

### Keunggulan
- Nol latensi — sinyal dieksekusi detik ini juga saat bar tertutup.
- Bisa dibacktest & dioptimasi di **Strategy Tester** MT5.
- Tidak tergantung internet/VPS/ngrok.

### Cara pakai
1. Salin `OBV_Confluence_Native.mq5` ke `MQL5\Experts\`, compile di MetaEditor (F7).
2. Pasang di chart XAUUSD timeframe pilihan (disarankan M5/M15), aktifkan Algo Trading.
3. Samakan input dengan setting indikator yang Anda sukai:

   | Input EA | Padanan di indikator TV | Default |
   |---|---|---|
   | `InpMAType` / `InpMALen` | MA Type / MA Len | SMA / 21 |
   | `InpUseHTF` / `InpHTF` | HTF Confirm / HTF | false / H1 |
   | `InpUseADX` / `InpADXMin` | ADX Filter / ADX Min | true / 20 |
   | `InpUseVolFilter` / `InpVolMult` | Vol Filter / Vol Mult | false / 1.0 |
   | `InpSLMult` | SL ATRx | 1.5 |
   | `InpTP1RR..TP3RR` | TP RR | 1 / 2 / 3 |

4. Manajemen uang identik dengan mode webhook: partial TP1/TP2, breakeven,
   trailing, filter spread/jam, hard stop drawdown.

### Backtest di Strategy Tester
1. MT5 → `View ▸ Strategy Tester` (Ctrl+R).
2. Expert: `OBV_Confluence_Native`, Symbol: XAUUSD, Period: M5/M15.
3. Model: "Every tick based on real ticks" untuk akurasi terbaik.
4. Optimasi parameter yang berguna: `InpSLMult`, `InpADXMin`, `InpTP2RR`,
   `InpTrailDistPts`, dan aktif/nonaktifnya `InpUseHTF`.

> Catatan: divergensi di EA hanya sebagai info dashboard/log (sama seperti di
> indikator aslinya, divergensi bukan bagian dari sinyal entry).

---

## 1. Instalasi EA (mode webhook — butuh TradingView Pro)

1. Buka MT5 → `File ▸ Open Data Folder` → masuk ke `MQL5\Experts\`.
2. Salin `OBV_SignalEA.mq5` ke sana.
3. Buka MetaEditor (F4), buka file tersebut, tekan **Compile** (F7). Harus 0 error.
4. Kembali ke MT5, pasang EA di chart **XAUUSD** timeframe yang sama dengan alert TradingView.
5. Aktifkan tombol **Algo Trading** (hijau) di toolbar.
6. Pastikan `Tools ▸ Options ▸ Expert Advisors ▸ Allow...` sesuai kebijakan broker Anda
   (EA ini tidak butuh akses DLL/WebRequest — hanya baca file internal).

## 2. Jalankan Bridge

Butuh **Python 3.8+** (tanpa library tambahan):

```bat
cd "C:\EA XAUUSD"
python tv_webhook_bridge.py --port 8899 --token RAHASIA123
```

- Folder `MQL5\Files\OBV_Signals` dibuat otomatis di **semua instalasi MT5** yang terdeteksi.
- Tes dari browser: `http://localhost:8899/health` → harus muncul `ok`.
- Jangan tutup jendela bridge selama trading.

### Agar bisa diakses TradingView (butuh URL publik)

TradingView webhook butuh alamat publik. Pilihan:

- **ngrok** (gratis): `ngrok http 8899` → catat URL, mis. `https://abc123.ngrok-free.app`
- **cloudflared**: `cloudflared tunnel --url http://localhost:8899`
- Atau jalankan bridge + MT5 di VPS dan buka port langsung.

> ⚠️ Fitur webhook memerlukan langganan TradingView **Pro ke atas**.

## 3. Setup Alert di TradingView

1. Chart XAUUSD, timeframe sesuai rencana (disarankan M5/M15).
2. Klik ikon **Alert** (jam alarm) → pilih indikator OBV Signal Confluence.
3. Di dropdown kondisi pilih: **"Any alert() function call"** ← *wajib, karena payload JSON
   dikirim lewat fungsi `alert()`, bukan alertcondition.*
4. Expiration / Trigger: sesuai selera (`Once per bar close` sudah diatur kode).
5. **Webhook URL**:
   ```
   https://abc123.ngrok-free.app/webhook?token=RAHASIA123
   ```
6. Message: **kosongkan / biarkan apa adanya** — payload JSON sudah dibangun indikator otomatis.
7. Simpan. Setiap sinyal long/short/close/tp akan dikirim sebagai JSON.

Format payload yang diterima EA:

```json
{"action":"long","ticker":"OANDA:XAUUSD","tf":"5","direction":"long",
 "entry":"2380.15","sl":"2377.90","tp1":"2382.40","tp2":"2384.65","tp3":"2386.90",
 "obv":"123456","adx":"24.3"}
```

Aksi yang dikenali EA: `long`, `short`, `closelong`, `closeshort`, `tp1`, `tp2`, `tp3`.

## 4. Input EA Penting

| Input | Default | Arti |
|---|---|---|
| `InpSignalFolder` | `OBV_Signals` | Folder dalam `MQL5\Files`, samakan dengan bridge |
| `InpWebhookToken` | kosong | Isi sama dengan `--token` bridge untuk verifikasi |
| `InpTickerFilter` | kosong | Mis. isi `XAUUSD` agar hanya ticker itu dieksekusi |
| `InpTFFilter` | kosong | Mis. isi `5` agar hanya sinyal TF M5 |
| `InpLotMode` | Lot Tetap | `Lot Tetap` atau `% Risiko dari Balance` (pakai jarak SL payload) |
| `InpUsePayloadSLTP` | true | SL/TP mengikuti hitungan ATR indikator; false = pakai points fix |
| `InpCloseOnOpposite` | true | Sinyal lawan menutup posisi berjalan dulu |
| `InpPartialTP1/TP2` | true | Kunci profit parsial di TP1 (50%) & TP2 (30%), sisanya lari ke TP3 |
| `InpBEAfterTP1` | true | SL digeser ke breakeven setelah TP1 |
| `InpTrailAfterTP2` | true | Trailing stop setelah TP2 tercapai |
| `InpMaxSpreadPoints` | 60 | Tolak entry saat spread melebar (XAUUSD jam sepi) |
| `InpMaxDrawdownPct` | 5% | Hard stop equity; EA berhenti sampai direstart |

## 5. Rekomendasi Setting Indikator untuk XAUUSD

Sesuaikan di pengaturan indikator TradingView:

| Group | Setting | Nilai disarankan |
|---|---|---|
| Core | MA Type / Len | RMA, 21 |
| Filters | HTF Confirm | **ON**, HTF = `60` (H1) untuk TF M5–M15 |
| Filters | ADX Filter | ON, ADX Min = **20–22** (hindari sideways gold) |
| Filters | Vol Filter | ON, Vol Mult = **1.0–1.2** |
| Trade | ATR Len / SL ATRx | 14 / **1.5–2.0** (gold volatil) |
| Trade | TP RR | 1.0 / 2.0 / 3.0 (sudah bagus) |

## 6. Checklist Troubleshooting

| Gejala | Penyebab umum |
|---|---|
| Alert TV terkirim tapi tidak ada file | Bridge mati; token salah (HTTP 403); URL ngrok berganti setelah restart |
| File JSON ada tapi EA diam | EA belum dipasang/AutoTrading off; folder input beda dengan bridge |
| Order ditolak | Spread > batas; lot < minimum broker; pasar tutup |
| Sinyal dobel saat restart alert | Sudah ada guard anti-duplikat `InpMinSecBetwSignal`; pastikan hanya 1 alert aktif |
| EA halt terus | Drawdown menyentuh `InpMaxDrawdownPct` — hapus & pasang ulang EA untuk reset |

Uji cepat tanpa TradingView (simulasi sinyal manual):

```powershell
curl.exe -X POST "http://localhost:8899/webhook?token=RAHASIA123" -d "{\"action\":\"long\",\"ticker\":\"OANDA:XAUUSD\",\"tf\":\"5\",\"entry\":\"2400.00\",\"sl\":\"2397.00\",\"tp1\":\"2403.00\",\"tp2\":\"2406.00\",\"tp3\":\"2409.00\"}"
```

Jika semuanya benar, dalam ±1 detik file muncul di `MQL5\Files\OBV_Signals\` dan EA membuka posisi.
