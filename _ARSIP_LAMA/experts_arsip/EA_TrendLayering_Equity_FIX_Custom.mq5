//+------------------------------------------------------------------+
//|              EA_TrendLayering_NoLimit.mq5
//|              Base: Validated M1 build - fix 6 critical bugs
//|              FIX#8:  cek entry/logic tiap detik via OnTimer
//|              FIX#9:  DD guard auto-resume (cooldown), tanpa ExpertRemove
//|              FIX#10: kena SL -> langsung cari entry baru, gak nunggu candle
//|              FIX#11: recycle layer tertua saat limit InpLevels tercapai
//|              FIX#12: heartbeat log biar Journal gak keliatan mati
//|              ---- CUSTOM ADD-ON (request user) ----
//|              FIX#13: InpEntryMode - CANDLE/STEP/BOTH. Default CANDLE:
//|                      tiap candle baru & trend masih searah -> LANGSUNG
//|                      entry layer baru. TIDAK nunggu posisi lama profit
//|                      atau harga bergerak sekian poin dulu (beda dgn
//|                      mode STEP lama). Ini fitur utama yg diminta.
//|              FIX#14: InpTrendConfirmBars - jumlah bar konfirmasi trend
//|                      bisa diatur (dulu hardcode 2 bar).
//|              FIX#15: InpLotMultiplier - lot tiap layer bisa di-scale
//|                      (flat / makin besar / makin kecil).
//|              FIX#16: InpUseATRForStep - step & SL opsional dinamis pakai
//|                      ATR, bukan poin fixed.
//|              FIX#17: filter jam trading (session) + filter hari.
//|              FIX#18: InpMaxTradesPerDay - batas entry baru per hari.
//|              FIX#19: InpUseFixedTP - opsi TP fixed (default off).
//|              FIX#20: InpUsePartialClose - tutup sebagian volume saat
//|                      profit poin tertentu tercapai.
//|              FIX#21: notifikasi push/alert utk event penting.
//|              ---- NO-LIMIT (request user) ----
//|              FIX#22: BATAS LAYER (InpLevels) DIHAPUS -> layer boleh
//|                      bertambah tanpa batas selama trend masih searah
//|                      (tidak ada lagi recycle layer tertua).
//|              FIX#23: SEMUA FILTER ENTRY DIHAPUS -> tidak ada filter
//|                      spread, filter jam (session), maupun filter hari.
//+------------------------------------------------------------------+
#property copyright "Neurobro"
#property version   "1.40"
#property strict

// ============================================================
// ================   INPUT - PENGATURAN DASAR   ==============
// ============================================================
input bool    InpUseRiskLots    = true;    // FIX#7: true = lot dihitung dari % risiko, false = pakai InpBaseLots
input double  InpRiskPercent    = 1.0;     // % risiko dari BALANCE per entry (dipakai kalau InpUseRiskLots=true)
input double  InpBaseLots       = 0.01;    // Lot tetap / fallback (dipakai kalau InpUseRiskLots=false atau formula gagal)
input double  InpStepPoints     = 350.0;   // Jarak antar layer (dipakai kalau InpEntryMode=STEP atau BOTH)
input double  InpSLPoints       = 300.0;   // SL per posisi (poin fixed, dipakai kalau InpUseATRForStep=false)
input double  InpTrailActiv     = 150.0;   // Pemicu trailing
input double  InpTrailStep      = 30.0;    // Step trailing
input double  InpMaxDDAcctPct   = 6.0;     // Guard equity (% dari puncak)
input double  InpBreakEvenPct   = 60.0;    // Geser BE saat profit X% dari SL
input int     InpMagicNumber    = 20260803;
input ENUM_TIMEFRAMES TF        = PERIOD_M1;
input int     InpFastMA         = 5;
input int     InpSlowMA         = 20;
input double  InpTrendBuffer    = 0.0;     // FIX#2: deadzone anti-flip (poin, 0=off)
input bool    InpOneTradeCandle = true;    // FIX#6: 1 keputusan per candle (rekomendasi: biarkan true)
input int     InpTimerSeconds   = 1;       // FIX#8: interval OnTimer (detik) buat cek logic/entry
input int     InpCooldownMinutes = 60;     // FIX#9: jeda (menit) sblm auto-resume stlh kena DD guard. 0 = nonaktifkan guard sama sekali di sini, EA tetap nempel tapi TIDAK auto-stop.
input int     InpHeartbeatMinutes = 5;     // FIX#12: print status "EA masih hidup" tiap X menit (0 = nonaktif)

