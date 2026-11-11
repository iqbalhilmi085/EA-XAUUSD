//+------------------------------------------------------------------+
//|                                            Project5_Trend_v3.mq5 |
//|  XAUUSD M1 trend-following scalper                               |
//|  - Filter tren: EMA fast/slow di M5                              |
//|  - Trigger: penutupan M1 menembus Donchian N-bar                 |
//|  - TP = RR x SL (asimetris, khas sistem tren)                    |
//|  - SL = max(ATRmult x ATR(M5), floor spread) + clamp broker      |
//|  - Disiplin: lock harian (profit/loss), cooldown pasca-SL,       |
//|    batas entry/hari, filter spread, isolasi magic number         |
//+------------------------------------------------------------------+
#property copyright "Project 5%"
#property version   "3.00"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\SymbolInfo.mqh>

//============================ INPUT ================================
input group "== Identitas =="
input long              InpMagicNumber     = 55300;
input int               InpSlippagePoints  = 10;

input group "== Uang (ruang optimasi) =="
input double            InpLotSize         = 0.01;    // Lot awal
input double            InpDailyProfitPct  = 2.0;     // Lock profit harian (% ekuitas)
input double            InpDailyMaxLossPct = 2.0;     // Cut loss harian (% ekuitas)

input group "== Sinyal tren =="
input int               InpEMAFastM5       = 20;      // EMA cepat (M5)
input int               InpEMASlowM5       = 50;      // EMA lambat (M5)
input int               InpBreakoutBars    = 20;      // Donchian M1: N bar
input int               InpATRPeriodM5     = 14;      // Periode ATR (M5)
input double            InpATRMult         = 1.0;     // SL = mult x ATR(M5)
input double            InpTP_RR           = 1.5;     // TP = RR x SL
input double            InpTrendMinSepPips = 0.0;     // Min jarak EMA fast-slow M5 (pip, 0=off)

input group "== Disiplin =="
input double            InpGlobalKillDDPct = 25.0;    // Kill-switch: DD maks dari puncak ekuitas (%)
input int               InpCooldownMin     = 5;       // Jeda pasca-SL (menit)
input int               InpMaxEntriesPerDay= 10;      // Batas entry per hari
input double            InpMaxSpreadPoints = 20.0;    // Spread maksimum (poin PRD)
input int               InpStartHour       = 0;       // Jam mulai trading (server)
input int               InpEndHour         = 24;      // Jam akhir trading (server)

//=========================== GLOBAL ================================
CTrade        trade;
CSymbolInfo   sym;

datetime g_lastBarTime  = 0;
datetime g_cooldownUntil= 0;
int      g_entriesToday = 0;
double   g_dayStartEquity = 0.0;
bool     g_dayLocked      = false;
string   g_lockReason     = "";
int      g_currentDay     = -1;

int      hEmaFast = INVALID_HANDLE;
int      hEmaSlow = INVALID_HANDLE;
int      hATR     = INVALID_HANDLE;

double   g_mpp      = 0.0;   // uang per point(0.001) per 1.00 lot (lazy)
double   g_capScale = 1.0;   // USC -> unit mata uang akun
double   g_peakEquity = 0.0; // puncak ekuitas utk kill-switch global
bool     g_killed     = false;

//========================== UTILITAS ===============================
double Pip()
{
   return _Point * ((_Digits == 3 || _Digits == 5) ? 10.0 : 1.0);
}

void EnsureHandles()
{
   if(hEmaFast == INVALID_HANDLE)
      hEmaFast = iMA(_Symbol, PERIOD_M5, InpEMAFastM5, 0, MODE_EMA, PRICE_CLOSE);
   if(hEmaSlow == INVALID_HANDLE)
      hEmaSlow = iMA(_Symbol, PERIOD_M5, InpEMASlowM5, 0, MODE_EMA, PRICE_CLOSE);
   if(hATR == INVALID_HANDLE)
      hATR = iATR(_Symbol, PERIOD_M5, InpATRPeriodM5);
}

bool SpreadOK()
{
   double sprPts = (sym.Ask() - sym.Bid()) / Pip();
   return (sprPts <= InpMaxSpreadPoints);
}

int CountMine()
{
   int cnt = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0 && PositionGetInteger(POSITION_MAGIC) == InpMagicNumber
         && PositionGetString(POSITION_SYMBOL) == _Symbol)
         cnt++;
   }
   return cnt;
}

