//+------------------------------------------------------------------+
//|              EA_TrendLayering_Equity_FIX.mq5
//|              Validated M1 build - fix 6 critical bugs
//|              FIX#8: cek entry/logic tiap detik via OnTimer
//|              FIX#9: DD guard auto-resume (cooldown), tanpa ExpertRemove
//|              FIX#10: kena SL -> langsung cari entry baru, gak nunggu candle
//|              FIX#11: recycle layer tertua saat limit InpLevels tercapai
//|              FIX#12: heartbeat log biar Journal gak keliatan mati
//+------------------------------------------------------------------+
#property copyright "Neurobro"
#property version   "1.24"
#property strict

// --- INPUT ---
input bool    InpUseRiskLots    = true;    // FIX#7: true = lot dihitung dari % risiko, false = pakai InpBaseLots
input double  InpRiskPercent    = 1.0;     // % risiko dari BALANCE per entry (dipakai kalau InpUseRiskLots=true)
input double  InpBaseLots       = 0.01;    // Lot tetap / fallback (dipakai kalau InpUseRiskLots=false atau formula gagal)
input int     InpLevels         = 3;       // Max layer (M1: 2-3, jgn 4)
input double  InpStepPoints     = 350.0;   // Jarak antar layer
input double  InpSLPoints       = 300.0;   // SL per posisi
input double  InpTrailActiv     = 150.0;   // Pemicu trailing
input double  InpTrailStep      = 30.0;    // Step trailing
input double  InpMaxDDAcctPct   = 6.0;     // Guard equity (% dari puncak)
input double  InpBreakEvenPct   = 60.0;    // Geser BE saat profit X% dari SL
input int     InpMagicNumber    = 20260803;
input ENUM_TIMEFRAMES TF        = PERIOD_M1;
input int     InpFastMA         = 5;
input int     InpSlowMA         = 20;
input double  InpMaxSpreadPts   = 40.0;    // FIX#1: MAX spread (poin) sblm entry
input double  InpTrendBuffer    = 0.0;     // FIX#2: deadzone anti-flip (poin, 0=off)
input bool    InpOneTradeCandle = true;    // FIX#6: 1 keputusan per candle
input int     InpTimerSeconds   = 1;       // FIX#8: interval OnTimer (detik) buat cek logic/entry
input int     InpCooldownMinutes = 60;     // FIX#9: jeda (menit) sblm auto-resume stlh kena DD guard. 0 = nonaktifkan guard sama sekali di sini, EA tetap nempel tapi TIDAK auto-stop.
input bool    InpRecycleOldestLayer = true; // FIX#11: kalau posisi terbuka sudah = InpLevels & trend masih sama, tutup layer TERTUA lalu buka yg baru
input int     InpHeartbeatMinutes = 5;     // FIX#12: print status "EA masih hidup" tiap X menit (0 = nonaktif). Biar Journal gak keliatan kosong/mati padahal cuma nunggu.

// --- STATE ---
int      g_handleFast    = INVALID_HANDLE;
int      g_handleSlow    = INVALID_HANDLE;
double   g_equityHigh    = 0.0;
datetime g_lastSignalTime = 0;
bool     g_tradingHalted = false;
datetime g_haltTime      = 0;
datetime g_lastHeartbeat = 0;
MqlTradeRequest  g_req;
MqlTradeResult   g_res;

#define TREND_NONE  0
#define TREND_UP    1
#define TREND_DOWN -1

