//+------------------------------------------------------------------+
//|                                       OBV_Confluence_Native.mq5  |
//|  Port native (MQL5) dari indikator TradingView                   |
//|  "OBV Signal Confluence [MarkitTick]"                            |
//|  Tanpa TradingView: sinyal dihitung langsung dari data chart.    |
//|                                                                  |
//|  Logika sinyal (identik dengan Pine):                            |
//|   - OBV = kumulatif sign(delta close) * volume                   |
//|   - Sinyal  = cross OBV vs MA(OBV)                               |
//|   - Filter  : HTF OBV trend, ADX minimum, volume rata-rata       |
//|   - Level   : Entry, SL = ATR*mult, TP = RR 1/2/3 dari risk      |
//+------------------------------------------------------------------+
#property copyright "OBV Signal Confluence - Native Port"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\SymbolInfo.mqh>

CTrade         trade;
CPositionInfo  mpos;
CSymbolInfo    msym;

//=== Enum ==========================================================
enum ENUM_MA_TYPE_OBV
  {
   MA_SMA = 0,   // SMA
   MA_RMA = 1,   // RMA
   MA_WMA = 2,   // WMA
   MA_VWMA = 3   // VWMA
  };

enum ENUM_ENTRY_MODE
  {
   ENTRY_PREV_CLOSE = 0,   // Close bar sebelumnya (paritas dgn TradingView)
   ENTRY_SIGNAL_CLOSE = 1  // Close bar sinyal (harga pasar saat ini)
  };

enum ENUM_LOT_MODE_X
  {
   LOT_FIXED_X = 0,     // Lot Tetap
   LOT_RISK_PCT_X = 1   // % Risiko dari Balance
  };

//=== Sinyal: Core ==================================================
input ENUM_MA_TYPE_OBV InpMAType     = MA_SMA;  // Tipe MA OBV
input int    InpMALen                 = 21;      // Periode MA OBV
input int    InpBarsCalc              = 1000;    // Jumlah bar kalkulasi rolling

//=== Sinyal: Filters ===============================================
input bool   InpUseHTF                = false;   // Konfirmasi timeframe tinggi
input ENUM_TIMEFRAMES InpHTF          = PERIOD_H1; // Timeframe konfirmasi
input bool   InpUseADX                = true;    // Filter ADX
input int    InpADXLen                = 14;      // Periode ADX
input double InpADXMin                = 20.0;    // ADX minimum
input bool   InpUseVolFilter          = false;   // Filter volume
input int    InpVolLen                = 20;      // Periode SMA volume
input double InpVolMult               = 1.0;     // Volume >= SMA x mult

//=== Level Trade ===================================================
input ENUM_ENTRY_MODE InpEntryMode    = ENTRY_PREV_CLOSE; // Acuan harga entry
input int    InpATRLen                = 14;      // Periode ATR
input double InpSLMult                = 1.5;     // SL = ATR x mult
input double InpTP1RR                 = 1.0;     // TP1 Risk:Reward
input double InpTP2RR                 = 2.0;     // TP2 Risk:Reward
input double InpTP3RR                 = 3.0;     // TP3 Risk:Reward

//=== Eksekusi ======================================================
input long   InpMagicNumber           = 12351;   // Magic number
input int    InpSlippagePoints        = 30;      // Slippage maksimal (points)
input double InpMaxSpreadPoints       = 60;      // Spread maksimal (points, 0=nonaktif)

//=== Lot & Risiko ==================================================
input ENUM_LOT_MODE_X InpLotMode      = LOT_FIXED_X; // Mode penentuan lot
input double InpFixedLot              = 0.01;    // Lot tetap
input double InpRiskPercent           = 0.5;     // % balance per trade (mode risiko)
input double InpMaxLot                = 0.10;    // Batas lot maksimal per order