bool CloseAllMine(const string reason)
{
   bool ok = true;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(!trade.PositionClose(ticket))
      {
         ok = false;
         Print("Gagal tutup #", ticket, " err=", trade.ResultRetcode());
      }
   }
   Print("CloseAllMine: ", reason);
   return ok;
}

//---------------- Kalibrasi uang per poin (lazy) -------------------
void Calibrate()
{
   if(g_mpp > 0.0) return;

   double tickVal  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tickVal <= 0.0 || tickSize <= 0.0) return;

   g_mpp = tickVal / tickSize * _Point;

   string accCur = AccountInfoString(ACCOUNT_CURRENCY);
   g_capScale = (accCur == "USD" ? 0.01 : 1.0);

   double mppPip = g_mpp * (Pip() / _Point);

   Print("=== PROBE KALIBRASI ", _Symbol, " (digits=", _Digits,
         ", akun=", accCur, ", capScale=", DoubleToString(g_capScale, 4), ") ===");
   Print("Uang per pip per lot: ", DoubleToString(mppPip, 3),
         " | per 0.01 lot=", DoubleToString(mppPip * 0.01, 4));

   double slMoney = mppPip * InpLotSize *
                    MathMax(1.0, InpATRMult);   // indikatif saja
   Print("Indikatif 1x SL @", DoubleToString(InpLotSize, 2), " lot x ",
         DoubleToString(InpATRMult, 2), " pip ATR ~ ",
         DoubleToString(slMoney, 2), " ", accCur);
}

//---------------- Reset & lock harian (equity-based) ---------------
void DailyResetCheck()
{
   MqlDateTime dt;
   TimeCurrent(dt);
   if(dt.day != g_currentDay)
   {
      g_currentDay     = dt.day;
      g_dayStartEquity = AccountInfoDouble(ACCOUNT_EQUITY);
      g_dayLocked      = false;
      g_lockReason     = "";
      g_entriesToday   = 0;
      g_cooldownUntil  = 0;
      Print("== Hari baru: equity awal ", DoubleToString(g_dayStartEquity, 2),
            " | cap P/L: +", DoubleToString(InpDailyProfitPct, 1), "% / -",
            DoubleToString(InpDailyMaxLossPct, 1), "% = +",
            DoubleToString(g_dayStartEquity * InpDailyProfitPct / 100.0, 2), " / -",
            DoubleToString(g_dayStartEquity * InpDailyMaxLossPct / 100.0, 2), " ==");
   }
}

void CheckDailyLocks()
{
   if(g_dayLocked || g_dayStartEquity <= 0.0) return;

   double dayPnL = AccountInfoDouble(ACCOUNT_EQUITY) - g_dayStartEquity;
   double capProfit = g_dayStartEquity * InpDailyProfitPct / 100.0;
   double capLoss   = g_dayStartEquity * InpDailyMaxLossPct / 100.0;

   if(capProfit > 0 && dayPnL >= capProfit)
   {
      g_dayLocked = true;
      g_lockReason = StringFormat("PROFIT LOCK harian (+%.2f)", dayPnL);
      CloseAllMine(g_lockReason);
      return;
   }
   if(capLoss > 0 && dayPnL <= -capLoss)
   {
      g_dayLocked = true;
      g_lockReason = StringFormat("CUT SWITCH harian (%.2f)", dayPnL);
      CloseAllMine(g_lockReason);
      return;
   }
}

//---------------- Sinyal -------------------------------------------
// 1 = beli, -1 = jual, 0 = diam
int GetSignal()
{
   double emaF[2], emaS[2];
   if(CopyBuffer(hEmaFast, 0, 1, 1, emaF) < 1) return 0;
   if(CopyBuffer(hEmaSlow, 0, 1, 1, emaS) < 1) return 0;

   double c1 = iClose(_Symbol, PERIOD_M1, 1);
   if(c1 <= 0.0) return 0;

   int n = MathMax(5, InpBreakoutBars);
   double hh = iHigh(_Symbol, PERIOD_M1, iHighest(_Symbol, PERIOD_M1, MODE_HIGH, n, 2));
   double ll = iLow (_Symbol, PERIOD_M1, iLowest (_Symbol, PERIOD_M1, MODE_LOW,  n, 2));
   if(hh <= 0.0 || ll <= 0.0) return 0;

   if(emaF[0] <= 0.0 || emaS[0] <= 0.0) return 0;
   if(InpTrendMinSepPips > 0.0 &&
      MathAbs(emaF[0] - emaS[0]) < InpTrendMinSepPips * Pip()) return 0;

   if(emaF[0] > emaS[0] && c1 > hh) return  1;   // tren naik + breakout atas
   if(emaF[0] < emaS[0] && c1 < ll) return -1;   // turun turun + breakout bawah
   return 0;
}