//+------------------------------------------------------------------+
string TradeServerRetcodeDescription(uint retcode);
void   ProcessLogic();
bool   CloseOldestLayer();
void   MaybePrintHeartbeat();

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

   g_equityHigh      = AccountInfoDouble(ACCOUNT_EQUITY);
   g_lastSignalTime  = 0;
   g_tradingHalted   = false;
   g_haltTime        = 0;

   // FIX#8: pastikan logic (termasuk cek entry) tetap jalan tiap detik
   // walaupun tidak ada tick baru masuk (misal saat market sepi/spread widening).
   EventSetTimer(MathMax(1, InpTimerSeconds));

   Print("OnInit OK. EquityHigh awal = ", g_equityHigh, ". Timer=", InpTimerSeconds, "s");
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   if(g_handleFast != INVALID_HANDLE) IndicatorRelease(g_handleFast);
   if(g_handleSlow != INVALID_HANDLE) IndicatorRelease(g_handleSlow);
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
//| terlepas dari ada/tidaknya tick baru dari broker. Ini yang bikin  |
//| EA "cek entry" tiap detik, bukan cuma nunggu tick.                |
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
   // FIX#12: lapor status tiap InpHeartbeatMinutes menit, TERLEPAS dari
   // halted/cooldown atau tidak. Ini yang jaga Journal supaya gak keliatan
   // kosong/mati padahal EA sebenarnya masih hidup & cuma nunggu.
   MaybePrintHeartbeat();

   // Guard equity dicek paling awal. Kalau sudah halted, EA benar2 diam.
   UpdateEquityGuard();
   if(g_tradingHalted)
      return;

   // Trailing / break-even dikelola tiap panggilan (tiap detik / tiap tick).
   ManageStopLoss();

   int myCount = CountMyPositions();

   // FIX#10: throttle 1x/candle SEKARANG hanya berlaku utk nambah LAYER ke
   // posisi yg masih terbuka (mencegah pyramiding berkali2 dlm 1 candle).
   // Kalau EA sedang FLAT (myCount==0, misal abis kena SL), throttle ini
   // TIDAK berlaku -> EA boleh langsung cari entry baru di candle yg sama,
   // otomatis, tanpa perlu nunggu candle berikutnya / campur tangan manual.
   datetime curBarTime = iTime(_Symbol, TF, 0);
   if(InpOneTradeCandle && curBarTime == g_lastSignalTime && myCount > 0)
      return;

   // FIX#1: spread filter sebelum entry apapun dipertimbangkan.
   long   brokerSpreadPts = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double ask   = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid   = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   double spreadPts = (double)brokerSpreadPts;
   if(point > 0.0)
   {
      double manualSpreadPts = (ask - bid) / point;
      if(manualSpreadPts > spreadPts)
         spreadPts = manualSpreadPts; // ambil yg lebih besar, jaga2 broker raw
   }

   if(spreadPts > InpMaxSpreadPts)
   {
      Print("Spread terlalu lebar (", DoubleToString(spreadPts,1), " pts) > batas ",
            InpMaxSpreadPts, ". Skip entry cek ini.");
      return;
   }

   int trend = DetectTrend();
   if(trend == TREND_NONE)
      return;

   int myDir = DirectionOfOpen();  // 1=buy, -1=sell, 0=belum ada posisi

   if(myCount == 0)
   {
      OpenLayer((trend == TREND_UP) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, GetEntryLots());
      g_lastSignalTime = curBarTime;
      return;
   }

   // Posisi sudah ada & searah trend -> pertimbangkan layer tambahan.
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
//| walau sedang tidak entry apa pun (nunggu trend / cooldown / dll). |
//+------------------------------------------------------------------+
void MaybePrintHeartbeat()
{
   if(InpHeartbeatMinutes <= 0)
      return;

   if(g_lastHeartbeat != 0 && (TimeCurrent() - g_lastHeartbeat) < InpHeartbeatMinutes * 60)
      return;

   g_lastHeartbeat = TimeCurrent();

   double eq = AccountInfoDouble(ACCOUNT_EQUITY);

   if(g_tradingHalted)
   {
      long remainSec = (long)(InpCooldownMinutes * 60 - (TimeCurrent() - g_haltTime));
      if(remainSec < 0) remainSec = 0;
      Print("[Heartbeat] EA HIDUP - status: COOLDOWN. Sisa ~", remainSec/60,
            " menit sblm resume otomatis. Equity=", DoubleToString(eq,2));
   }
   else
   {
      int myCount = CountMyPositions();
      Print("[Heartbeat] EA HIDUP - status: NORMAL. Posisi terbuka=", myCount, "/", InpLevels,
            ". Equity=", DoubleToString(eq,2));
   }
}