//=== Manajemen Posisi ==============================================
input int    InpMaxPositions          = 1;       // Maksimal posisi bersamaan
input bool   InpPartialTP1            = true;    // Partial close di TP1
input double InpTP1ClosePct           = 50.0;    // % volume ditutup di TP1
input bool   InpBEAfterTP1            = true;    // SL ke breakeven setelah TP1
input bool   InpPartialTP2            = true;    // Partial close di TP2
input double InpTP2ClosePct           = 30.0;    // % volume ditutup di TP2
input bool   InpTrailAfterTP2         = true;    // Trailing stop setelah TP2
input int    InpTrailDistPts          = 250;     // Jarak trailing (points)

//=== Filter Waktu & Keamanan =======================================
input bool   InpUseTimeFilter         = false;   // Aktifkan filter jam
input int    InpStartHour             = 1;       // Jam mulai (server)
input int    InpEndHour               = 23;      // Jam selesai (server)
input bool   InpCloseFriday           = false;   // Tutup semua akhir Jumat
input int    InpFridayCloseHour       = 20;      // Jam tutup Jumat (server)
input double InpMaxDrawdownPct        = 5.0;     // Hard stop DD equity % (restart utk lanjut)
input bool   InpPushNotify            = false;   // Kirim notifikasi push saat sinyal

//=== State global ==================================================
int      g_atrHandle = INVALID_HANDLE;
int      g_adxHandle = INVALID_HANDLE;
double   g_eqPeak    = 0.0;
bool     g_halted    = false;

// hasil evaluasi bar terakhir (untuk eksekusi)
double   g_evalEntry = 0.0;
double   g_evalSL    = 0.0;
double   g_evalTP1   = 0.0;
double   g_evalTP2   = 0.0;
double   g_evalTP3   = 0.0;

// dashboard info terakhir
string   g_dashTrend = "-";
string   g_dashDiv   = "None";
string   g_dashDir   = "Flat";
double   g_dashADX   = 0.0;
double   g_dashVolR  = 0.0;

// pelacak pivot divergensi (info saja)
double   g_lastPH = 0, g_prevPH = 0, g_lastPHobvH = 0, g_prevPHobvH = 0;
bool     g_hasPH = false, g_hasPrevPH = false;
double   g_lastPL = 0, g_prevPL = 0, g_lastPLobvH = 0, g_prevPLobvH = 0;
bool     g_hasPL = false, g_hasPrevPL = false;

const string GV_PREFIX = "OBVEA_";

//+------------------------------------------------------------------+
//| OnInit                                                            |
//+------------------------------------------------------------------+
int OnInit()
  {
   msym.Name(_Symbol);
   if(!msym.Refresh())
     {
      Print("Gagal init symbol: ", _Symbol);
      return INIT_FAILED;
     }

   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(InpSlippagePoints);
   trade.SetTypeFillingBySymbol(_Symbol);

   g_atrHandle = iATR(_Symbol, _Period, InpATRLen);
   if(g_atrHandle == INVALID_HANDLE)
     {
      Print("Gagal membuat handle ATR");
      return INIT_FAILED;
     }

   if(InpUseADX)
     {
      g_adxHandle = iADX(_Symbol, _Period, InpADXLen);
      if(g_adxHandle == INVALID_HANDLE)
        {
         Print("Gagal membuat handle ADX");
         return INIT_FAILED;
        }
     }

   g_eqPeak = AccountInfoDouble(ACCOUNT_EQUITY);
   g_halted = false;

   EventSetMillisecondTimer(500);
   Print("OBV_Confluence_Native aktif pada ", _Symbol, " ", EnumToString(_Period));
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
//| OnDeinit                                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();
   if(g_atrHandle != INVALID_HANDLE)
      IndicatorRelease(g_atrHandle);
   if(g_adxHandle != INVALID_HANDLE)
      IndicatorRelease(g_adxHandle);
   Comment("");
  }

//+------------------------------------------------------------------+
//| Loop utama                                                        |
//+------------------------------------------------------------------+
void Process()
  {
   if(!msym.RefreshRates())
      return;

   UpdateHaltAndFriday();

   if(g_halted)
     {
      Comment("OBV Native EA: HALT (drawdown)\nRestart EA untuk melanjutkan");
      return;
     }

   CheckNewBarAndEvaluate();
   ManagePositions();
   CleanupStageVars();
   UpdateComment();
  }