//---------------- Eksekusi -----------------------------------------
void OpenTrade(int dir)
{
   double atr[1];
   double slDist = 0.0;
   if(CopyBuffer(hATR, 0, 1, 1, atr) == 1 && atr[0] > 0.0)
      slDist = InpATRMult * atr[0];

   double spreadDist = sym.Ask() - sym.Bid();
   slDist = MathMax(slDist, spreadDist * 3.0);
   slDist = MathMax(slDist, Pip());                       // minimum 1 pip
   double tpDist = slDist * InpTP_RR;

   double stopsLevel = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   slDist = MathMax(slDist, stopsLevel + _Point);
   tpDist = MathMax(tpDist, stopsLevel + _Point);

   for(int attempt = 0; attempt < 3; attempt++)
   {
      bool ok;
      if(dir > 0)
      {
         double px  = sym.Ask();
         double sl  = NormalizeDouble(px - slDist, _Digits);
         double tp  = NormalizeDouble(px + tpDist, _Digits);
         ok = trade.Buy(InpLotSize, _Symbol, 0.0, sl, tp, "P5-Trend");
      }
      else
      {
         double px  = sym.Bid();
         double sl  = NormalizeDouble(px + slDist, _Digits);
         double tp  = NormalizeDouble(px - tpDist, _Digits);
         ok = trade.Sell(InpLotSize, _Symbol, 0.0, sl, tp, "P5-Trend");
      }

      uint rc = trade.ResultRetcode();
      if(ok && (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_PLACED))
      {
         g_entriesToday++;
         Print("Entry ", (dir > 0 ? "BUY" : "SELL"), " #", g_entriesToday,
               "/", InpMaxEntriesPerDay, " hari ini | SLdist=",
               DoubleToString(slDist / Pip(), 1), " pip TP=",
               DoubleToString(tpDist / Pip(), 1), " pip");
         return;
      }
      if(rc == TRADE_RETCODE_INVALID_STOPS)
      {
         slDist *= 1.5;
         tpDist  = slDist * InpTP_RR;
         continue;
      }
      Print("Gagal entry ", (dir > 0 ? "BUY" : "SELL"),
            " retcode=", rc, " (", trade.ResultRetcodeDescription(), ")");
      return;
   }
}

//---------------- Panel --------------------------------------------
void UpdatePanel()
{
   double dayPnL = (g_dayStartEquity > 0)
                   ? AccountInfoDouble(ACCOUNT_EQUITY) - g_dayStartEquity : 0.0;
   Comment(
      "== Project5 Trend v3 ==\n",
      "Status : ", (g_killed ? "TERHENTI GLOBAL (kill-switch DD)" :
                    (g_dayLocked ? "TERKUNCI (" + g_lockReason + ")" :
                    (CountMine() > 0 ? "POSISI AKTIF" : "MEMANTAU"))), "\n",
      "PnL hari ini: ", DoubleToString(dayPnL, 2), " (",
      DoubleToString(100.0 * dayPnL / MathMax(g_dayStartEquity, 0.01), 2), "%)",
      " (cap +", DoubleToString(InpDailyProfitPct, 1), "%/-",
      DoubleToString(InpDailyMaxLossPct, 1), "%)\n",
      "Entry hari ini: ", g_entriesToday, "/", InpMaxEntriesPerDay, "\n",
      "Spread: ", DoubleToString((sym.Ask() - sym.Bid()) / Pip(), 1), " poin",
      (g_cooldownUntil > TimeCurrent()
        ? "\nCooldown sampai " + TimeToString(g_cooldownUntil, TIME_MINUTES) : ""));
}

