//+------------------------------------------------------------------+
//|                                                OBV_SignalEA.mq5  |
//|  Eksekusi otomatis sinyal dari indikator TradingView             |
//|  "OBV Signal Confluence [MarkitTick]"                            |
//|  Alur: TradingView alert() JSON -> bridge Python -> file JSON    |
//|        di folder MQL5\Files\OBV_Signals -> EA baca & eksekusi    |
//+------------------------------------------------------------------+
#property copyright "OBV Signal Confluence Integration"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\SymbolInfo.mqh>

CTrade         trade;
CPositionInfo  mpos;
CSymbolInfo    msym;

//--- enum mode lot
enum ENUM_LOT_MODE
  {
   LOT_FIXED = 0,      // Lot Tetap
   LOT_RISK_PCT = 1    // % Risiko dari Balance
  };

//=== Sumber Sinyal =================================================
input string InpSignalFolder     = "OBV_Signals"; // Folder di dalam MQL5\Files
input bool   InpDeleteAfterRead  = true;          // Hapus file setelah diproses
input long   InpMagicNumber      = 12350;         // Magic number
input int    InpSlippagePoints   = 30;            // Slippage maksimal (points)
input double InpMaxSpreadPoints  = 60;            // Spread maksimal (points, 0=nonaktif)
input string InpTickerFilter     = "";            // Filter ticker payload (mis. XAUUSD, kosong=semua)
input string InpTFFilter         = "";            // Filter timeframe payload (mis. 5, kosong=semua)
input string InpWebhookToken     = "";            // Token wajib di payload (kosong=nonaktif)
input int    InpMinSecBetwSignal = 5;             // Jeda minimal antar sinyal (anti duplikat)

//=== Lot & Risiko ==================================================
input ENUM_LOT_MODE InpLotMode   = LOT_FIXED;    // Mode penentuan lot
input double InpFixedLot         = 0.01;         // Lot tetap
input double InpRiskPercent      = 0.5;          // % balance per trade (mode risiko)
input double InpMaxLot           = 0.10;         // Batas lot maksimal per order

//=== SL / TP =======================================================
input bool   InpUsePayloadSLTP   = true;         // Pakai Entry/SL/TP dari payload indikator
input int    InpFallbackSLPts    = 300;          // SL cadangan (points) jika payload kosong
input int    InpFallbackTPPts    = 600;          // TP cadangan (points) jika payload kosong

//=== Manajemen Posisi ==============================================
input bool   InpCloseOnOpposite  = true;         // Tutup posisi saat sinyal berlawanan
input int    InpMaxPositions     = 1;            // Maksimal posisi terbuka bersamaan
input bool   InpPartialTP1       = true;         // Partial close di TP1
input double InpTP1ClosePct      = 50.0;         // % volume ditutup di TP1
input bool   InpBEAfterTP1       = true;         // Geser SL ke breakeven setelah TP1
input bool   InpPartialTP2       = true;         // Partial close di TP2
input double InpTP2ClosePct      = 30.0;         // % volume ditutup di TP2
input bool   InpTrailAfterTP2    = true;         // Trailing stop setelah TP2
input int    InpTrailDistPts     = 250;          // Jarak trailing stop (points)

//=== Filter Waktu ==================================================
input bool   InpUseTimeFilter    = false;        // Aktifkan filter jam trading
input int    InpStartHour        = 1;            // Jam mulai (waktu server)
input int    InpEndHour          = 23;           // Jam selesai (waktu server)
input bool   InpCloseFriday      = false;        // Tutup semua menjelang akhir Jumat
input int    InpFridayCloseHour  = 20;           // Jam tutup Jumat (waktu server)

//=== Keamanan ======================================================
input double InpMaxDrawdownPct   = 5.0;          // Hard stop jika DD equity > % (restart EA utk lanjut)

//=== State global ==================================================
double   g_eqPeak        = 0.0;
bool     g_halted        = false;
datetime g_lastExecTime  = 0;

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

   g_eqPeak       = AccountInfoDouble(ACCOUNT_EQUITY);
   g_halted       = false;
   g_lastExecTime = 0;

   EventSetMillisecondTimer(500);
   Print("OBV_SignalEA aktif pada ", _Symbol, " | folder sinyal: ", InpSignalFolder);
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
//| OnDeinit                                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();
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
      Comment("OBV EA: HALT (drawdown)\nRestart EA untuk melanjutkan");
      return;
     }

   ProcessSignalFiles();
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
         Print("HALT: drawdown ", DoubleToString(ddPct, 2), "% >= ", DoubleToString(InpMaxDrawdownPct, 2), "%");
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
//| Filter jam server                                                 |
//+------------------------------------------------------------------+
bool TimeAllowed()
  {
   if(!InpUseTimeFilter)
      return true;
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   if(InpStartHour <= InpEndHour)
      return (dt.hour >= InpStartHour && dt.hour < InpEndHour);
   return (dt.hour >= InpStartHour || dt.hour < InpEndHour); // lintas tengah malam
  }