void OnTimer() { Process(); }
void OnTick()  { Process(); }

//+------------------------------------------------------------------+
//| Hard stop drawdown + tutup paksa Jumat                           |
//+------------------------------------------------------------------+
void UpdateHaltAndFriday()
  {
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   if(eq > g_eqPeak)
      g_eqPeak = eq;

   if(g_eqPeak > 0)
     {
      double ddPct = (g_eqPeak - eq) / g_eqPeak * 100.0;
      if(ddPct >= InpMaxDrawdownPct)
        {
         CloseAllOwn("HARD STOP DD");
         g_halted = true;
         Print("HALT: drawdown ", DoubleToString(ddPct, 2), "%");
        }
     }

   if(InpCloseFriday && !g_halted)
     {
      MqlDateTime dt;
      TimeToStruct(TimeCurrent(), dt);
      if(dt.day_of_week == 5 && dt.hour >= InpFridayCloseHour)
         CloseAllOwn("FRIDAY CLOSE");
     }
  }

//+------------------------------------------------------------------+
//| Deteksi bar baru lalu evaluasi bar yang baru saja tertutup       |
//+------------------------------------------------------------------+
void CheckNewBarAndEvaluate()
  {
   static datetime lastBar = 0;
   datetime cur = iTime(_Symbol, _Period, 0);
   if(cur == lastBar)
      return;
   lastBar = cur;
   EvaluateClosedBar();
  }

//+------------------------------------------------------------------+
//| Hitung seri OBV kronologis dari rates                            |
//+------------------------------------------------------------------+
void BuildObvSeries(const MqlRates &r[], double &obv[])
  {
   int n = ArraySize(r);
   ArrayResize(obv, n);
   obv[0] = 0.0;
   for(int i = 1; i < n; i++)
     {
      double dc = r[i].close - r[i - 1].close;
      double sg = (dc > 0 ? 1.0 : (dc < 0 ? -1.0 : 0.0));
      obv[i] = obv[i - 1] + sg * (double)r[i].tick_volume;
     }
  }

//+------------------------------------------------------------------+
//| Isi array MA dari seri OBV (SMA/RMA/WMA/VWMA)                    |
//+------------------------------------------------------------------+
void BuildMASeries(const double &obv[], const MqlRates &r[], const int matype,
                   const int len, double &ma[])
  {
   int n = ArraySize(obv);
   ArrayResize(ma, n);

   for(int i = 0; i < n; i++)
     {
      ma[i] = 0.0;
      if(i < len - 1)
         continue;

      if(matype == MA_SMA)
        {
         double s = 0;
         for(int j = i - len + 1; j <= i; j++)
            s += obv[j];
         ma[i] = s / len;
        }
      else if(matype == MA_RMA)
        {
         if(i == len - 1)
           {
            double s = 0;
            for(int j = 0; j <= i; j++)
               s += obv[j];
            ma[i] = s / len;
           }
         else
            ma[i] = (ma[i - 1] * (len - 1) + obv[i]) / len;
        }
      else if(matype == MA_WMA)
        {
         double sw = 0, sv = 0;
         for(int j = i - len + 1, w = 1; j <= i; j++, w++)
           {
            sv += w * obv[j];
            sw += w;
           }
         ma[i] = sv / sw;
        }
      else // VWMA
        {
         double sp = 0, sv = 0;
         for(int j = i - len + 1; j <= i; j++)
           {
            sp += obv[j] * (double)r[j].tick_volume;
            sv += (double)r[j].tick_volume;
           }
         ma[i] = (sv > 0 ? sp / sv : obv[i]);
        }
     }
  }

//+------------------------------------------------------------------+
//| Pivot high ketat (toleran sama persis dgn versi Pine)            |
//+------------------------------------------------------------------+
bool IsPivotHigh(const MqlRates &r[], const int center, const int len)
  {
   if(center - len < 0 || center + len >= ArraySize(r))
      return false;
   double cand = r[center].high;
   for(int i = center - len; i <= center + len; i++)
     {
      if(i == center)
         continue;
      if(r[i].high >= cand)
         return false;
     }
   return true;
  }