//+------------------------------------------------------------------+
//| FIX#9: guard equity TIDAK LAGI permanen (tanpa ExpertRemove).     |
//| Saat DD guard kena: tutup semua posisi, EA masuk mode cooldown.   |
//| Setelah InpCooldownMinutes lewat, EA reset baseline equityHigh ke |
//| level sekarang dan lanjut trading otomatis lagi tanpa perlu       |
//| di-attach ulang manual.                                           |
//+------------------------------------------------------------------+
void UpdateEquityGuard()
{
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);

   if(g_tradingHalted)
   {
      // Masih dalam masa cooldown -> tetap diam, jangan cek DD lagi dulu.
      if(InpCooldownMinutes <= 0 || (TimeCurrent() - g_haltTime) < InpCooldownMinutes * 60)
         return;

      // Cooldown selesai -> resume otomatis. Baseline puncak equity di-reset
      // ke level SEKARANG (bukan nunggu balik ke puncak lama), supaya EA
      // benar2 lanjut jalan, bukan macet nunggu recovery yg mungkin gak pernah terjadi.
      g_tradingHalted = false;
      g_equityHigh    = eq;
      Print("Cooldown ", InpCooldownMinutes, " menit selesai. EA resume otomatis. EquityHigh baseline baru = ", g_equityHigh);
   }

   // equityHigh HANYA boleh naik -> jadi acuan puncak yang benar2 valid
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
      // TIDAK ada ExpertRemove() lagi -> EA tetap nempel di chart & jalan terus,
      // cuma nunggu cooldown lalu resume sendiri.
   }
}

//+------------------------------------------------------------------+
//| FIX: trend STABIL (bukan flip-flop) + deadzone                   |
//+------------------------------------------------------------------+
int DetectTrend()
{
   double fast[], slow[];
   ArraySetAsSeries(fast, true);
   ArraySetAsSeries(slow, true);

   // index0 = bar berjalan (belum closed), index1 & index2 = 2 bar closed terakhir
   if(CopyBuffer(g_handleFast, 0, 0, 4, fast) < 4) return TREND_NONE;
   if(CopyBuffer(g_handleSlow, 0, 0, 4, slow) < 4) return TREND_NONE;

   double point      = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double bufferPrice = InpTrendBuffer * point;

   double diff1 = fast[1] - slow[1];
   double diff2 = fast[2] - slow[2];

   bool upStable   = (diff1 > bufferPrice)  && (diff2 > bufferPrice);
   bool downStable = (diff1 < -bufferPrice) && (diff2 < -bufferPrice);

   if(upStable)   return TREND_UP;
   if(downStable) return TREND_DOWN;
   return TREND_NONE;
}

//+------------------------------------------------------------------+
//| FIX: layer terbaca via ticket dgn waktu open PALING BARU          |
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

   // Nilai uang per 1 poin pergerakan harga, untuk 1.0 lot.
   double valuePerPoint = tickValue * (point / tickSize);
   double lossPerLot     = slPoints * valuePerPoint;

   if(lossPerLot <= 0.0)
      return 0.0;

   double lots = riskAmount / lossPerLot;

   double lotStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double minLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);

   if(lotStep > 0.0)
      lots = MathFloor(lots / lotStep) * lotStep; // bulatkan KE BAWAH biar risiko tidak pernah lebih besar dari target

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
//| FIX#7: pilih lot final untuk entry berikutnya (baru/layer)       |
//+------------------------------------------------------------------+
double GetEntryLots()
{
   if(!InpUseRiskLots)
      return InpBaseLots;

   double lots = CalcLotByRisk(InpRiskPercent, InpSLPoints);
   if(lots <= 0.0)
      return InpBaseLots; // fallback aman kalau formula gagal

   return lots;
}