//======================== EVENT HANDLER ============================
int OnInit()
{
   if(!sym.Name(_Symbol)) return INIT_FAILED;
   sym.RefreshRates();

   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(InpSlippagePoints);
   trade.SetTypeFillingBySymbol(_Symbol);

   EnsureHandles();

   MqlDateTime dt;
   TimeCurrent(dt);
   g_currentDay     = dt.day;
   g_dayStartEquity = AccountInfoDouble(ACCOUNT_EQUITY);
   g_peakEquity     = g_dayStartEquity;
   g_killed         = false;

   Print("=== Project5 Trend v3 aktif ===");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   Comment("");
   if(hEmaFast != INVALID_HANDLE) IndicatorRelease(hEmaFast);
   if(hEmaSlow != INVALID_HANDLE) IndicatorRelease(hEmaSlow);
   if(hATR     != INVALID_HANDLE) IndicatorRelease(hATR);
}

void OnTick()
{
   Calibrate();
   if(!sym.RefreshRates()) return;

   DailyResetCheck();
   CheckDailyLocks();

   // kill-switch global: berhenti permanen saat DD dari puncak tembus batas
   double eqNow = AccountInfoDouble(ACCOUNT_EQUITY);
   if(eqNow > g_peakEquity) g_peakEquity = eqNow;
   if(!g_killed && g_peakEquity > 0.0 && InpGlobalKillDDPct > 0.0 &&
      eqNow <= g_peakEquity * (1.0 - InpGlobalKillDDPct / 100.0))
   {
      g_killed = true;
      CloseAllMine("GLOBAL KILL");
      Print("KILL-SWITCH AKTIF: puncak=", DoubleToString(g_peakEquity, 2),
            " ekuitas=", DoubleToString(eqNow, 2), " -> EA berhenti permanen sampai re-init");
   }
   if(g_killed)
   {
      UpdatePanel();
      return;
   }

   if(g_dayLocked)
   {
      UpdatePanel();
      return;
   }

   // hanya proses di bar M1 baru
   datetime bt = iTime(_Symbol, PERIOD_M1, 0);
   bool isNewBar = (bt != g_lastBarTime);
   if(isNewBar) g_lastBarTime = bt;

   UpdatePanel();
   if(!isNewBar) return;

   // jam operasional
   MqlDateTime dt;
   TimeCurrent(dt);
   if(dt.hour < InpStartHour || dt.hour >= InpEndHour) return;

   if(TimeCurrent() < g_cooldownUntil) return;
   if(g_entriesToday >= InpMaxEntriesPerDay) return;
   if(!SpreadOK()) return;
   if(CountMine() > 0) return;

   int sig = GetSignal();
   if(sig == 0) return;

   OpenTrade(sig);
}

//---------------- Cooldown otomatis pasca-SL -----------------------
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD) return;

   ulong dealTicket = trans.deal;
   if(dealTicket == 0) return;
   if(!HistoryDealSelect(dealTicket)) return;

   if(HistoryDealGetInteger(dealTicket, DEAL_MAGIC) != InpMagicNumber) return;
   if(HistoryDealGetString(dealTicket, DEAL_SYMBOL) != _Symbol) return;
   if(HistoryDealGetInteger(dealTicket, DEAL_ENTRY) != DEAL_ENTRY_OUT) return;

   ENUM_DEAL_REASON reason = (ENUM_DEAL_REASON)HistoryDealGetInteger(dealTicket, DEAL_REASON);
   double profit = HistoryDealGetDouble(dealTicket, DEAL_PROFIT)
                 + HistoryDealGetDouble(dealTicket, DEAL_SWAP)
                 + HistoryDealGetDouble(dealTicket, DEAL_COMMISSION);

   if(reason == DEAL_REASON_SL && profit < 0.0)
   {
      g_cooldownUntil = TimeCurrent() + InpCooldownMin * 60;
      Print("SL kena (", DoubleToString(profit, 2), ") -> cooldown sampai ",
            TimeToString(g_cooldownUntil, TIME_MINUTES));
   }
}

//---------------- Skor kustom optimasi -----------------------------
double OnTester()
{
   double net   = TesterStatistics(STAT_PROFIT);
   double pf    = TesterStatistics(STAT_PROFIT_FACTOR);
   double ddPct = TesterStatistics(STAT_BALANCE_DDREL_PERCENT);
   int    deals = (int)TesterStatistics(STAT_DEALS);

   if(deals < 30) return 0.0;
   if(net <= 0.0) return 0.0;

   double wrProxy = MathMin(pf, 3.0);
   return net * wrProxy * wrProxy / (1.0 + ddPct);
}