bool IsPivotLow(const MqlRates &r[], const int center, const int len)
  {
   if(center - len < 0 || center + len >= ArraySize(r))
      return false;
   double cand = r[center].low;
   for(int i = center - len; i <= center + len; i++)
     {
      if(i == center)
         continue;
      if(r[i].low <= cand)
         return false;
     }
   return true;
  }

//+------------------------------------------------------------------+
//| Evaluasi lengkap pada bar yang baru tertutup                     |
//+------------------------------------------------------------------+
void EvaluateClosedBar()
  {
   int minBars = MathMax(InpBarsCalc, MathMax(InpMALen * 4, 300));
   MqlRates r[];
   ArraySetAsSeries(r, false);
   int got = CopyRates(_Symbol, _Period, 1, minBars, r);
   if(got < MathMax(InpMALen + 5, 100))
      return;

   int k = got - 1;              // indeks bar yang baru ditutup
   if(k < InpMALen + 2)
      return;

   double obv[];
   double ma[];
   BuildObvSeries(r, obv);
   BuildMASeries(obv, r, (int)InpMAType, InpMALen, ma);

   double hist[];
   ArrayResize(hist, got);
   for(int i = 0; i < got; i++)
      hist[i] = obv[i] - ma[i];

   // --- crossover (definisi ta.crossover/crossunder Pine)
   bool crossBull = (obv[k] > ma[k] && obv[k - 1] <= ma[k - 1]);
   bool crossBear = (obv[k] < ma[k] && obv[k - 1] >= ma[k - 1]);

   // --- dashboard trend
   g_dashTrend = (obv[k] > ma[k]) ? "BULL" : ((obv[k] < ma[k]) ? "BEAR" : "NETRAL");

   // --- filter HTF: OBV > MA(OBV) di timeframe tinggi
   bool htfBull = true, htfBear = true;
   if(InpUseHTF)
     {
      MqlRates hr[];
      ArraySetAsSeries(hr, false);
      int hgot = CopyRates(_Symbol, InpHTF, 1, InpMALen * 4 + 10, hr);
      if(hgot < InpMALen + 3)
        {
         Print("Data HTF belum cukup, sinyal dilewati");
         return;
        }
      double hobv[], hma[];
      BuildObvSeries(hr, hobv);
      BuildMASeries(hobv, hr, (int)InpMAType, InpMALen, hma);
      int hk = hgot - 1;
      htfBull = (hobv[hk] > hma[hk]);
      htfBear = !htfBull;
     }

   // --- filter ADX
   double adxVal = 0.0;
   bool adxOk = true;
   if(InpUseADX && g_adxHandle != INVALID_HANDLE)
     {
      double abuf[];
      ArraySetAsSeries(abuf, true);
      if(CopyBuffer(g_adxHandle, 0, 1, 1, abuf) < 1)
         return;
      adxVal = abuf[0];
      adxOk = (adxVal >= InpADXMin);
     }
   g_dashADX = adxVal;

   // --- filter volume
   double volRatio = 1.0;
   bool volOk = true;
   if(InpUseVolFilter)
     {
      double svol = 0;
      if(k - InpVolLen + 1 < 0)
         return;
      for(int j = k - InpVolLen + 1; j <= k; j++)
         svol += (double)r[j].tick_volume;
      double volAvg = svol / InpVolLen;
      volRatio = (volAvg > 0 ? (double)r[k].tick_volume / volAvg : 0.0);
      volOk = ((double)r[k].tick_volume >= volAvg * InpVolMult);
     }
   g_dashVolR = volRatio;

   // --- update pelacak divergensi (info dashboard)
   UpdateDivergenceState(r, hist, k);

   // --- gabungkan sinyal
   bool longSignal  = (crossBull && (!InpUseHTF || htfBull) && adxOk && volOk);
   bool shortSignal = (crossBear && (!InpUseHTF || htfBear) && adxOk && volOk);

   if(!longSignal && !shortSignal)
      return;

   // --- level trade (identik rumus indikator)
   double atrVal = 0.0;
   double tbuf[];
   ArraySetAsSeries(tbuf, true);
   if(CopyBuffer(g_atrHandle, 0, 1, 1, tbuf) < 1)
      return;
   atrVal = tbuf[0];

   double entryBase = (InpEntryMode == ENTRY_PREV_CLOSE ? r[k - 1].close : r[k].close);
   double slDist = atrVal * InpSLMult;
   if(slDist <= 0)
      return;

   if(longSignal)
     {
      g_evalEntry = entryBase;
      g_evalSL    = entryBase - slDist;
      g_evalTP1   = entryBase + slDist * InpTP1RR;
      g_evalTP2   = entryBase + slDist * InpTP2RR;
      g_evalTP3   = entryBase + slDist * InpTP3RR;
      ExecuteSignal(true, "OBV-LONG");
     }
   else
     {
      g_evalEntry = entryBase;
      g_evalSL    = entryBase + slDist;
      g_evalTP1   = entryBase - slDist * InpTP1RR;
      g_evalTP2   = entryBase - slDist * InpTP2RR;
      g_evalTP3   = entryBase - slDist * InpTP3RR;
      ExecuteSignal(false, "OBV-SHORT");
     }
  }