// ============================================================
// ===========   FIX#13: MODE ENTRY (INTI REQUEST)   ==========
// ============================================================
enum ENUM_ENTRY_MODE
{
   ENTRY_MODE_CANDLE = 0, // CANDLE (default): tiap candle baru & trend masih searah -> langsung entry layer baru. Lebih sering, gak nunggu posisi lama profit/bergerak dulu.
   ENTRY_MODE_STEP   = 1, // STEP (mode lama): layer baru cuma dibuka kalau harga sudah bergerak >= InpStepPoints dari layer terakhir (menyiratkan posisi lama sudah "profit" dulu)
   ENTRY_MODE_BOTH   = 2  // BOTH: layer PERTAMA di tiap candle bebas (spt CANDLE), layer TAMBAHAN di candle yg sama baru butuh syarat STEP
};
input ENUM_ENTRY_MODE InpEntryMode      = ENTRY_MODE_CANDLE; // Lihat penjelasan enum di atas. INI YG BIKIN ENTRY LEBIH SERING.
input int              InpMaxLayersPerCandle = 1;   // Batas layer baru yg boleh dibuka DALAM 1 candle yg sama (jaga2 kalau InpOneTradeCandle=false)
input int              InpTrendConfirmBars   = 2;   // Jumlah bar closed berturut2 yg harus searah biar trend dianggap valid (dulu hardcode 2)

// ============================================================
// =============   FIX#15: LOT SCALING PER LAYER   ============
// ============================================================
input double  InpLotMultiplier   = 1.0;    // Pengali lot tiap layer BERIKUTNYA. 1.0=flat rata, >1=makin besar tiap layer (agresif), <1=makin kecil (konservatif)

// ============================================================
// =========   FIX#16: STEP & SL DINAMIS PAKAI ATR   ==========
// ============================================================
input bool    InpUseATRForStep   = false;  // true = step & SL ikut volatilitas (ATR), bukan poin fixed
input int     InpATRPeriod       = 14;
input double  InpATRStepMult     = 1.0;    // Step layer = ATR * mult (kalau mode STEP/BOTH)
input double  InpATRSLMult       = 1.5;    // SL = ATR * mult

// ============================================================
// ==========   FIX#18: BATAS ENTRY BARU PER HARI   ===========
// ============================================================
input int     InpMaxTradesPerDay = 0;      // 0 = tanpa batas. Batasi TOTAL entry baru (termasuk hasil recycle) per hari server.

// ============================================================
// ===========   FIX#19: TAKE PROFIT FIXED (OPSIONAL)   =======
// ============================================================
input bool    InpUseFixedTP  = false;      // default off, EA ini basicnya keluar via trailing/BE/DD guard
input double  InpTPPoints    = 0.0;

// ============================================================
// ============   FIX#20: PARTIAL CLOSE (OPSIONAL)   ===========
// ============================================================
input bool    InpUsePartialClose  = false;
input double  InpPartialClosePct  = 50.0;  // % volume ditutup saat trigger tercapai
input double  InpPartialCloseTrig = 200.0; // poin profit trigger partial close

// ============================================================
// ================   FIX#21: NOTIFIKASI   =====================
// ============================================================
input bool    InpEnablePushNotify = false; // push notif ke HP (perlu MetaQuotes ID diset di terminal)
input bool    InpEnableAlertPopup = false; // popup Alert() di terminal

// --- STATE ---
int      g_handleFast    = INVALID_HANDLE;
int      g_handleSlow    = INVALID_HANDLE;
int      g_handleATR     = INVALID_HANDLE;   // FIX#16
double   g_equityHigh    = 0.0;
datetime g_lastSignalTime = 0;
bool     g_tradingHalted = false;
datetime g_haltTime      = 0;
datetime g_lastHeartbeat = 0;

datetime g_layerCandleTime  = 0;             // FIX#13: candle acuan buat hitung layer per-candle
int      g_layersThisCandle = 0;             // FIX#13

datetime g_tradesTodayDate  = 0;             // FIX#18
int      g_tradesToday      = 0;             // FIX#18

ulong    g_partialDone[];                    // FIX#20: ticket yg sudah kena partial close

MqlTradeRequest  g_req;
MqlTradeResult   g_res;

#define TREND_NONE  0
#define TREND_UP    1
#define TREND_DOWN -1

//+------------------------------------------------------------------+
string TradeServerRetcodeDescription(uint retcode);
void   ProcessLogic();
void   MaybePrintHeartbeat();
bool   OpenLayer(int type, double lots);
void   ManageLayers(int trend);
double GetEntryLots(int layerIndex);
double GetEffectiveSLPoints();
double GetEffectiveStepPoints();
double GetATRValue();
bool   CanOpenNewTradeToday();
void   MaybeApplyPartialClose();
void   NotifyEvent(const string msg);
double NormalizeLotToStep(double lots);