//+------------------------------------------------------------------+
//| FIX: OrderSend divalidasi penuh via MqlTradeResult                |
//+------------------------------------------------------------------+
void OpenLayer(int type, double lots)
{
   if(CountMyPositions() >= InpLevels)
   {
      if(InpRecycleOldestLayer)
      {
         Print("OpenLayer: sudah mencapai InpLevels (", InpLevels, "). Recycle layer tertua dulu...");
         if(!CloseOldestLayer())
         {
            Print("OpenLayer: recycle GAGAL, skip entry baru kali ini.");
            return;
         }
         // Lanjut ke bawah -> buka posisi baru menggantikan yg baru ditutup.
      }
      else
      {
         Print("OpenLayer: sudah mencapai InpLevels (", InpLevels, "). Skip.");
         return;
      }
   }

   double point  = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   int    digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double ask    = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid    = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   double price = (type == ORDER_TYPE_BUY) ? ask : bid;
   double sl    = (type == ORDER_TYPE_BUY) ? (price - InpSLPoints * point)
                                            : (price + InpSLPoints * point);

   // Cek stops level minimum broker supaya tidak REJECT karena SL terlalu dekat.
   long   stopsLevel  = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   double minStopDist = stopsLevel * point;
   if(minStopDist > 0 && MathAbs(price - sl) < minStopDist)
   {
      Print("OpenLayer: SL lebih dekat dari stops level minimum broker (", stopsLevel,
            " pts). Order dibatalkan.");
      return;
   }

   // Pilih filling mode sesuai yang didukung symbol (hindari TRADE_RETCODE_INVALID_FILL).
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
   g_req.tp           = 0.0;
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
      return;
   }

   Print("OrderSend OK. Ticket=", g_res.order, " Deal=", g_res.deal,
         " Harga=", g_res.price, " Volume=", g_res.volume);
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

         // Break-even: geser SL ke openPr sekali profit >= X% dari SL awal.
         if(profitPts >= beTriggerPts && curSL < openPr)
         {
            ModifySL(ticket, openPr);
            continue;
         }

         // Trailing: SL HANYA maju (naik), tidak pernah mundur.
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

         // Trailing: SL HANYA maju (turun), tidak pernah mundur.
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
//| FIX#4: layering pakai LastLayerPrice (ticket terbaru) + satu arah |
//+------------------------------------------------------------------+
void ManageLayers(int trend)
{
   // FIX#11: cap check DIPINDAH ke dalam OpenLayer() supaya recycle logic
   // (InpRecycleOldestLayer) bisa jalan. Kalau recycle nonaktif, OpenLayer
   // sendiri yg skip dan print "sudah mencapai InpLevels".
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double lastPrice = LastLayerPrice();
   if(lastPrice <= 0.0)
      return;

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   if(trend == TREND_UP)
   {
      if(ask - lastPrice >= InpStepPoints * point)
         OpenLayer(ORDER_TYPE_BUY, GetEntryLots());
   }
   else if(trend == TREND_DOWN)
   {
      if(lastPrice - bid >= InpStepPoints * point)
         OpenLayer(ORDER_TYPE_SELL, GetEntryLots());
   }
}

//+------------------------------------------------------------------+
//| FIX#11: tutup SATU posisi TERTUA (POSITION_TIME paling kecil)     |
//| milik EA ini, biar ada ruang buka layer baru saat limit tercapai. |
//| Return true kalau berhasil ditutup.                               |
//+------------------------------------------------------------------+
bool CloseOldestLayer()
{
   ulong    oldestTicket = 0;
   datetime oldestTime   = 0;
   long     oldestType   = -1;
   double   oldestVol    = 0.0;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((int)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;

      datetime openTime = (datetime)PositionGetInteger(POSITION_TIME);
      if(oldestTicket == 0 || openTime < oldestTime)
      {
         oldestTicket = ticket;
         oldestTime   = openTime;
         oldestType   = PositionGetInteger(POSITION_TYPE);
         oldestVol    = PositionGetDouble(POSITION_VOLUME);
      }
   }

   if(oldestTicket == 0)
      return false; // gak ada posisi sama sekali, aneh tapi tangani aman

   double price = (oldestType == POSITION_TYPE_BUY) ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                                                      : SymbolInfoDouble(_Symbol, SYMBOL_ASK);

   ZeroMemory(g_req);
   ZeroMemory(g_res);

   g_req.action       = TRADE_ACTION_DEAL;
   g_req.symbol       = _Symbol;
   g_req.volume       = oldestVol;
   g_req.position     = oldestTicket;
   g_req.type         = (oldestType == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
   g_req.price        = price;
   g_req.deviation    = 20;
   g_req.magic        = InpMagicNumber;
   g_req.type_filling = ORDER_FILLING_IOC;

   bool sent = OrderSend(g_req, g_res);
   if(!sent || g_res.retcode != TRADE_RETCODE_DONE)
   {
      Print("CloseOldestLayer GAGAL utk ticket ", oldestTicket, ". retcode=", g_res.retcode,
            " (", TradeServerRetcodeDescription(g_res.retcode), ")");
      return false;
   }

   Print("CloseOldestLayer OK: ticket ", oldestTicket, " (buka ",
         TimeToString(oldestTime), ") ditutup utk kasih ruang layer baru.");
   return true;
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
//| Helper: deskripsi retcode manusiawi (MQL5 tidak punya bawaan ini) |
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