//+------------------------------------------------------------------+
//| Divergensi (info dashboard + log)                                |
//+------------------------------------------------------------------+
void UpdateDivergenceState(const MqlRates &r[], const double &hist[], const int k)
  {
   int dl = 5; // sesuai default Div Piv indikator
   int center = k - dl;
   if(center - dl < 0)
      return;

   if(IsPivotHigh(r, center, dl))
     {
      g_prevPH = g_lastPH;      g_prevPHobvH = g_lastPHobvH;
      g_hasPrevPH = g_hasPH;
      g_lastPH = r[center].high;
      g_lastPHobvH = hist[center];
      g_hasPH = true;

      if(g_hasPrevPH)
        {
         if(g_lastPH > g_prevPH && g_lastPHobvH < g_prevPHobvH)
           { g_dashDiv = "BearDiv"; Print("Divergence: BEARISH (regular)"); }
         else if(g_lastPH < g_prevPH && g_lastPHobvH > g_prevPHobvH)
           { g_dashDiv = "HidBearDiv"; Print("Divergence: BEARISH (hidden)"); }
        }
     }

   if(IsPivotLow(r, center, dl))
     {
      g_prevPL = g_lastPL;      g_prevPLobvH = g_lastPLobvH;
      g_hasPrevPL = g_hasPL;
      g_lastPL = r[center].low;
      g_lastPLobvH = hist[center];
      g_hasPL = true;

      if(g_hasPrevPL)
        {
         if(g_lastPL < g_prevPL && g_lastPLobvH > g_prevPLobvH)
           { g_dashDiv = "BullDiv"; Print("Divergence: BULLISH (regular)"); }
         else if(g_lastPL > g_prevPL && g_lastPLobvH < g_prevPLobvH)
           { g_dashDiv = "HidBullDiv"; Print("Divergence: BULLISH (hidden)"); }
        }
     }
  }

//+------------------------------------------------------------------+
//| Eksekusi sinyal                                                  |
//+------------------------------------------------------------------+
void ExecuteSignal(const bool isBuy, const string tag)
  {
   // tutup posisi lawan dulu
   CloseAllDir(isBuy ? POSITION_TYPE_SELL : POSITION_TYPE_BUY, tag + "-REV");

   if(TotalOwn() >= InpMaxPositions)
     {
      Print(tag, ": posisi sudah maksimal, skip");
      return;
     }
   if(!TimeAllowed() || !SpreadOk())
      return;

   OpenWithLevels(isBuy, tag);

   if(InpPushNotify)
      SendNotification("OBV Native " + tag + " " + _Symbol +
                       " entry=" + DoubleToString(g_evalEntry, (int)msym.Digits()));
  }