//+------------------------------------------------------------------+
int OnInit()
{
   g_handleFast = iMA(_Symbol, TF, InpFastMA, 0, MODE_EMA, PRICE_CLOSE);
   g_handleSlow = iMA(_Symbol, TF, InpSlowMA, 0, MODE_EMA, PRICE_CLOSE);

   if(g_handleFast == INVALID_HANDLE || g_handleSlow == INVALID_HANDLE)
   {
      Print("OnInit: gagal membuat handle MA. Fast=", g_handleFast, " Slow=", g_handleSlow);
      return(INIT_FAILED);
   }

   if(InpUseATRForStep)
   {
      g_handleATR = iATR(_Symbol, TF, MathMax(1, InpATRPeriod));
      if(g_handleATR == INVALID_HANDLE)
         Print("OnInit: gagal membuat handle ATR. InpUseATRForStep akan fallback otomatis ke poin fixed.");
   }

   g_equityHigh       = AccountInfoDouble(ACCOUNT_EQUITY);
   g_lastSignalTime   = 0;
   g_tradingHalted    = false;
   g_haltTime         = 0;
   g_layerCandleTime  = 0;
   g_layersThisCandle = 0;
   g_tradesTodayDate  = 0;
   g_tradesToday      = 0;
   ArrayResize(g_partialDone, 0);

   // FIX#8: pastikan logic (termasuk cek entry) tetap jalan tiap detik
   // walaupun tidak ada tick baru masuk (misal saat market sepi/spread widening).
   EventSetTimer(MathMax(1, InpTimerSeconds));

   Print("OnInit OK. EquityHigh awal=", g_equityHigh,
         ". Timer=", InpTimerSeconds, "s. EntryMode=", EnumToString(InpEntryMode),
         ". MaxLayersPerCandle=", MathMax(1, InpMaxLayersPerCandle),
         ". TrendConfirmBars=", MathMax(1, InpTrendConfirmBars),
         ". LotMultiplier=", DoubleToString(InpLotMultiplier, 2),
         ". MODE: NO-LIMIT (tanpa batas layer, tanpa filter entry).");
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   if(g_handleFast != INVALID_HANDLE) IndicatorRelease(g_handleFast);
   if(g_handleSlow != INVALID_HANDLE) IndicatorRelease(g_handleSlow);
   if(g_handleATR  != INVALID_HANDLE) IndicatorRelease(g_handleATR);
   Print("OnDeinit, alasan=", reason);
}

//+------------------------------------------------------------------+
//| Tick asli dari broker -> tetap diproses seperti biasa             |
//+------------------------------------------------------------------+
void OnTick()
{
   ProcessLogic();
}

//+------------------------------------------------------------------+
//| FIX#8: dipanggil oleh terminal tiap InpTimerSeconds detik,        |
//| terlepas dari ada/tidaknya tick baru dari broker.                 |
//+------------------------------------------------------------------+
void OnTimer()
{
   ProcessLogic();
}

//+------------------------------------------------------------------+
//| Semua logic entry/manajemen posisi, dipanggil dari OnTick maupun  |
//| OnTimer supaya perilakunya identik di kedua jalur.                |
//+------------------------------------------------------------------+
void ProcessLogic()
{
   // FIX#12: heartbeat, jalan terlepas dari halted/cooldown atau tidak.
   MaybePrintHeartbeat();

   // Guard equity dicek paling awal. Kalau sudah halted, EA benar2 diam.
   UpdateEquityGuard();
   if(g_tradingHalted)
      return;

   // Trailing / break-even / partial-close dikelola tiap panggilan.
   ManageStopLoss();
   MaybeApplyPartialClose(); // FIX#20

   int myCount = CountMyPositions();

   datetime curBarTime = iTime(_Symbol, TF, 0);

   // FIX#13: reset jatah layer-per-candle begitu candle berganti.
   if(curBarTime != g_layerCandleTime)
   {
      g_layerCandleTime  = curBarTime;
      g_layersThisCandle = 0;
   }

   // FIX#10: throttle 1x/candle SEKARANG hanya berlaku utk nambah LAYER ke
   // posisi yg masih terbuka (mencegah pyramiding berkali2 dlm 1 candle).
   // Kalau EA sedang FLAT (myCount==0, misal abis kena SL), throttle ini
   // TIDAK berlaku -> EA boleh langsung cari entry baru di candle yg sama.
   if(InpOneTradeCandle && curBarTime == g_lastSignalTime && myCount > 0)
      return;

   int trend = DetectTrend();
   if(trend == TREND_NONE)
      return;

   int myDir = DirectionOfOpen();  // 1=buy, -1=sell, 0=belum ada posisi

   if(myCount == 0)
   {
      if(!CanOpenNewTradeToday()) // FIX#18
      {
         g_lastSignalTime = curBarTime;
         return;
      }
      if(g_layersThisCandle < MathMax(1, InpMaxLayersPerCandle))
      {
         bool ok = OpenLayer((trend == TREND_UP) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, GetEntryLots(0));
         if(ok) g_layersThisCandle++;
      }
      g_lastSignalTime = curBarTime;
      return;
   }

   // Posisi sudah ada & searah trend -> pertimbangkan layer tambahan.
   // FIX#22: TIDAK ada lagi batas InpLevels. Layer boleh terus bertambah
   // selama trend masih searah (masing2 punya SL sendiri, DD guard tetap aktif).
   if((myDir == 1 && trend == TREND_UP) || (myDir == -1 && trend == TREND_DOWN))
   {
      ManageLayers(trend);
      g_lastSignalTime = curBarTime;
   }
   // Trend berlawanan dari posisi terbuka: EA ini TIDAK auto-reverse.
   // Sengaja dibiarkan begitu supaya tidak menambah risiko searah tanpa perintah eksplisit.
}