//+------------------------------------------------------------------+
//| Scan folder sinyal & proses tiap file JSON                       |
//+------------------------------------------------------------------+
void ProcessSignalFiles()
  {
   string fname = "";
   string filter = InpSignalFolder + "\\*.json";
   long fh = FileFindFirst(filter, fname);
   if(fh == INVALID_HANDLE)
      return;

   do
     {
      string path = fname;
      if(StringFind(path, InpSignalFolder + "\\") != 0)
         path = InpSignalFolder + "\\" + fname;
      HandleSignalFile(path);
     }
   while(FileFindNext(fh, fname));

   FileFindClose(fh);
  }

//+------------------------------------------------------------------+
//| Baca satu file payload lalu eksekusi                             |
//+------------------------------------------------------------------+
void HandleSignalFile(const string path)
  {
   int h = FileOpen(path, FILE_READ | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE)
     {
      Print("Gagal buka file: ", path, " err=", GetLastError());
      return;
     }

   string js = "";
   while(!FileIsEnding(h))
     {
      js += FileReadString(h);
      if(!FileIsEnding(h))
         js += " ";
     }
   FileClose(h);

   StringTrimLeft(js);
   StringTrimRight(js);

   if(StringLen(js) < 2 || StringGetCharacter(js, 0) != '{')
     {
      if(InpDeleteAfterRead)
         FileDelete(path);
      return;
     }

   ExecutePayload(js);

   if(InpDeleteAfterRead)
      FileDelete(path);
  }

//+------------------------------------------------------------------+
//| Helper JSON: ambil nilai string per key                          |
//+------------------------------------------------------------------+
string GetJsonStr(const string js, const string key)
  {
   string pat = "\"" + key + "\":\"";
   int p = StringFind(js, pat);
   if(p < 0)
      return "";
   p += StringLen(pat);
   int e = StringFind(js, "\"", p);
   if(e < 0)
      return "";
   return StringSubstr(js, p, e - p);
  }

double GetJsonNum(const string js, const string key)
  {
   string s = GetJsonStr(js, key);
   if(s == "")
      return 0.0;
   return StringToDouble(s);
  }

//+------------------------------------------------------------------+
//| Validasi payload lalu dispatch aksi                              |
//+------------------------------------------------------------------+
void ExecutePayload(const string js)
  {
   // token
   if(InpWebhookToken != "" && GetJsonStr(js, "token") != InpWebhookToken)
     {
      Print("Sinyal DITOLAK: token tidak cocok");
      return;
     }

   // filter ticker / timeframe (pencarian longgar)
   if(InpTickerFilter != "" && StringFind(GetJsonStr(js, "ticker"), InpTickerFilter) < 0)
      return;
   if(InpTFFilter != "" && GetJsonStr(js, "tf") != InpTFFilter)
      return;

   string action = GetJsonStr(js, "action");
   StringToLower(action);

   if(action == "")
     {
      Print("Payload tanpa action: ", js);
      return;
     }

   // anti duplikat
   if(TimeCurrent() - g_lastExecTime < InpMinSecBetwSignal)
     {
      Print("Sinyal dilewati (jeda anti-duplikat): ", action);
      return;
     }

   if(g_halted)
     {
      Print("Sinyal diabaikan, EA halted: ", action);
      return;
     }

   double entry = GetJsonNum(js, "entry");
   double sl    = GetJsonNum(js, "sl");
   double tp1   = GetJsonNum(js, "tp1");
   double tp2   = GetJsonNum(js, "tp2");
   double tp3   = GetJsonNum(js, "tp3");

   if(action == "long")
     {
      if(InpCloseOnOpposite)
         CloseAllDir(POSITION_TYPE_SELL, "OPPOSITE");
      TryOpen(true, entry, sl, tp1, tp2, tp3, "OBV-LONG");
     }
   else if(action == "short")
     {
      if(InpCloseOnOpposite)
         CloseAllDir(POSITION_TYPE_BUY, "OPPOSITE");
      TryOpen(false, entry, sl, tp1, tp2, tp3, "OBV-SHORT");
     }
   else if(action == "closelong")
      CloseAllDir(POSITION_TYPE_BUY, "CLOSELONG");
   else if(action == "closeshort")
      CloseAllDir(POSITION_TYPE_SELL, "CLOSESHORT");
   else if(action == "tp1")
      AdvanceStageTo(1);
   else if(action == "tp2")
      AdvanceStageTo(2);
   else if(action == "tp3" && InpUsePayloadSLTP)
      CloseAllOwn("TP3");
   else
      Print("Action tidak dikenal: ", action);
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
//| Hitung lot                                                       |
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

double CalcLots(double entry, double sl)
  {
   if(InpLotMode == LOT_FIXED)
      return NormalizeLot(InpFixedLot);

   double dist = MathAbs(entry - sl);
   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);

   if(dist <= 0 || tickSize <= 0 || tickValue <= 0)
     {
      Print("Data tick tidak valid, fallback ke lot tetap");
      return NormalizeLot(InpFixedLot);
     }

   double ticks    = dist / tickSize;
   double lossPerLot = ticks * tickValue;
   double money    = AccountInfoDouble(ACCOUNT_BALANCE) * InpRiskPercent / 100.0;

   if(lossPerLot <= 0)
      return NormalizeLot(InpFixedLot);

   return NormalizeLot(money / lossPerLot);
  }