//+------------------------------------------------------------------+
//| Cek spread                                                       |
//+------------------------------------------------------------------+
bool SpreadOk()
  {
   if(InpMaxSpreadPoints <= 0)
      return true;
   long spr = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   if(spr > InpMaxSpreadPoints)
     {
      Print("Spread terlalu lebar: ", spr, " pts");
      return false;
     }
   return true;
  }

//+------------------------------------------------------------------+
//| Filter jam server                                                |
//+------------------------------------------------------------------+
bool TimeAllowed()
  {
   if(!InpUseTimeFilter)
      return true;
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   if(InpStartHour <= InpEndHour)
      return (dt.hour >= InpStartHour && dt.hour < InpEndHour);
   return (dt.hour >= InpStartHour || dt.hour < InpEndHour);
  }

//+------------------------------------------------------------------+
//| Lot                                                              |
//+------------------------------------------------------------------+
double NormalizeLot(double lot)
  {
   double minLot = msym.LotsMin();
   double maxLot = MathMin(msym.LotsMax(), InpMaxLot);
   double step   = msym.LotsStep();

   if(step > 0)
      lot = MathFloor(lot / step + 0.0000001) * step;

   lot = MathMax(minLot, MathMin(maxLot, lot));
   return NormalizeDouble(lot, 2);
  }

double CalcLots(const double entry, const double sl)
  {
   if(InpLotMode == LOT_FIXED_X)
      return NormalizeLot(InpFixedLot);

   double dist = MathAbs(entry - sl);
   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);

   if(dist <= 0 || tickSize <= 0 || tickValue <= 0)
      return NormalizeLot(InpFixedLot);

   double ticks      = dist / tickSize;
   double lossPerLot = ticks * tickValue;
   double money      = AccountInfoDouble(ACCOUNT_BALANCE) * InpRiskPercent / 100.0;

   if(lossPerLot <= 0)
      return NormalizeLot(InpFixedLot);

   return NormalizeLot(money / lossPerLot);
  }

//+------------------------------------------------------------------+
//| Posisi                                                           |
//+------------------------------------------------------------------+
int CountDir(const ENUM_POSITION_TYPE dir)
  {
   int cnt = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE) == dir)
         cnt++;
     }
   return cnt;
  }

int TotalOwn() { return CountDir(POSITION_TYPE_BUY) + CountDir(POSITION_TYPE_SELL); }

//+------------------------------------------------------------------+
//| Buka posisi dgn level hasil evaluasi                             |
//+------------------------------------------------------------------+
void OpenWithLevels(const bool isBuy, const string tag)
  {
   double sl      = NormalizeDouble(g_evalSL,  (int)msym.Digits());
   double tpFinal = NormalizeDouble(g_evalTP3, (int)msym.Digits());
   double lots    = CalcLots(g_evalEntry, g_evalSL);

   if(lots < msym.LotsMin())
     {
      Print(tag, ": lot terlalu kecil");
      return;
     }

   bool ok = isBuy
             ? trade.Buy(lots, _Symbol, 0.0, sl, tpFinal, tag)
             : trade.Sell(lots, _Symbol, 0.0, sl, tpFinal, tag);

   uint rc = trade.ResultRetcode();
   if(!ok || (rc != TRADE_RETCODE_DONE && rc != TRADE_RETCODE_PLACED && rc != TRADE_RETCODE_DONE_PARTIAL))
     {
      Print(tag, ": open dgn SL/TP gagal rc=", rc, " -> coba tanpa stops");
      ok = isBuy
           ? trade.Buy(lots, _Symbol, 0.0, 0.0, 0.0, tag)
           : trade.Sell(lots, _Symbol, 0.0, 0.0, 0.0, tag);
      rc = trade.ResultRetcode();
      if(ok && (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_PLACED))
        {
         for(int i = PositionsTotal() - 1; i >= 0; i--)
           {
            ulong ticket = PositionGetTicket(i);
            if(ticket == 0) continue;
            if(PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;
            if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
            if(PositionGetDouble(POSITION_SL) == 0.0)
               trade.PositionModify(ticket, sl, tpFinal);
           }
        }
      else
        {
         Print(tag, ": open gagal total rc=", rc, " ", trade.ResultRetcodeDescription());
         return;
        }
     }

   Print(tag, " OK | lot=", DoubleToString(lots, 2),
         " entry=", DoubleToString(g_evalEntry, (int)msym.Digits()),
         " sl=", DoubleToString(sl, (int)msym.Digits()),
         " tp=", DoubleToString(tpFinal, (int)msym.Digits()));

   // simpan level partial per ticket
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      string base = GV_PREFIX + IntegerToString(InpMagicNumber) + "_" + IntegerToString((long)ticket) + "_";
      if(GlobalVariableCheck(base + "stage"))
         continue;
      GlobalVariableSet(base + "stage", 0.0);
      GlobalVariableSet(base + "tp1", g_evalTP1);
      GlobalVariableSet(base + "tp2", g_evalTP2);
     }
  }