//+------------------------------------------------------------------+
//| FIX#12: heartbeat -> bukti EA masih hidup, dicetak berkala        |
//+------------------------------------------------------------------+
void MaybePrintHeartbeat()
{
   if(InpHeartbeatMinutes <= 0)
      return;

   if(g_lastHeartbeat != 0 && (TimeCurrent() - g_lastHeartbeat) < InpHeartbeatMinutes * 60)
      return;

   g_lastHeartbeat = TimeCurrent();

   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   string tradesTodayStr = (InpMaxTradesPerDay > 0)
                            ? (IntegerToString(g_tradesToday) + "/" + IntegerToString(InpMaxTradesPerDay))
                            : (IntegerToString(g_tradesToday) + "/unlimited");

   if(g_tradingHalted)
   {
      long remainSec = (long)(InpCooldownMinutes * 60 - (TimeCurrent() - g_haltTime));
      if(remainSec < 0) remainSec = 0;
      Print("[Heartbeat] EA HIDUP - status: COOLDOWN. Sisa ~", remainSec/60,
            " menit sblm resume otomatis. Equity=", DoubleToString(eq,2),
            ". TradesToday=", tradesTodayStr);
   }
   else
   {
      int myCount = CountMyPositions();
      Print("[Heartbeat] EA HIDUP - status: NORMAL. Posisi terbuka=", myCount,
            " (NO LIMIT). EntryMode=", EnumToString(InpEntryMode),
            ". Equity=", DoubleToString(eq,2), ". TradesToday=", tradesTodayStr);
   }
}

//+------------------------------------------------------------------+
//| FIX#9: guard equity TIDAK LAGI permanen (tanpa ExpertRemove).     |
//+------------------------------------------------------------------+
void UpdateEquityGuard()
{
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);

   if(g_tradingHalted)
   {
      if(InpCooldownMinutes <= 0 || (TimeCurrent() - g_haltTime) < InpCooldownMinutes * 60)
         return;

      g_tradingHalted = false;
      g_equityHigh    = eq;
      Print("Cooldown ", InpCooldownMinutes, " menit selesai. EA resume otomatis. EquityHigh baseline baru = ", g_equityHigh);
      NotifyEvent(StringFormat("%s: cooldown selesai, EA resume otomatis.", _Symbol));
   }

   if(eq > g_equityHigh)
      g_equityHigh = eq;

   if(g_equityHigh <= 0.0)
      return;

   double ddPct = (g_equityHigh - eq) / g_equityHigh * 100.0;

   if(ddPct >= InpMaxDDAcctPct && !g_tradingHalted)
   {
      Print("MAX DRAWDOWN TERCAPAI: ", DoubleToString(ddPct,2), "% >= ", InpMaxDDAcctPct,
            "%. Menutup semua posisi. Cooldown ", InpCooldownMinutes, " menit sblm resume otomatis.");
      CloseAll();
      g_tradingHalted = true;
      g_haltTime      = TimeCurrent();
      NotifyEvent(StringFormat("%s: MAX DD %.2f%% tercapai, semua posisi ditutup, cooldown %d menit.",
                  _Symbol, ddPct, InpCooldownMinutes));
   }
}

//+------------------------------------------------------------------+
//| FIX#14: trend stabil, jumlah bar konfirmasi bisa diatur           |
//+------------------------------------------------------------------+
int DetectTrend()
{
   int bars = MathMax(1, InpTrendConfirmBars);
   int need = bars + 2; // +1 bar berjalan (index0) + buffer aman

   double fast[], slow[];
   ArraySetAsSeries(fast, true);
   ArraySetAsSeries(slow, true);

   if(CopyBuffer(g_handleFast, 0, 0, need, fast) < need) return TREND_NONE;
   if(CopyBuffer(g_handleSlow, 0, 0, need, slow) < need) return TREND_NONE;

   double point       = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double bufferPrice = InpTrendBuffer * point;

   bool upStable   = true;
   bool downStable = true;

   for(int i = 1; i <= bars; i++)
   {
      double diff = fast[i] - slow[i];
      if(!(diff > bufferPrice))  upStable   = false;
      if(!(diff < -bufferPrice)) downStable = false;
   }

   if(upStable)   return TREND_UP;
   if(downStable) return TREND_DOWN;
   return TREND_NONE;
}

//+------------------------------------------------------------------+
double LastLayerPrice()
{
   double   lastPrice = 0.0;
   datetime lastTime  = 0;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((int)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;

      datetime openTime = (datetime)PositionGetInteger(POSITION_TIME);
      if(openTime > lastTime)
      {
         lastTime  = openTime;
         lastPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      }
   }
   return lastPrice;
}

//+------------------------------------------------------------------+
int CountMyPositions()
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((int)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;
      count++;
   }
   return count;
}

//+------------------------------------------------------------------+
int DirectionOfOpen()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((int)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;

      long type = PositionGetInteger(POSITION_TYPE);
      return (type == POSITION_TYPE_BUY) ? 1 : -1;
   }
   return 0;
}