//+------------------------------------------------------------------+
//| Hitung posisi terbuka milik EA ini                               |
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

int TotalOwn()
  {
   return CountDir(POSITION_TYPE_BUY) + CountDir(POSITION_TYPE_SELL);
  }

//+------------------------------------------------------------------+
//| Buka posisi dengan SL/TP dari payload (fallback bila kosong)     |
//+------------------------------------------------------------------+
void TryOpen(const bool isBuy, double entry, double sl,
             const double tp1, const double tp2, const double tp3,
             const string tag)
  {
   if(TotalOwn() >= InpMaxPositions)
     {
      Print(tag, ": jumlah posisi sudah maksimal (", TotalOwn(), ")");
      return;
     }
   if(!TimeAllowed() || !SpreadOk())
      return;

   double ask = msym.Ask();
   double bid = msym.Bid();
   double px  = isBuy ? ask : bid;

   if(sl <= 0 || entry <= 0)
     {
      entry = px;
      double off = InpFallbackSLPts * msym.Point();
      sl = isBuy ? px - off : px + off;
     }

   double tpFinal = tp3;
   if(tpFinal <= 0)
     {
      double risk = MathAbs(entry - sl);
      if(risk <= 0)
         risk = InpFallbackTPPts * msym.Point();
      tpFinal = isBuy ? entry + risk : entry - risk;
     }

   sl       = NormalizeDouble(sl, (int)msym.Digits());
   tpFinal  = NormalizeDouble(tpFinal, (int)msym.Digits());
   double lots = CalcLots(entry, sl);
   if(lots < msym.LotsMin())
     {
      Print(tag, ": lot terlalu kecil setelah normalisasi");
      return;
     }

   bool ok = isBuy
             ? trade.Buy(lots, _Symbol, 0.0, sl, tpFinal, tag)
             : trade.Sell(lots, _Symbol, 0.0, sl, tpFinal, tag);

   uint rc = trade.ResultRetcode();
   if(!ok || (rc != TRADE_RETCODE_DONE && rc != TRADE_RETCODE_PLACED && rc != TRADE_RETCODE_DONE_PARTIAL))
     {
      Print(tag, ": open dengan SL/TP gagal rc=", rc, " -> coba tanpa SL/TP lalu modify");
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

   g_lastExecTime = TimeCurrent();
   Print(tag, " OK | lot=", DoubleToString(lots, 2),
         " entry=", DoubleToString(entry, (int)msym.Digits()),
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
      GlobalVariableSet(base + "tp1", tp1 > 0 ? tp1 : (isBuy ? entry + MathAbs(entry - sl) : entry - MathAbs(entry - sl)));
      GlobalVariableSet(base + "tp2", tp2 > 0 ? tp2 : (isBuy ? entry + 2 * MathAbs(entry - sl) : entry - 2 * MathAbs(entry - sl)));
     }
  }

//+------------------------------------------------------------------+
//| Stage GV helpers                                                 |
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
//| Kelola posisi: partial TP1/TP2, BE, trailing                     |
//+------------------------------------------------------------------+
void ManagePositions()
  {
   if(!InpUsePayloadSLTP)
      return; // mode SL/TP fix: biarkan broker yang mengeksekusi

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
      double vol    = PositionGetDouble(POSITION_VOLUME);
      double openprc= PositionGetDouble(POSITION_PRICE_OPEN);
      double curSL  = PositionGetDouble(POSITION_SL);
      double curTP  = PositionGetDouble(POSITION_TP);

      double stage = GetGV(ticket, "stage", 0.0);
      double tpLvl1 = GetGV(ticket, "tp1", 0.0);
      double tpLvl2 = GetGV(ticket, "tp2", 0.0);

      if(ptype == POSITION_TYPE_BUY)
        {
         if(stage < 1 && tpLvl1 > 0 && bid >= tpLvl1)
           {
            DoPartial(ticket, vol, InpTP1ClosePct, "TP1");
            stage = 1;
            GlobalVariableSet(GVBase(ticket) + "stage", stage);
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
            stage = 2;
            GlobalVariableSet(GVBase(ticket) + "stage", stage);
           }
         if(stage >= 2 && InpTrailAfterTP2)
           {
            double newSL = NormalizeDouble(bid - InpTrailDistPts * point, (int)msym.Digits());
            if(newSL > curSL + point)
               trade.PositionModify(ticket, newSL, curTP);
           }
        }
      else // SELL
        {
         if(stage < 1 && tpLvl1 > 0 && ask <= tpLvl1)
           {
            DoPartial(ticket, vol, InpTP1ClosePct, "TP1");
            stage = 1;
            GlobalVariableSet(GVBase(ticket) + "stage", stage);
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
            stage = 2;
            GlobalVariableSet(GVBase(ticket) + "stage", stage);
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
//| Partial close aman (sisa volume harus >= min lot)                |
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
     {
      Print(tag, ": sisa lot < minlot, skip partial (biarkan TP akhir)");
      return;
     }

   if(trade.PositionClosePartial(ticket, NormalizeDouble(part, 2)))
      Print(tag, " partial OK: ", DoubleToString(part, 2), " lot dari ticket ", ticket);
   else
      Print(tag, " partial GAGAL rc=", trade.ResultRetcode(), " ", trade.ResultRetcodeDescription());
  }

//+------------------------------------------------------------------+
//| Terima aksi tp1/tp2 dari payload: dorong stage                   |
//+------------------------------------------------------------------+
void AdvanceStageTo(const int level)
  {
   if(level == 1)
     {
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0) continue;
         if(PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;
         if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
         if(GetGV(ticket, "stage", 0.0) < 1)
           {
            DoPartial(ticket, PositionGetDouble(POSITION_VOLUME), InpTP1ClosePct, "TP1(alert)");
            GlobalVariableSet(GVBase(ticket) + "stage", 1.0);
           }
        }
     }
   else if(level == 2)
     {
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0) continue;
         if(PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;
         if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
         if(GetGV(ticket, "stage", 0.0) < 2)
           {
            DoPartial(ticket, PositionGetDouble(POSITION_VOLUME), InpTP2ClosePct, "TP2(alert)");
            GlobalVariableSet(GVBase(ticket) + "stage", 2.0);
           }
        }
     }
  }

//+------------------------------------------------------------------+
//| Tutup semua posisi milik EA                                      |
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
         Print(reason, ": close ticket ", ticket);
      else
         Print(reason, ": GAGAL close ticket ", ticket, " rc=", trade.ResultRetcode());
     }
   g_lastExecTime = TimeCurrent();
  }

void CloseAllOwn(const string reason)
  {
   CloseAllDir(POSITION_TYPE_BUY, reason);
   CloseAllDir(POSITION_TYPE_SELL, reason);
  }

//+------------------------------------------------------------------+
//| Bersihkan GV milik ticket yang sudah tertutup                    |
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
//| Dashboard di chart                                               |
//+------------------------------------------------------------------+
void UpdateComment()
  {
   string dir = "FLAT";
   int nb = CountDir(POSITION_TYPE_BUY);
   int ns = CountDir(POSITION_TYPE_SELL);
   if(nb > 0) dir = "LONG x" + IntegerToString(nb);
   else if(ns > 0) dir = "SHORT x" + IntegerToString(ns);

   Comment("OBV Signal EA  |  ", _Symbol,
           "\nStatus : ", g_halted ? "HALTED (DD)" : "AKTIF",
           "\nPosisi : ", dir,
           "\nSpread : ", IntegerToString(SymbolInfoInteger(_Symbol, SYMBOL_SPREAD)), " pts",
           "\nFile   : MQL5\\Files\\", InpSignalFolder);
  }
//+------------------------------------------------------------------+