//+------------------------------------------------------------------+
//| GV helpers                                                       |
//+------------------------------------------------------------------+
string GVBase(const ulong ticket)
  {
   return GV_PREFIX + IntegerToString(InpMagicNumber) + "_" + IntegerToString((long)ticket) + "_";
  }

double GetGV(const ulong ticket, const string field, const double defval)
  {
   string name = GVBase(ticket) + field;
   if(GlobalVariableCheck(name))
      return GlobalVariableGet(name);
   return defval;
  }

//+------------------------------------------------------------------+
//| Kelola posisi berjalan                                           |
//+------------------------------------------------------------------+
void ManagePositions()
  {
   double point = msym.Point();
   double bid = msym.Bid();
   double ask = msym.Ask();

   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;

      ENUM_POSITION_TYPE ptype = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      double vol     = PositionGetDouble(POSITION_VOLUME);
      double openprc = PositionGetDouble(POSITION_PRICE_OPEN);
      double curSL   = PositionGetDouble(POSITION_SL);
      double curTP   = PositionGetDouble(POSITION_TP);

      double stage  = GetGV(ticket, "stage", 0.0);
      double tpLvl1 = GetGV(ticket, "tp1", 0.0);
      double tpLvl2 = GetGV(ticket, "tp2", 0.0);

      if(ptype == POSITION_TYPE_BUY)
        {
         if(stage < 1 && tpLvl1 > 0 && bid >= tpLvl1)
           {
            DoPartial(ticket, vol, InpTP1ClosePct, "TP1");
            GlobalVariableSet(GVBase(ticket) + "stage", 1.0);
            stage = 1;
            if(InpBEAfterTP1)
              {
               double be = NormalizeDouble(openprc + 2 * point, (int)msym.Digits());
               if(be > curSL)
                 {
                  trade.PositionModify(ticket, be, curTP);
                  curSL = be;
                 }
              }
           }
         if(stage < 2 && InpPartialTP2 && tpLvl2 > 0 && bid >= tpLvl2)
           {
            DoPartial(ticket, vol, InpTP2ClosePct, "TP2");
            GlobalVariableSet(GVBase(ticket) + "stage", 2.0);
            stage = 2;
           }
         if(stage >= 2 && InpTrailAfterTP2)
           {
            double newSL = NormalizeDouble(bid - InpTrailDistPts * point, (int)msym.Digits());
            if(newSL > curSL + point)
               trade.PositionModify(ticket, newSL, curTP);
           }
        }
      else
        {
         if(stage < 1 && tpLvl1 > 0 && ask <= tpLvl1)
           {
            DoPartial(ticket, vol, InpTP1ClosePct, "TP1");
            GlobalVariableSet(GVBase(ticket) + "stage", 1.0);
            stage = 1;
            if(InpBEAfterTP1)
              {
               double be = NormalizeDouble(openprc - 2 * point, (int)msym.Digits());
               if(curSL == 0.0 || be < curSL)
                 {
                  trade.PositionModify(ticket, be, curTP);
                  curSL = be;
                 }
              }
           }
         if(stage < 2 && InpPartialTP2 && tpLvl2 > 0 && ask <= tpLvl2)
           {
            DoPartial(ticket, vol, InpTP2ClosePct, "TP2");
            GlobalVariableSet(GVBase(ticket) + "stage", 2.0);
            stage = 2;
           }
         if(stage >= 2 && InpTrailAfterTP2)
           {
            double newSL = NormalizeDouble(ask + InpTrailDistPts * point, (int)msym.Digits());
            if(newSL < curSL - point || curSL == 0.0)
               trade.PositionModify(ticket, newSL, curTP);
           }
        }
     }
  }