//+------------------------------------------------------------------+
//| FIX#7: lot dihitung dari % risiko BALANCE, dinormalisasi ke       |
//|        step/min/max volume broker. Return 0.0 kalau gagal hitung.|
//+------------------------------------------------------------------+
double CalcLotByRisk(double riskPercent, double slPoints)
{
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double riskAmount = balance * riskPercent / 100.0;

   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double point     = SymbolInfoDouble(_Symbol, SYMBOL_POINT);

   if(tickSize <= 0.0 || tickValue <= 0.0 || slPoints <= 0.0 || riskAmount <= 0.0)
   {
      Print("CalcLotByRisk: data simbol tidak valid (tickValue=", tickValue,
            " tickSize=", tickSize, "). Fallback ke InpBaseLots.");
      return 0.0;
   }

   double valuePerPoint = tickValue * (point / tickSize);
   double lossPerLot     = slPoints * valuePerPoint;

   if(lossPerLot <= 0.0)
      return 0.0;

   double lots = riskAmount / lossPerLot;

   double lotStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double minLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);

   if(lotStep > 0.0)
      lots = MathFloor(lots / lotStep) * lotStep;

   lots = MathMax(minLot, MathMin(maxLot, lots));

   if(lots < minLot)
   {
      Print("CalcLotByRisk: hasil hitung (", DoubleToString(lots,2),
            ") di bawah SYMBOL_VOLUME_MIN. Fallback ke InpBaseLots.");
      return 0.0;
   }

   return lots;
}

//+------------------------------------------------------------------+
//| Bulatkan/klem lot ke step & min/max volume broker                |
//+------------------------------------------------------------------+
double NormalizeLotToStep(double lots)
{
   double lotStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double minLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);

   if(lotStep > 0.0)
      lots = MathRound(lots / lotStep) * lotStep;

   lots = MathMax(minLot, MathMin(maxLot, lots));
   return lots;
}

//+------------------------------------------------------------------+
//| FIX#16: ambil nilai ATR bar closed terakhir. 0.0 kalau gagal.     |
//+------------------------------------------------------------------+
double GetATRValue()
{
   if(g_handleATR == INVALID_HANDLE) return 0.0;
   double buf[];
   ArraySetAsSeries(buf, true);
   if(CopyBuffer(g_handleATR, 0, 0, 2, buf) < 2) return 0.0;
   return buf[1]; // pakai bar closed terakhir, bukan bar berjalan
}

//+------------------------------------------------------------------+
//| FIX#16: SL efektif -> ATR kalau diaktifkan & berhasil, else fixed |
//+------------------------------------------------------------------+
double GetEffectiveSLPoints()
{
   if(!InpUseATRForStep) return InpSLPoints;

   double atr = GetATRValue();
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   if(atr <= 0.0 || point <= 0.0) return InpSLPoints;

   double slPts = (atr * InpATRSLMult) / point;
   return (slPts > 0.0) ? slPts : InpSLPoints;
}

//+------------------------------------------------------------------+
//| FIX#16: step efektif -> ATR kalau diaktifkan & berhasil, else fixed|
//+------------------------------------------------------------------+
double GetEffectiveStepPoints()
{
   if(!InpUseATRForStep) return InpStepPoints;

   double atr = GetATRValue();
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   if(atr <= 0.0 || point <= 0.0) return InpStepPoints;

   double stepPts = (atr * InpATRStepMult) / point;
   return (stepPts > 0.0) ? stepPts : InpStepPoints;
}

//+------------------------------------------------------------------+
//| FIX#15: pilih lot final untuk entry berikutnya (baru/layer),      |
//|         layerIndex = 0 utk entry pertama, 1 utk layer ke-2, dst.  |
//+------------------------------------------------------------------+
double GetEntryLots(int layerIndex)
{
   double baseLots;
   if(!InpUseRiskLots)
   {
      baseLots = InpBaseLots;
   }
   else
   {
      double lots = CalcLotByRisk(InpRiskPercent, GetEffectiveSLPoints());
      baseLots = (lots > 0.0) ? lots : InpBaseLots;
   }

   if(layerIndex <= 0 || InpLotMultiplier == 1.0)
      return NormalizeLotToStep(baseLots);

   double scaled = baseLots * MathPow(InpLotMultiplier, layerIndex);
   return NormalizeLotToStep(scaled);
}

//+------------------------------------------------------------------+
//| FIX#18: rollover harian otomatis + cek batas entry baru per hari  |
//+------------------------------------------------------------------+
bool CanOpenNewTradeToday()
{
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   datetime today = StringToTime(StringFormat("%04d.%02d.%02d", dt.year, dt.mon, dt.day));

   if(g_tradesTodayDate != today)
   {
      g_tradesTodayDate = today;
      g_tradesToday = 0;
   }

   if(InpMaxTradesPerDay <= 0) return true;
   return (g_tradesToday < InpMaxTradesPerDay);
}

//+------------------------------------------------------------------+
//| FIX#21: kirim notifikasi (push/alert) sesuai setting               |
//+------------------------------------------------------------------+
void NotifyEvent(const string msg)
{
   if(InpEnablePushNotify)
      SendNotification(msg);
   if(InpEnableAlertPopup)
      Alert(msg);
}