//+------------------------------------------------------------------+
//| Partial close aman                                               |
//+------------------------------------------------------------------+
void DoPartial(const ulong ticket, double vol, const double pct, const string tag)
  {
   if(pct <= 0 || vol <= 0)
      return;

   double part = vol * pct / 100.0;
   double step = msym.LotsStep();
   double minL = msym.LotsMin();

   if(step > 0)
      part = MathFloor(part / step + 0.0000001) * step;

   if(part < minL)
      return;
   if(vol - part < minL)
      return;

   if(trade.PositionClosePartial(ticket, NormalizeDouble(part, 2)))
      Print(tag, " partial OK: ", DoubleToString(part, 2), " lot #", ticket);
   else
      Print(tag, " partial GAGAL rc=", trade.ResultRetcode());
  }

//+------------------------------------------------------------------+
//| Tutup posisi                                                     |
//+------------------------------------------------------------------+
void CloseAllDir(const ENUM_POSITION_TYPE dir, const string reason)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE) != dir) continue;
      if(trade.PositionClose(ticket))
         Print(reason, ": close #", ticket);
      else
         Print(reason, ": GAGAL close #", ticket, " rc=", trade.ResultRetcode());
     }
  }

void CloseAllOwn(const string reason)
  {
   CloseAllDir(POSITION_TYPE_BUY, reason);
   CloseAllDir(POSITION_TYPE_SELL, reason);
  }

//+------------------------------------------------------------------+
//| Bersihkan GV ticket tertutup                                     |
//+------------------------------------------------------------------+
void CleanupStageVars()
  {
   static datetime lastRun = 0;
   if(TimeCurrent() - lastRun < 10)
      return;
   lastRun = TimeCurrent();

   string prefix = GV_PREFIX + IntegerToString(InpMagicNumber) + "_";
   int total = GlobalVariablesTotal();
   for(int i = total - 1; i >= 0; i--)
     {
      string name = GlobalVariableName(i);
      if(StringFind(name, prefix) != 0)
         continue;

      string parts[];
      int n = StringSplit(name, '_', parts);
      if(n < 3)
         continue;

      ulong ticket = (ulong)StringToInteger(parts[2]);
      bool stillOpen = false;
      for(int p = PositionsTotal() - 1; p >= 0; p--)
        {
         if(PositionGetTicket(p) == ticket)
           {
            stillOpen = true;
            break;
           }
        }
      if(!stillOpen)
         GlobalVariableDel(name);
     }
  }

//+------------------------------------------------------------------+
//| Dashboard                                                        |
//+------------------------------------------------------------------+
void UpdateComment()
  {
   int nb = CountDir(POSITION_TYPE_BUY);
   int ns = CountDir(POSITION_TYPE_SELL);
   g_dashDir = (nb > 0 ? "LONG x" + IntegerToString(nb) :
                ns > 0 ? "SHORT x" + IntegerToString(ns) : "FLAT");

   Comment("OBV Confluence Native | ", _Symbol, " ", EnumToString(_Period),
           "\nTrend OBV : ", g_dashTrend,
           "\nADX       : ", DoubleToString(g_dashADX, 1),
           "\nVol Ratio : ", DoubleToString(g_dashVolR, 2),
           "\nDivergensi: ", g_dashDiv,
           "\nPosisi    : ", g_dashDir,
           "\nStatus    : ", g_halted ? "HALTED (DD)" : "AKTIF");
  }
//+------------------------------------------------------------------+