//+------------------------------------------------------------------+
//| FIX#13: buka layer baru. Return true kalau order sukses.          |
//| Kembalikan bool (dulu void) supaya caller bisa update counter     |
//| g_layersThisCandle / g_tradesToday cuma saat beneran sukses.      |
//| FIX#22: cek InpLevels + recycle layer tertua DIHAPUS -> layer     |
//| boleh terus bertambah tanpa batas.                                |
//+------------------------------------------------------------------+
bool OpenLayer(int type, double lots)
{
   double point  = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   int    digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double ask    = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid    = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   double slPoints = GetEffectiveSLPoints(); // FIX#16
   double price = (type == ORDER_TYPE_BUY) ? ask : bid;
   double sl    = (type == ORDER_TYPE_BUY) ? (price - slPoints * point)
                                            : (price + slPoints * point);

   double tp = 0.0;
   if(InpUseFixedTP && InpTPPoints > 0.0) // FIX#19
      tp = (type == ORDER_TYPE_BUY) ? (price + InpTPPoints * point)
                                     : (price - InpTPPoints * point);

   // Cek stops level minimum broker supaya tidak REJECT karena SL/TP terlalu dekat.
   long   stopsLevel  = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   double minStopDist = stopsLevel * point;
   if(minStopDist > 0)
   {
      if(MathAbs(price - sl) < minStopDist)
      {
         Print("OpenLayer: SL lebih dekat dari stops level minimum broker (", stopsLevel,
               " pts). Order dibatalkan.");
         return false;
      }
      if(tp > 0.0 && MathAbs(tp - price) < minStopDist)
      {
         Print("OpenLayer: TP lebih dekat dari stops level minimum broker (", stopsLevel,
               " pts). Order dibatalkan.");
         return false;
      }
   }

   // Pilih filling mode sesuai yang didukung symbol.
   long fillingFlags = SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   ENUM_ORDER_TYPE_FILLING fillMode;
   if((fillingFlags & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK)
      fillMode = ORDER_FILLING_FOK;
   else if((fillingFlags & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC)
      fillMode = ORDER_FILLING_IOC;
   else
      fillMode = ORDER_FILLING_RETURN;

   ZeroMemory(g_req);
   ZeroMemory(g_res);

   g_req.action       = TRADE_ACTION_DEAL;
   g_req.symbol       = _Symbol;
   g_req.volume       = lots;
   g_req.type         = (ENUM_ORDER_TYPE)type;
   g_req.price        = NormalizeDouble(price, digits);
   g_req.sl           = NormalizeDouble(sl, digits);
   g_req.tp           = (tp > 0.0) ? NormalizeDouble(tp, digits) : 0.0;
   g_req.deviation    = 20;
   g_req.magic        = InpMagicNumber;
   g_req.comment      = "TrendLayering";
   g_req.type_filling = fillMode;

   bool sent = OrderSend(g_req, g_res);

   if(!sent || g_res.retcode != TRADE_RETCODE_DONE)
   {
      Print("OrderSend GAGAL. retcode=", g_res.retcode,
            " (", TradeServerRetcodeDescription(g_res.retcode), ")",
            " comment=", g_res.comment);
      return false;
   }

   g_tradesToday++; // FIX#18

   Print("OrderSend OK. Ticket=", g_res.order, " Deal=", g_res.deal,
         " Harga=", g_res.price, " Volume=", g_res.volume,
         " SLpts=", DoubleToString(slPoints,1),
         (tp > 0.0 ? (" TP=" + DoubleToString(g_req.tp, digits)) : ""));

   NotifyEvent(StringFormat("%s: entry baru %s %.2f lot @ %s",
               _Symbol, (type == ORDER_TYPE_BUY ? "BUY" : "SELL"),
               g_res.volume, DoubleToString(g_res.price, digits)));

   return true;
}

//+------------------------------------------------------------------+
void ModifySL(ulong ticket, double sl)
{
   if(!PositionSelectByTicket(ticket)) return;

   double tp     = PositionGetDouble(POSITION_TP);
   int    digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);

   ZeroMemory(g_req);
   ZeroMemory(g_res);

   g_req.action   = TRADE_ACTION_SLTP;
   g_req.position = ticket;
   g_req.symbol   = _Symbol;
   g_req.sl       = NormalizeDouble(sl, digits);
   g_req.tp       = tp;

   bool sent = OrderSend(g_req, g_res);

   if(!sent || g_res.retcode != TRADE_RETCODE_DONE)
   {
      Print("ModifySL GAGAL utk ticket ", ticket, ". retcode=", g_res.retcode,
            " (", TradeServerRetcodeDescription(g_res.retcode), ")");
   }
}

//+------------------------------------------------------------------+
//| FIX#3: trailing SIMETRIS (buy & sell) + break-even                |
//+------------------------------------------------------------------+
void ManageStopLoss()
{
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double ask   = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid   = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double beTriggerPts = InpSLPoints * (InpBreakEvenPct / 100.0);

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((int)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;

      long   type   = PositionGetInteger(POSITION_TYPE);
      double openPr = PositionGetDouble(POSITION_PRICE_OPEN);
      double curSL  = PositionGetDouble(POSITION_SL);

      if(type == POSITION_TYPE_BUY)
      {
         double profitPts = (bid - openPr) / point;

         if(profitPts >= beTriggerPts && curSL < openPr)
         {
            ModifySL(ticket, openPr);
            continue;
         }

         if(profitPts >= InpTrailActiv)
         {
            double newSL = bid - InpTrailStep * point;
            if(newSL > curSL)
               ModifySL(ticket, newSL);
         }
      }
      else if(type == POSITION_TYPE_SELL)
      {
         double profitPts = (openPr - ask) / point;

         if(profitPts >= beTriggerPts && (curSL > openPr || curSL == 0.0))
         {
            ModifySL(ticket, openPr);
            continue;
         }

         if(profitPts >= InpTrailActiv)
         {
            double newSL = ask + InpTrailStep * point;
            if(newSL < curSL || curSL == 0.0)
               ModifySL(ticket, newSL);
         }
      }
   }
}

//+------------------------------------------------------------------+
//| FIX#20: cek & eksekusi partial close per posisi                   |
//+------------------------------------------------------------------+
bool IsPartialDone(ulong ticket)
{
   for(int i = 0; i < ArraySize(g_partialDone); i++)
      if(g_partialDone[i] == ticket) return true;
   return false;
}

void MarkPartialDone(ulong ticket)
{
   int n = ArraySize(g_partialDone);
   ArrayResize(g_partialDone, n + 1);
   g_partialDone[n] = ticket;
}

void CleanupPartialDoneArray()
{
   int n = ArraySize(g_partialDone);
   if(n == 0) return;

   ulong keep[];
   for(int i = 0; i < n; i++)
   {
      if(PositionSelectByTicket(g_partialDone[i]))
      {
         int k = ArraySize(keep);
         ArrayResize(keep, k + 1);
         keep[k] = g_partialDone[i];
      }
   }
   ArrayResize(g_partialDone, ArraySize(keep));
   for(int i = 0; i < ArraySize(keep); i++)
      g_partialDone[i] = keep[i];
}

void MaybeApplyPartialClose()
{
   if(!InpUsePartialClose || InpPartialClosePct <= 0.0 || InpPartialClosePct >= 100.0)
      return;

   CleanupPartialDoneArray();

   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double ask   = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid   = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((int)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;
      if(IsPartialDone(ticket)) continue;

      long   type   = PositionGetInteger(POSITION_TYPE);
      double openPr = PositionGetDouble(POSITION_PRICE_OPEN);
      double vol    = PositionGetDouble(POSITION_VOLUME);

      double profitPts = (type == POSITION_TYPE_BUY) ? (bid - openPr) / point
                                                       : (openPr - ask) / point;

      if(profitPts < InpPartialCloseTrig) continue;

      double closeVol = NormalizeLotToStep(vol * InpPartialClosePct / 100.0);
      if(closeVol < minLot || (vol - closeVol) < minLot)
         continue; // sisa/potongan di bawah min lot broker -> skip biar gak reject

      double price = (type == POSITION_TYPE_BUY) ? bid : ask;

      ZeroMemory(g_req);
      ZeroMemory(g_res);
      g_req.action       = TRADE_ACTION_DEAL;
      g_req.symbol       = _Symbol;
      g_req.volume       = closeVol;
      g_req.position     = ticket;
      g_req.type         = (type == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
      g_req.price        = price;
      g_req.deviation    = 20;
      g_req.magic        = InpMagicNumber;
      g_req.type_filling = ORDER_FILLING_IOC;

      bool sent = OrderSend(g_req, g_res);
      if(sent && g_res.retcode == TRADE_RETCODE_DONE)
      {
         Print("PartialClose OK: ticket ", ticket, " tutup ", DoubleToString(closeVol,2),
               " lot dari ", DoubleToString(vol,2), " (profit ", DoubleToString(profitPts,1), " pts).");
         MarkPartialDone(ticket);
         NotifyEvent(StringFormat("%s: partial close ticket %I64u (%.1f pts profit)", _Symbol, ticket, profitPts));
      }
      else
      {
         Print("PartialClose GAGAL utk ticket ", ticket, ". retcode=", g_res.retcode,
               " (", TradeServerRetcodeDescription(g_res.retcode), ")");
      }
   }
}

//+------------------------------------------------------------------+
//| FIX#13: layering. Default (ENTRY_MODE_CANDLE) = tiap candle baru  |
//| & trend masih searah -> entry, TANPA syarat harga bergerak/profit.|
//| FIX#22: tanpa batas jumlah layer -> selama trend searah & ada     |
//| jatah per-candle, layer baru terus dibuka.                        |
//+------------------------------------------------------------------+
void ManageLayers(int trend)
{
   if(!CanOpenNewTradeToday()) return; // FIX#18
   if(g_layersThisCandle >= MathMax(1, InpMaxLayersPerCandle)) return; // FIX#13

   double point     = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double lastPrice = LastLayerPrice();
   if(lastPrice <= 0.0) return;

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   bool doOpen = false;

   if(InpEntryMode == ENTRY_MODE_CANDLE)
   {
      // INTI REQUEST USER: gak perlu nunggu posisi lama profit/gerak dulu.
      // Selama masih ada jatah di candle ini (g_layersThisCandle < cap) &
      // trend masih searah -> langsung entry.
      doOpen = true;
   }
   else if(InpEntryMode == ENTRY_MODE_STEP)
   {
      double stepPts = GetEffectiveStepPoints();
      if(trend == TREND_UP)   doOpen = (ask - lastPrice) >= stepPts * point;
      if(trend == TREND_DOWN) doOpen = (lastPrice - bid) >= stepPts * point;
   }
   else // ENTRY_MODE_BOTH: layer pertama di candle ini bebas, tambahan butuh step
   {
      if(g_layersThisCandle == 0)
      {
         doOpen = true;
      }
      else
      {
         double stepPts = GetEffectiveStepPoints();
         if(trend == TREND_UP)   doOpen = (ask - lastPrice) >= stepPts * point;
         if(trend == TREND_DOWN) doOpen = (lastPrice - bid) >= stepPts * point;
      }
   }

   if(!doOpen) return;

   int layerIdx = CountMyPositions();
   bool ok = OpenLayer((trend == TREND_UP) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, GetEntryLots(layerIdx));
   if(ok) g_layersThisCandle++;
}

//+------------------------------------------------------------------+
void CloseAll()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((int)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;

      long   type  = PositionGetInteger(POSITION_TYPE);
      double vol   = PositionGetDouble(POSITION_VOLUME);
      double price = (type == POSITION_TYPE_BUY) ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                                                   : SymbolInfoDouble(_Symbol, SYMBOL_ASK);

      ZeroMemory(g_req);
      ZeroMemory(g_res);

      g_req.action       = TRADE_ACTION_DEAL;
      g_req.symbol       = _Symbol;
      g_req.volume       = vol;
      g_req.position     = ticket;
      g_req.type         = (type == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
      g_req.price        = price;
      g_req.deviation    = 20;
      g_req.magic        = InpMagicNumber;
      g_req.type_filling = ORDER_FILLING_IOC;

      bool sent = OrderSend(g_req, g_res);
      if(!sent || g_res.retcode != TRADE_RETCODE_DONE)
      {
         Print("CloseAll GAGAL utk ticket ", ticket, ". retcode=", g_res.retcode,
               " (", TradeServerRetcodeDescription(g_res.retcode), ")");
      }
      else
      {
         Print("CloseAll OK utk ticket ", ticket);
      }
   }
}

//+------------------------------------------------------------------+
//| Helper: deskripsi retcode manusiawi                                |
//+------------------------------------------------------------------+
string TradeServerRetcodeDescription(uint retcode)
{
   switch(retcode)
   {
      case TRADE_RETCODE_REQUOTE:            return "Requote";
      case TRADE_RETCODE_REJECT:             return "Request rejected";
      case TRADE_RETCODE_CANCEL:             return "Request canceled by trader";
      case TRADE_RETCODE_PLACED:             return "Order placed";
      case TRADE_RETCODE_DONE:               return "Request completed";
      case TRADE_RETCODE_DONE_PARTIAL:       return "Request executed partially";
      case TRADE_RETCODE_ERROR:              return "Request processing error";
      case TRADE_RETCODE_TIMEOUT:            return "Request timeout";
      case TRADE_RETCODE_INVALID:            return "Invalid request";
      case TRADE_RETCODE_INVALID_VOLUME:     return "Invalid volume";
      case TRADE_RETCODE_INVALID_PRICE:      return "Invalid price";
      case TRADE_RETCODE_INVALID_STOPS:      return "Invalid stops";
      case TRADE_RETCODE_TRADE_DISABLED:     return "Trading disabled";
      case TRADE_RETCODE_MARKET_CLOSED:      return "Market closed";
      case TRADE_RETCODE_NO_MONEY:           return "Not enough money";
      case TRADE_RETCODE_PRICE_CHANGED:      return "Price changed";
      case TRADE_RETCODE_PRICE_OFF:          return "No quotes to process request";
      case TRADE_RETCODE_INVALID_EXPIRATION: return "Invalid order expiration";
      case TRADE_RETCODE_ORDER_CHANGED:      return "Order state changed";
      case TRADE_RETCODE_TOO_MANY_REQUESTS:  return "Too many requests";
      case TRADE_RETCODE_NO_CHANGES:         return "No changes in request";
      case TRADE_RETCODE_SERVER_DISABLES_AT: return "Autotrading disabled by server";
      case TRADE_RETCODE_CLIENT_DISABLES_AT: return "Autotrading disabled by client terminal";
      case TRADE_RETCODE_LOCKED:             return "Request locked for processing";
      case TRADE_RETCODE_FROZEN:             return "Order or position frozen";
      case TRADE_RETCODE_INVALID_FILL:       return "Invalid order filling type";
      case TRADE_RETCODE_CONNECTION:         return "No connection with trade server";
      case TRADE_RETCODE_ONLY_REAL:          return "Operation allowed only for live accounts";
      case TRADE_RETCODE_LIMIT_ORDERS:       return "Number of pending orders reached limit";
      case TRADE_RETCODE_LIMIT_VOLUME:       return "Volume of orders/positions reached limit";
      default: return "Unknown retcode " + IntegerToString((int)retcode);
   }
}
//+------------------------------------------------------------------+
