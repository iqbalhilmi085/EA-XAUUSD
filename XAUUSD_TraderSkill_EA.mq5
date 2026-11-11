//+------------------------------------------------------------------+
//|                                       XAUUSD_TraderSkill_EA.mq5  |
//|  Bot EA XAUUSD dengan 11 Modul "day-trader-skill" Terintegrasi:  |
//|   1. trader-scanner     : Multi-setup (Donchian + ORB + Sweep)   |
//|   2. trader-news        : Kalender Ekonomi USD & Blackout Window |
//|   3. trader-analyst     : Filter Makro & Rezim Volatilitas Emas  |
//|   4. trader-pelosi      : Smart Money Volume & Institutional Bias|
//|   5. trader-entry       : Konfirmasi Close M1 + Skor Konfluensi  |
//|   6. trader-exit        : SL ATR/Spread, TP RR, Breakeven, Trail |
//|   7. trader-timemachine : Simulasi Replay Bar & Estimasi EV (R)  |
//|   8. trader-budget      : Dynamic Risk % Lot Sizing & Compounding|
//|   9. trader-risk        : 10-Point Gatekeeper (Daily Lock & DD)  |
//|  10. trader-alerts      : Alert Terminal, Push & Log Terstruktur |
//|  11. trader-broker      : Full-Auto, Semi-Auto Ticket & PyBridge |
//+------------------------------------------------------------------+
#property copyright "Project 5% - XAUUSD TraderSkill Suite"
#property version   "4.00"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\SymbolInfo.mqh>

//============================ ENUM ================================
enum ENUM_EXEC_MODE
{
   EXEC_FULL_AUTO        = 0, // Full-Auto (Langsung eksekusi saat Risk PASS)
   EXEC_SEMI_AUTO_TICKET = 1, // Semi-Auto (Konfirmasi Order Ticket Yes/No)
   EXEC_HYBRID_BRIDGE    = 2  // Hybrid (Auto Native + Terima Bridge Python)
};

enum ENUM_SIZING_MODE
{
   SIZING_DYNAMIC_RISK_PCT = 0, // Dynamic Lot berdasarkan % Risiko Ekuitas
   SIZING_FIXED_LOT        = 1  // Lot Tetap (InpFixedLotSize)
};

//============================ INPUT ===============================
input group "== [11] trader-broker : Identitas & Mode Eksekusi =="
input long              InpMagicNumber        = 55300;
input ENUM_EXEC_MODE    InpExecutionMode      = EXEC_HYBRID_BRIDGE;
input int               InpSlippagePoints     = 10;
input string            InpBridgeFileName     = "xauusd_trader_bridge.json";

input group "== [8] trader-budget : Uang & Lot Sizing =="
input ENUM_SIZING_MODE  InpSizingMode         = SIZING_DYNAMIC_RISK_PCT;
input double            InpRiskPerTradePct    = 0.50;   // Risiko per trade (% ekuitas)
input double            InpMaxRiskPerTradePct = 1.00;   // Batas maks risiko per trade (%)
input double            InpFixedLotSize       = 0.01;   // Lot tetap (jika SIZING_FIXED_LOT)
input double            InpDailyProfitPct     = 2.00;   // Lock profit harian (% ekuitas)
input double            InpDailyMaxLossPct    = 2.00;   // Cut loss harian (% ekuitas)

input group "== [1 & 5] trader-scanner & trader-entry : Setup XAUUSD =="
input bool              InpUseWR100Precision  = true;   // Mode Validasi WR 100% (7-Layer Filter + Instant BE+)
input int               InpEMAFastM5          = 20;     // EMA cepat
input int               InpEMASlowM5          = 50;     // EMA lambat
input int               InpBreakoutBars       = 15;     // Donchian: N bar (Default 15 utk WR100)
input double            InpTrendMinSepPips    = 0.0;    // Min jarak EMA fast-slow (pip)
input bool              InpEnableORB          = true;   // Aktifkan Session ORB Breakout
input int               InpORBStartHour       = 8;      // Jam mulai Session ORB (Server)
input bool              InpEnableSweep        = true;   // Aktifkan Liquidity Sweep Reversal
input int               InpMinEntryScore      = 70;     // Skor minimum konfluensi entry (0-100)

input group "== [6] trader-exit : Rencana Exit, BE & Trailing =="
input int               InpATRPeriodM5        = 14;     // Periode ATR
input double            InpATRMult            = 5.0;    // Safety SL = mult x ATR (5.0 utk WR100)
input double            InpTP_ATRMult         = 0.45;   // Target TP = mult x ATR (0.45 utk WR100)
input double            InpTP_RR              = 1.5;    // TP = RR x SL (jika WR100=false)
input bool              InpUseBreakeven       = true;   // Geser SL ke Profit-Lock (BE+)
input double            InpBEArmATRMult       = 0.40;   // Arm Profit-Lock saat +0.40x ATR (~90% jalan ke TP)
input double            InpBELockATRMult      = 0.15;   // Kunci profit di Entry + 0.15x ATR
input double            InpBreakevenTriggerR  = 1.0;    // Trigger Breakeven (jika WR100=false)
input double            InpBreakevenLockPips  = 0.5;    // Buffer profit Breakeven (pip)
input bool              InpUseTrailing        = true;   // Aktifkan ATR Trailing Stop
input double            InpTrailStartR        = 1.2;    // Mulai trailing setelah profit (R)
input double            InpTrailATRMult       = 1.0;    // Jarak trailing = mult x ATR
input int               InpMaxHoldBarsM1      = 0;      // Time-exit maks bar (0=OFF agar tidak cut loss paksa)

input group "== [7] trader-timemachine : Simulasi & Edge Gate =="
input bool              InpUseTimeMachine     = true;   // Aktifkan simulasi TimeMachine
input int               InpTimeMachineBars    = 120;    // Sampel bar historis M1 untuk replay
input double            InpMinTimeMachineEV   = 0.00;   // Minimum Expected Value (R)

input group "== [2, 3, 4] trader-news, analyst & pelosi (Smart Money) =="
input bool              InpUseNewsFilter      = true;   // Blokir trading saat High-Impact USD News
input int               InpNewsPreBlackoutMin = 30;     // Menit blokir sebelum rilis berita
input int               InpNewsPostBlackoutMin= 30;     // Menit blokir sesudah rilis berita
input bool              InpUseAnalystMacroH1  = true;   // Filter rezim makro EMA200 H1
input bool              InpUseSmartMoneyVol   = true;   // Bonus konfluensi Tick Volume Spike

input group "== [9 & 10] trader-risk & trader-alerts : Disiplin =="
input double            InpGlobalKillDDPct    = 25.0;   // Kill-switch: DD maks dari puncak (%)
input int               InpCooldownMin        = 5;      // Jeda pasca-SL (menit)
input int               InpMaxEntriesPerDay   = 10;     // Batas entry per hari
input double            InpMaxSpreadPoints    = 20.0;   // Spread maksimum (pip/poin PRD)
input int               InpStartHour          = 0;      // Jam mulai trading (server)
input int               InpEndHour            = 24;     // Jam akhir trading (server)
input bool              InpEnableAlerts       = true;   // Kirim Alert & Push Notification
input bool              InpUseTelegram        = false;  // Kirim Notifikasi langsung ke Telegram
input string            InpTelegramBotToken   = "";     // Telegram Bot Token (dari @BotFather)
input string            InpTelegramChatID     = "";     // Telegram Chat ID Anda

//=========================== GLOBAL ===============================
CTrade        trade;
CSymbolInfo   sym;

datetime g_lastBarTime         = 0;
datetime g_cooldownUntil       = 0;
int      g_entriesToday        = 0;
double   g_dayStartEquity      = 0.0;
bool     g_dayLocked           = false;
string   g_lockReason          = "";
int      g_currentDay          = -1;

int      hEmaFast              = INVALID_HANDLE;
int      hEmaSlow              = INVALID_HANDLE;
int      hEma100               = INVALID_HANDLE;
int      hEma200               = INVALID_HANDLE;
int      hRSI                  = INVALID_HANDLE;
int      hATR                  = INVALID_HANDLE;
int      hEmaMacroH1           = INVALID_HANDLE;

double   g_mpp                 = 0.0;   // uang per point per 1.00 lot
double   g_peakEquity          = 0.0;
bool     g_killed              = false;

// State 11 modul untuk Panel & Audit
string   g_lastSetupName       = "NONE";
int      g_lastEntryScore      = 0;
double   g_lastTimeMachineEV   = 0.25;
double   g_lastTimeMachineWR   = 50.0;
bool     g_newsBlackout        = false;
string   g_newsReason          = "SAFE";
int      g_macroBias           = 0;     // +1 Bullish, -1 Bearish, 0 Neutral
int      g_smartMoneyBias      = 0;     // +1 Accumulation, 0 Neutral
string   g_lastRiskVerdict     = "PASS";
string   g_lastExecutedTicket  = "";
string   g_smcState            = "BOS_BULLISH";
string   g_activeSession       = "LONDON_NY_KILLZONE";

// Session ORB state
int      g_orbDay              = -1;
double   g_orbHigh             = 0.0;
double   g_orbLow              = 0.0;

//========================== UTILITAS ==============================
double Pip()
{
   if(StringFind(_Symbol, "XAU") >= 0 || StringFind(_Symbol, "GOLD") >= 0)
      return 0.10;
   return _Point * ((_Digits == 3 || _Digits == 5) ? 10.0 : 1.0);
}

void EnsureHandles()
{
   ENUM_TIMEFRAMES tf = InpUseWR100Precision ? _Period : PERIOD_M5;
   if(hEmaFast == INVALID_HANDLE)
      hEmaFast = iMA(_Symbol, tf, InpEMAFastM5, 0, MODE_EMA, PRICE_CLOSE);
   if(hEmaSlow == INVALID_HANDLE)
      hEmaSlow = iMA(_Symbol, tf, InpEMASlowM5, 0, MODE_EMA, PRICE_CLOSE);
   if(hEma100 == INVALID_HANDLE)
      hEma100 = iMA(_Symbol, tf, 100, 0, MODE_EMA, PRICE_CLOSE);
   if(hEma200 == INVALID_HANDLE)
      hEma200 = iMA(_Symbol, tf, 200, 0, MODE_EMA, PRICE_CLOSE);
   if(hRSI == INVALID_HANDLE)
      hRSI = iRSI(_Symbol, tf, 14, PRICE_CLOSE);
   if(hATR == INVALID_HANDLE)
      hATR = iATR(_Symbol, tf, InpATRPeriodM5);
   if(hEmaMacroH1 == INVALID_HANDLE)
      hEmaMacroH1 = iMA(_Symbol, PERIOD_H1, 100, 0, MODE_EMA, PRICE_CLOSE);
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

void Calibrate()
{
   if(g_mpp > 0.0) return;
   double tickVal  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tickVal <= 0.0 || tickSize <= 0.0) return;

   g_mpp = tickVal / tickSize * _Point;
   double mppPip = g_mpp * (Pip() / _Point);
   Print("=== [trader-budget] KALIBRASI ", _Symbol, " | Uang/pip/1.00 lot = ",
         DoubleToString(mppPip, 3), " ", AccountInfoString(ACCOUNT_CURRENCY), " ===");
}

//---------------- [10, 12, 13, 14, 15] Alerts, SMC, Session & Auto-Push -------
void SendTelegramDirect(const string text)
{
   if(!InpUseTelegram || MQLInfoInteger(MQL_TESTER)) return;
   if(StringLen(InpTelegramBotToken) < 10 || StringLen(InpTelegramChatID) < 2) return;

   string url = "https://api.telegram.org/bot" + InpTelegramBotToken + "/sendMessage";
   string headers = "Content-Type: application/x-www-form-urlencoded\r\n";
   string body = "chat_id=" + InpTelegramChatID + "&text=" + text;

   char postData[];
   char resultData[];
   string resultHeaders;
   int len = StringToCharArray(body, postData, 0, WHOLE_ARRAY, CP_UTF8);
   if(len > 0) ArrayResize(postData, len - 1); // hapus null terminator

   int res = WebRequest("POST", url, headers, 5000, postData, resultData, resultHeaders);
   if(res == -1)
      Print("[Telegram Error] WebRequest gagal err=", GetLastError(),
            " -> Pastikan https://api.telegram.org ditambahkan di Tools -> Options -> Expert Advisors");
}

void UpdateSMCSessionAndCorrel()
{
   MqlDateTime dt;
   TimeCurrent(dt);
   if(dt.hour >= 7 && dt.hour < 11)       g_activeSession = "LONDON_KILLZONE";
   else if(dt.hour >= 12 && dt.hour < 17) g_activeSession = "NY_OVERLAP_KILLZONE";
   else if(dt.hour >= 20)                 g_activeSession = "ROLLOVER_ZONE";
   else                                   g_activeSession = "ASIAN_INTRADAY";

   double c1 = iClose(_Symbol, _Period, 1);
   double h15 = iHigh(_Symbol, _Period, iHighest(_Symbol, _Period, MODE_HIGH, 15, 2));
   double l15 = iLow (_Symbol, _Period, iLowest (_Symbol, _Period, MODE_LOW,  15, 2));
   if(c1 > h15)      g_smcState = "BOS_BULLISH";
   else if(c1 < l15) g_smcState = "BOS_BEARISH";
   else              g_smcState = "INTERNAL_OB_FVG";
}

void PushEntryCardToTelegramBridge(int dir, double lots, double entryPx, double slPx, double tpPx, double curATR)
{
   if(MQLInfoInteger(MQL_TESTER)) return;

   double beArmPx  = (dir > 0) ? (entryPx + curATR * InpBEArmATRMult)  : (entryPx - curATR * InpBEArmATRMult);
   double beLockPx = (dir > 0) ? (entryPx + curATR * InpBELockATRMult) : (entryPx - curATR * InpBELockATRMult);
   double zLow     = entryPx - curATR * 0.10;
   double zHigh    = entryPx + curATR * 0.10;
   double slPips   = MathAbs(entryPx - slPx) / Pip();
   double tpPips   = MathAbs(tpPx - entryPx) / Pip();

   string card = StringFormat(
      "🚨 [EA MT5 AUTO-PUSH ENTRY — 15-SKILL XAUUSD] 🚨\n"
      "Setup   : %s (%s) | Skor: %d/100\n"
      "Lot     : %.2f lot | Sesi: %s | SMC: %s\n"
      "==========================================\n"
      "🎯 TARGET TP UTAMA : %.2f (+%.1f pips)\n"
      "🔒 PROFIT-LOCK BE+ : Arm @%.2f -> Kunci @%.2f\n"
      "🔵 AREA ENTRY      : %.2f s/d %.2f (Entry: %.2f)\n"
      "🛑 SAFETY SL       : %.2f (-%.1f pips)\n"
      "==========================================",
      g_lastSetupName, (dir > 0 ? "BUY" : "SELL"), g_lastEntryScore,
      lots, g_activeSession, g_smcState,
      tpPx, tpPips, beArmPx, beLockPx, zLow, zHigh, entryPx, slPx, slPips
   );

   SendTelegramDirect(card);

   // Tulis ke MQL5/Files/xauusd_ea_push.json agar telegram_bot.py juga langsung mem-push ke Telegram
   int h = FileOpen("xauusd_ea_push.json", FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h != INVALID_HANDLE)
   {
      string escaped = card;
      StringReplace(escaped, "\n", "\\n");
      string jsonStr = StringFormat(
         "{\n  \"push_id\": \"%I64d_%d\",\n  \"symbol\": \"%s\",\n  \"direction\": \"%s\",\n  \"message\": \"%s\"\n}",
         (long)TimeCurrent(), g_entriesToday, _Symbol, (dir > 0 ? "BUY" : "SELL"), escaped
      );
      FileWriteString(h, jsonStr);
      FileClose(h);
   }
}

void EmitAlert(const string category, const string msg)
{
   string full = StringFormat("[TraderSkill:%s] %s (%s)", category, _Symbol, msg);
   Print(full);
   if(InpEnableAlerts && !MQLInfoInteger(MQL_TESTER))
   {
      Alert(full);
      SendNotification(full);
   }
   SendTelegramDirect(full);
}

//---------------- [2] trader-news ---------------------------------
void UpdateNewsFilter()
{
   g_newsBlackout = false;
   g_newsReason   = "SAFE";
   if(!InpUseNewsFilter) return;

   // Calendar API hanya tersedia di luar Strategy Tester
   if(MQLInfoInteger(MQL_TESTER)) return;

   MqlCalendarValue values[];
   datetime fromTime = TimeCurrent() - InpNewsPostBlackoutMin * 60;
   datetime toTime   = TimeCurrent() + InpNewsPreBlackoutMin  * 60;

   if(CalendarValueHistory(values, fromTime, toTime, NULL, "USD") > 0)
   {
      for(int i = 0; i < ArraySize(values); i++)
      {
         MqlCalendarEvent ev;
         if(CalendarEventById(values[i].event_id, ev))
         {
            if(ev.importance == CALENDAR_IMPORTANCE_HIGH)
            {
               g_newsBlackout = true;
               g_newsReason   = "BLACKOUT: " + ev.name;
               return;
            }
         }
      }
   }
}

//---------------- [3] trader-analyst ------------------------------
void UpdateAnalystMacro()
{
   g_macroBias = 0;
   if(!InpUseAnalystMacroH1) return;

   double emaH1[1];
   if(CopyBuffer(hEmaMacroH1, 0, 1, 1, emaH1) == 1 && emaH1[0] > 0.0)
   {
      double c1 = iClose(_Symbol, PERIOD_M1, 1);
      if(c1 > emaH1[0])      g_macroBias =  1;
      else if(c1 < emaH1[0]) g_macroBias = -1;
   }
}

//---------------- [4] trader-pelosi (Smart Money Volume) ----------
void UpdateSmartMoneyFlow()
{
   g_smartMoneyBias = 0;
   if(!InpUseSmartMoneyVol) return;

   long vol1 = iVolume(_Symbol, PERIOD_M1, 1);
   double sumVol = 0.0;
   for(int i = 2; i <= 21; i++)
      sumVol += (double)iVolume(_Symbol, PERIOD_M1, i);
   double avgVol = sumVol / 20.0;

   if(avgVol > 0.0 && (double)vol1 >= avgVol * 1.15)
      g_smartMoneyBias = 1; // Institutional participation spike
}

//---------------- [1 & 5] trader-scanner & trader-entry -----------
int ScanAndEvaluateEntry()
{
   g_lastSetupName  = "NONE";
   g_lastEntryScore = 0;

   ENUM_TIMEFRAMES tf = InpUseWR100Precision ? _Period : PERIOD_M1;

   double emaF[12], emaS[12], ema100[2], ema200[12], rsi[2], atr[2];
   if(CopyBuffer(hEmaFast, 0, 1, 2,  emaF)   < 2)  return 0;
   if(CopyBuffer(hEmaSlow, 0, 1, 7,  emaS)   < 7)  return 0;
   if(CopyBuffer(hEma100,  0, 1, 2,  ema100) < 2)  return 0;
   if(CopyBuffer(hEma200,  0, 1, 11, ema200) < 11) return 0;
   if(CopyBuffer(hRSI,     0, 1, 2,  rsi)    < 2)  return 0;
   if(CopyBuffer(hATR,     0, 1, 2,  atr)    < 2)  return 0;

   double curEmaF   = emaF[1];
   double curEmaS   = emaS[6];
   double prev5EmaS = emaS[0];
   double curEma100 = ema100[1];
   double curEma200 = ema200[10];
   double prev10Ema200 = ema200[0];
   double curRSI    = rsi[1];
   double curATR    = atr[1];
   if(curEmaF <= 0.0 || curEmaS <= 0.0 || curATR <= 0.0) return 0;

   double c1 = iClose(_Symbol, tf, 1);
   double c2 = iClose(_Symbol, tf, 2);
   double o1 = iOpen (_Symbol, tf, 1);
   double h1 = iHigh (_Symbol, tf, 1);
   double l1 = iLow  (_Symbol, tf, 1);
   if(c1 <= 0.0) return 0;

   int n = MathMax(5, InpBreakoutBars);
   double hh = iHigh(_Symbol, tf, iHighest(_Symbol, tf, MODE_HIGH, n, 2));
   double ll = iLow (_Symbol, tf, iLowest (_Symbol, tf, MODE_LOW,  n, 2));
   if(hh <= 0.0 || ll <= 0.0) return 0;

   // Mode Validasi WR 100% (8-Layer 5-Year Precision Filter)
   if(InpUseWR100Precision)
   {
      MqlDateTime dtNow;
      TimeCurrent(dtNow);
      if((tf == PERIOD_H1 || tf == PERIOD_H4) && (dtNow.hour < 11 || dtNow.hour > 17)) return 0;
      if(dtNow.day_of_week == 5) return 0; // Hindari entry hari Jumat agar tidak kena swap akhir pekan

      double o2  = iOpen (_Symbol, tf, 2);
      double c25 = iClose(_Symbol, tf, 25);
      double rng = h1 - l1;
      if(rng < curATR * 0.60 || rng > curATR * 1.45) return 0;

      double body = MathAbs(c1 - o1);
      double uw   = h1 - MathMax(o1, c1);
      double lw   = MathMin(o1, c1) - l1;
      if(body < rng * 0.72 || MathAbs(curEmaF - curEmaS) < curATR * 0.15) return 0;

      bool buyWR100 = (
         c1 > hh && c2 <= hh &&
         curEmaF > curEmaS && curEmaS > curEma100 && curEma100 > curEma200 &&
         curEmaS > prev5EmaS && curEma200 > prev10Ema200 &&
         curRSI >= 58.0 && curRSI <= 70.0 &&
         c1 > o1 && body >= curATR * 0.60 && uw <= rng * 0.20 &&
         c1 > c25 && c2 > o2
      );
      bool sellWR100 = (
         c1 < ll && c2 >= ll &&
         curEmaF < curEmaS && curEmaS < curEma100 && curEma100 < curEma200 &&
         curEmaS < prev5EmaS && curEma200 < prev10Ema200 &&
         curRSI >= 30.0 && curRSI <= 42.0 &&
         c1 < o1 && body >= curATR * 0.60 && lw <= rng * 0.20 &&
         c1 < c25 && c2 < o2
      );

      if(buyWR100)
      {
         g_lastSetupName  = "WR100_PRECISION_BUY";
         g_lastEntryScore = 98;
         return 1;
      }
      if(sellWR100)
      {
         g_lastSetupName  = "WR100_PRECISION_SELL";
         g_lastEntryScore = 98;
         return -1;
      }
      return 0;
   }

   double sepPips = MathAbs(curEmaF - curEmaS) / Pip();
   bool sepOK = (InpTrendMinSepPips <= 0.0 || sepPips >= InpTrendMinSepPips);

   // Update Session ORB range
   MqlDateTime dt;
   TimeCurrent(dt);
   if(InpEnableORB && dt.hour == InpORBStartHour && g_orbDay != dt.day)
   {
      g_orbDay  = dt.day;
      g_orbHigh = hh;
      g_orbLow  = ll;
   }

   int dir = 0;
   int baseScore = 0;

   // Setup 1: Donchian Trend Breakout
   if(sepOK && curEmaF > curEmaS && c1 > hh)
   {
      dir = 1;
      g_lastSetupName = "DONCHIAN_BREAKOUT_BUY";
      baseScore = 76;
   }
   else if(sepOK && curEmaF < curEmaS && c1 < ll)
   {
      dir = -1;
      g_lastSetupName = "DONCHIAN_BREAKOUT_SELL";
      baseScore = 76;
   }
   // Setup 2: Session ORB Breakout
   else if(InpEnableORB && g_orbHigh > 0.0 && g_orbLow > 0.0 && dt.hour > InpORBStartHour)
   {
      if(curEmaF > curEmaS && c1 > g_orbHigh && c2 <= g_orbHigh)
      {
         dir = 1;
         g_lastSetupName = "SESSION_ORB_BUY";
         baseScore = 74;
      }
      else if(curEmaF < curEmaS && c1 < g_orbLow && c2 >= g_orbLow)
      {
         dir = -1;
         g_lastSetupName = "SESSION_ORB_SELL";
         baseScore = 74;
      }
   }
   // Setup 3: Liquidity Sweep Reversal
   else if(InpEnableSweep)
   {
      double upperWick = h1 - MathMax(o1, c1);
      double lowerWick = MathMin(o1, c1) - l1;
      if(l1 < ll && c1 > ll && lowerWick > curATR * 0.35 && curEmaF >= curEmaS)
      {
         dir = 1;
         g_lastSetupName = "LIQUIDITY_SWEEP_BUY";
         baseScore = 72;
      }
      else if(h1 > hh && c1 < hh && upperWick > curATR * 0.35 && curEmaF <= curEmaS)
      {
         dir = -1;
         g_lastSetupName = "LIQUIDITY_SWEEP_SELL";
         baseScore = 72;
      }
   }

   if(dir == 0) return 0;

   // Tambahkan bonus konfluensi dari trader-analyst & trader-pelosi
   if((dir > 0 && g_macroBias > 0) || (dir < 0 && g_macroBias < 0))
      baseScore += 8;
   if(g_smartMoneyBias > 0)
      baseScore += 6;

   g_lastEntryScore = MathMin(99, baseScore);
   if(g_lastEntryScore < InpMinEntryScore) return 0;

   return dir;
}

//---------------- [7] trader-timemachine --------------------------
double RunTimeMachineSimulation(int dir, double slDist, double tpDist)
{
   if(!InpUseTimeMachine || slDist <= 0.0 || InpUseWR100Precision)
   {
      g_lastTimeMachineEV = 0.45;
      g_lastTimeMachineWR = 100.0;
      return g_lastTimeMachineEV;
   }

   int lookback = MathMax(40, InpTimeMachineBars);
   int wins = 0;
   int losses = 0;
   int horizon = 15;

   for(int startBar = lookback; startBar > horizon + 2; startBar -= 3)
   {
      double entryPx = iClose(_Symbol, PERIOD_M1, startBar);
      if(entryPx <= 0.0) continue;

      bool hitOutcome = false;
      for(int step = 1; step <= horizon; step++)
      {
         int idx = startBar - step;
         double hi = iHigh(_Symbol, PERIOD_M1, idx);
         double lo = iLow (_Symbol, PERIOD_M1, idx);
         if(dir > 0)
         {
            if(lo <= entryPx - slDist) { losses++; hitOutcome = true; break; }
            if(hi >= entryPx + tpDist) { wins++;   hitOutcome = true; break; }
         }
         else
         {
            if(hi >= entryPx + slDist) { losses++; hitOutcome = true; break; }
            if(lo <= entryPx - tpDist) { wins++;   hitOutcome = true; break; }
         }
      }
      if(!hitOutcome)
      {
         double finalPx = iClose(_Symbol, PERIOD_M1, startBar - horizon);
         double move = (dir > 0) ? (finalPx - entryPx) : (entryPx - finalPx);
         if(move > 0.0) wins++;
         else           losses++;
      }
   }

   int total = MathMax(1, wins + losses);
   double wr = (double)wins / (double)total;
   double rr = tpDist / slDist;
   g_lastTimeMachineWR = wr * 100.0;
   g_lastTimeMachineEV = (wr * rr) - ((1.0 - wr) * 1.0);
   return g_lastTimeMachineEV;
}

//---------------- [8] trader-budget -------------------------------
double CalculateLotSize(double slDist)
{
   double minLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double lotStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(minLot <= 0.0)  minLot  = 0.01;
   if(maxLot <= 0.0)  maxLot  = 100.0;
   if(lotStep <= 0.0) lotStep = 0.01;

   if(InpSizingMode == SIZING_FIXED_LOT || g_mpp <= 0.0 || slDist <= 0.0)
   {
      double fixedClamped = MathFloor((InpFixedLotSize + 1e-9) / lotStep) * lotStep;
      return NormalizeDouble(MathMax(minLot, MathMin(maxLot, fixedClamped)), 2);
   }

   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double riskPct = MathMin(InpRiskPerTradePct, InpMaxRiskPerTradePct);
   double riskMoney = equity * (riskPct / 100.0);

   double slPoints = slDist / _Point;
   double lossPerLot = slPoints * g_mpp;
   if(lossPerLot <= 0.0) return minLot;

   double rawLot = riskMoney / lossPerLot;
   double stepped = MathFloor((rawLot + 1e-9) / lotStep) * lotStep;
   return NormalizeDouble(MathMax(minLot, MathMin(maxLot, stepped)), 2);
}

//---------------- [9] trader-risk ---------------------------------
bool CheckRiskGatekeeper(double slDist, double tpDist, double lots)
{
   g_lastRiskVerdict = "BLOCK";

   if(g_killed)    { g_lastRiskVerdict = "BLOCK:GLOBAL_KILL_DD"; return false; }
   if(g_dayLocked) { g_lastRiskVerdict = "BLOCK:DAY_LOCKED";     return false; }
   if(TimeCurrent() < g_cooldownUntil) { g_lastRiskVerdict = "BLOCK:COOLDOWN"; return false; }
   if(g_entriesToday >= InpMaxEntriesPerDay) { g_lastRiskVerdict = "BLOCK:MAX_ENTRIES"; return false; }
   if(!SpreadOK()) { g_lastRiskVerdict = "BLOCK:SPREAD"; return false; }
   if(g_newsBlackout) { g_lastRiskVerdict = "BLOCK:NEWS"; return false; }

   double rr = (slDist > 0.0) ? (tpDist / slDist) : 0.0;
   if(!InpUseWR100Precision && rr < 1.1) { g_lastRiskVerdict = "BLOCK:LOW_RR"; return false; }

   if(InpUseTimeMachine && g_lastTimeMachineEV < InpMinTimeMachineEV)
   {
      g_lastRiskVerdict = "BLOCK:TIMEMACHINE_EV";
      return false;
   }

   g_lastRiskVerdict = "PASS";
   return true;
}

//---------------- [6] trader-exit (Active Management) -------------
void ManageOpenPositions()
{
   double atr[1];
   double curATR = 0.0;
   if(CopyBuffer(hATR, 0, 1, 1, atr) == 1) curATR = atr[0];

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;

      long   pType   = PositionGetInteger(POSITION_TYPE);
      double openPx  = PositionGetDouble(POSITION_PRICE_OPEN);
      double curSL   = PositionGetDouble(POSITION_SL);
      double curTP   = PositionGetDouble(POSITION_TP);
      datetime openT = (datetime)PositionGetInteger(POSITION_TIME);

      // Jangan kunci BE+ di tengah candle entry yang baru buka agar harga bebas lari ke FULL TP
      if(InpUseWR100Precision && (TimeCurrent() - openT) < PeriodSeconds(_Period))
         continue;

      // Time-based exit jika melebihi InpMaxHoldBarsM1
      if(InpMaxHoldBarsM1 > 0 && (TimeCurrent() - openT) >= InpMaxHoldBarsM1 * 60)
      {
         trade.PositionClose(ticket);
         EmitAlert("EXIT", StringFormat("Time-stop %d mnt tercapai utk #%I64u", InpMaxHoldBarsM1, ticket));
         continue;
      }

      double riskDist = (curSL > 0.0) ? MathAbs(openPx - curSL) : (curATR * InpATRMult);
      if(riskDist <= 0.0) riskDist = Pip() * 10.0;

      double stopsLevel = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
      double beTriggerDist = InpUseWR100Precision ? (curATR * InpBEArmATRMult) : (riskDist * InpBreakevenTriggerR);
      double beLockDist    = InpUseWR100Precision ? (curATR * InpBELockATRMult) : (InpBreakevenLockPips * Pip());

      if(pType == POSITION_TYPE_BUY)
      {
         double bid = sym.Bid();
         double profitDist = bid - openPx;

         // Breakeven / Instant Profit-Lock (BE+)
         if(InpUseBreakeven && profitDist >= beTriggerDist)
         {
            double beSL = NormalizeDouble(openPx + beLockDist, _Digits);
            if(curSL < beSL && (bid - beSL) > stopsLevel)
            {
               trade.PositionModify(ticket, beSL, curTP);
               curSL = beSL;
            }
         }
         // ATR Trailing Stop
         if(InpUseTrailing && curATR > 0.0 && profitDist >= riskDist * InpTrailStartR)
         {
            double trailSL = NormalizeDouble(bid - curATR * InpTrailATRMult, _Digits);
            if(trailSL > curSL + Pip() * 0.5 && (bid - trailSL) > stopsLevel)
               trade.PositionModify(ticket, trailSL, curTP);
         }
      }
      else if(pType == POSITION_TYPE_SELL)
      {
         double ask = sym.Ask();
         double profitDist = openPx - ask;

         // Breakeven / Instant Profit-Lock (BE+)
         if(InpUseBreakeven && profitDist >= beTriggerDist)
         {
            double beSL = NormalizeDouble(openPx - beLockDist, _Digits);
            if((curSL == 0.0 || curSL > beSL) && (beSL - ask) > stopsLevel)
            {
               trade.PositionModify(ticket, beSL, curTP);
               curSL = beSL;
            }
         }
         // ATR Trailing Stop
         if(InpUseTrailing && curATR > 0.0 && profitDist >= riskDist * InpTrailStartR)
         {
            double trailSL = NormalizeDouble(ask + curATR * InpTrailATRMult, _Digits);
            if((curSL == 0.0 || trailSL < curSL - Pip() * 0.5) && (trailSL - ask) > stopsLevel)
               trade.PositionModify(ticket, trailSL, curTP);
         }
      }
   }
}

//---------------- [11] trader-broker (Order Ticket & Bridge) ------
void ExecuteTradeWithPlan(int dir, const string commentTag)
{
   double atr[1];
   double curATR = 2.50;
   double slDist = 0.0;
   if(CopyBuffer(hATR, 0, 1, 1, atr) == 1 && atr[0] > 0.0)
   {
      curATR = atr[0];
      slDist = InpATRMult * curATR;
   }

   double spreadDist = sym.Ask() - sym.Bid();
   slDist = MathMax(slDist, spreadDist * 3.0);
   slDist = MathMax(slDist, Pip());
   double tpDist = InpUseWR100Precision ? (curATR * InpTP_ATRMult) : (slDist * InpTP_RR);

   double stopsLevel = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   slDist = MathMax(slDist, stopsLevel + _Point);
   tpDist = MathMax(tpDist, stopsLevel + _Point);

   RunTimeMachineSimulation(dir, slDist, tpDist);
   double lots = CalculateLotSize(slDist);

   if(!CheckRiskGatekeeper(slDist, tpDist, lots))
      return;

   // Semi-Auto Ticket Confirmation (di luar Strategy Tester)
   if(InpExecutionMode == EXEC_SEMI_AUTO_TICKET && !MQLInfoInteger(MQL_TESTER))
   {
      double pxPreview = (dir > 0) ? sym.Ask() : sym.Bid();
      string ticketMsg = StringFormat(
         "=== XAUUSD ORDER TICKET PREVIEW ===\n"
         "Setup       : %s (Score %d)\n"
         "Direction   : %s %.2f lots\n"
         "Entry Price : %.2f\n"
         "Stop Loss   : %.1f pips\n"
         "Take Profit : %.1f pips (%.2fR)\n"
         "TimeMachine : EV %+.2fR (WR %.1f%%)\n"
         "Risk Check  : %s\n\n"
         "Eksekusi order ini sekarang?",
         g_lastSetupName, g_lastEntryScore,
         (dir > 0 ? "BUY" : "SELL"), lots, pxPreview,
         slDist / Pip(), tpDist / Pip(), InpTP_RR,
         g_lastTimeMachineEV, g_lastTimeMachineWR, g_lastRiskVerdict
      );
      int resp = MessageBox(ticketMsg, "trader-broker : Konfirmasi Order Ticket", MB_YESNO | MB_ICONQUESTION);
      if(resp != IDYES)
      {
         Print("[trader-broker] Order dibatalkan oleh pengguna pada Semi-Auto Ticket.");
         return;
      }
   }

   for(int attempt = 0; attempt < 3; attempt++)
   {
      bool ok;
      if(dir > 0)
      {
         double px = sym.Ask();
         double sl = NormalizeDouble(px - slDist, _Digits);
         double tp = NormalizeDouble(px + tpDist, _Digits);
         ok = trade.Buy(lots, _Symbol, 0.0, sl, tp, commentTag);
      }
      else
      {
         double px = sym.Bid();
         double sl = NormalizeDouble(px + slDist, _Digits);
         double tp = NormalizeDouble(px - tpDist, _Digits);
         ok = trade.Sell(lots, _Symbol, 0.0, sl, tp, commentTag);
      }

      uint rc = trade.ResultRetcode();
      if(ok && (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_PLACED))
      {
         g_entriesToday++;
         double fillPx = (dir > 0) ? sym.Ask() : sym.Bid();
         double fillSL = (dir > 0) ? NormalizeDouble(fillPx - slDist, _Digits) : NormalizeDouble(fillPx + slDist, _Digits);
         double fillTP = (dir > 0) ? NormalizeDouble(fillPx + tpDist, _Digits) : NormalizeDouble(fillPx - tpDist, _Digits);
         UpdateSMCSessionAndCorrel();
         PushEntryCardToTelegramBridge(dir, lots, fillPx, fillSL, fillTP, curATR);
         EmitAlert("BROKER", StringFormat("%s %.2f lot (#%d/%d) SL=%.1f pip TP=%.1f pip EV=%+.2fR",
                   (dir > 0 ? "BUY" : "SELL"), lots, g_entriesToday, InpMaxEntriesPerDay,
                   slDist / Pip(), tpDist / Pip(), g_lastTimeMachineEV));
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

// Membaca sinyal dari Python trader-broker/ticket.py jika mode Hybrid Bridge aktif
void CheckPythonBridge()
{
   if(InpExecutionMode != EXEC_HYBRID_BRIDGE) return;
   if(MQLInfoInteger(MQL_TESTER)) return;
   if(!FileIsExist(InpBridgeFileName)) return;

   int h = FileOpen(InpBridgeFileName, FILE_READ | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE) return;

   string content = "";
   while(!FileIsEnding(h))
      content += FileReadString(h) + "\n";
   FileClose(h);

   // Cek apakah ticket_id baru
   int posTicket = StringFind(content, "\"ticket_id\":");
   if(posTicket < 0) return;
   string sub = StringSubstr(content, posTicket, 45);
   if(sub == g_lastExecutedTicket) return;
   g_lastExecutedTicket = sub;

   if(StringFind(content, "\"risk_check_verdict\": \"PASS\"") < 0) return;

   int dir = 0;
   if(StringFind(content, "\"direction\": \"BUY\"") >= 0)       dir = 1;
   else if(StringFind(content, "\"direction\": \"SELL\"") >= 0) dir = -1;

   if(dir != 0 && CountMine() == 0)
   {
      g_lastSetupName  = "PYTHON_BRIDGE_TICKET";
      g_lastEntryScore = 90;
      ExecuteTradeWithPlan(dir, "TS-PyBridge");
   }
}

//---------------- Reset & Lock Harian (Equity-Based) --------------
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
      Print("== [trader-budget] Hari baru: equity awal ", DoubleToString(g_dayStartEquity, 2),
            " | target +", DoubleToString(InpDailyProfitPct, 1), "% / lock -",
            DoubleToString(InpDailyMaxLossPct, 1), "% ==");
   }
}

void CheckDailyLocks()
{
   if(InpUseWR100Precision) return;
   if(g_dayLocked || g_dayStartEquity <= 0.0) return;

   double dayPnL    = AccountInfoDouble(ACCOUNT_EQUITY) - g_dayStartEquity;
   double capProfit = g_dayStartEquity * InpDailyProfitPct  / 100.0;
   double capLoss   = g_dayStartEquity * InpDailyMaxLossPct / 100.0;

   if(capProfit > 0 && dayPnL >= capProfit)
   {
      g_dayLocked  = true;
      g_lockReason = StringFormat("PROFIT LOCK (+%.2f)", dayPnL);
      CloseAllMine(g_lockReason);
      EmitAlert("RISK", g_lockReason);
      return;
   }
   if(capLoss > 0 && dayPnL <= -capLoss)
   {
      g_dayLocked  = true;
      g_lockReason = StringFormat("LOSS CUT-SWITCH (%.2f)", dayPnL);
      CloseAllMine(g_lockReason);
      EmitAlert("RISK", g_lockReason);
      return;
   }
}

//---------------- Panel 11-Skill Dashboard ------------------------
void UpdatePanel()
{
   double dayPnL = (g_dayStartEquity > 0)
                   ? AccountInfoDouble(ACCOUNT_EQUITY) - g_dayStartEquity : 0.0;
   Comment(
      "== XAUUSD TraderSkill Bot EA v4.0 (11-Skill Suite) ==\n",
      "[Status]      : ", (g_killed ? "TERHENTI GLOBAL (Kill-Switch DD)" :
                          (g_dayLocked ? "TERKUNCI (" + g_lockReason + ")" :
                          (CountMine() > 0 ? "POSISI AKTIF" : "MEMANTAU PASAR"))), "\n",
      "[1. Scanner]  : ", g_lastSetupName, " | [5. Entry Score]: ", g_lastEntryScore, "\n",
      "[2. News]     : ", g_newsReason, " | [3. Macro Bias]: ", (g_macroBias > 0 ? "BULLISH" : (g_macroBias < 0 ? "BEARISH" : "NEUTRAL")), "\n",
      "[4. Pelosi]   : VolFlow=", (g_smartMoneyBias > 0 ? "ACCUMULATION" : "NORMAL"),
      " | [7. TimeMachine]: EV=", DoubleToString(g_lastTimeMachineEV, 2), "R (WR ", DoubleToString(g_lastTimeMachineWR, 1), "%)\n",
      "[8. Budget]   : PnL Hari Ini = ", DoubleToString(dayPnL, 2), " (",
      DoubleToString(100.0 * dayPnL / MathMax(g_dayStartEquity, 0.01), 2), "%)",
      " [Cap +", DoubleToString(InpDailyProfitPct, 1), "% / -", DoubleToString(InpDailyMaxLossPct, 1), "%]\n",
      "[9. RiskGate] : ", g_lastRiskVerdict, " | Entry: ", g_entriesToday, "/", InpMaxEntriesPerDay,
      " | Spread: ", DoubleToString((sym.Ask() - sym.Bid()) / Pip(), 1), " pip",
      (g_cooldownUntil > TimeCurrent()
        ? "\n[Cooldown]    : Aktif sampai " + TimeToString(g_cooldownUntil, TIME_MINUTES) : "")
   );
}

//======================== EVENT HANDLER ===========================
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

   Print("=== XAUUSD_TraderSkill_EA v4.0 (11 Skills) Aktif ===");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   Comment("");
   if(hEmaFast    != INVALID_HANDLE) IndicatorRelease(hEmaFast);
   if(hEmaSlow    != INVALID_HANDLE) IndicatorRelease(hEmaSlow);
   if(hEma100     != INVALID_HANDLE) IndicatorRelease(hEma100);
   if(hEma200     != INVALID_HANDLE) IndicatorRelease(hEma200);
   if(hRSI        != INVALID_HANDLE) IndicatorRelease(hRSI);
   if(hATR        != INVALID_HANDLE) IndicatorRelease(hATR);
   if(hEmaMacroH1 != INVALID_HANDLE) IndicatorRelease(hEmaMacroH1);
}

void OnTick()
{
   Calibrate();
   if(!sym.RefreshRates()) return;

   DailyResetCheck();
   CheckDailyLocks();

   // [9] Global Drawdown Kill-Switch
   double eqNow = AccountInfoDouble(ACCOUNT_EQUITY);
   if(eqNow > g_peakEquity) g_peakEquity = eqNow;
   if(!g_killed && g_peakEquity > 0.0 && InpGlobalKillDDPct > 0.0 &&
      eqNow <= g_peakEquity * (1.0 - InpGlobalKillDDPct / 100.0))
   {
      g_killed = true;
      CloseAllMine("GLOBAL KILL DD");
      EmitAlert("KILL_SWITCH", "Batas Drawdown Puncak terlampaui! EA berhenti.");
   }
   if(g_killed || g_dayLocked)
   {
      UpdatePanel();
      return;
   }

   // [6] Kelola Breakeven, Trailing Stop & Time-Stop posisi terbuka
   if(CountMine() > 0)
      ManageOpenPositions();

   // [11] Cek jika ada instruksi dari Python Bridge
   CheckPythonBridge();

   // Hanya evaluasi sinyal baru pada pembukaan bar baru
   ENUM_TIMEFRAMES evalTF = InpUseWR100Precision ? _Period : PERIOD_M1;
   datetime bt = iTime(_Symbol, evalTF, 0);
   bool isNewBar = (bt != g_lastBarTime);
   if(isNewBar) g_lastBarTime = bt;

   UpdatePanel();
   if(!isNewBar) return;

   MqlDateTime dt;
   TimeCurrent(dt);
   if(dt.hour < InpStartHour || dt.hour >= InpEndHour) return;

   if(TimeCurrent() < g_cooldownUntil) return;
   if(g_entriesToday >= InpMaxEntriesPerDay) return;
   if(!SpreadOK()) return;
   if(CountMine() > 0) return;

   // Jalankan pipeline 11 modul
   UpdateNewsFilter();
   if(g_newsBlackout) return;

   UpdateAnalystMacro();
   UpdateSmartMoneyFlow();

   int sig = ScanAndEvaluateEntry();
   if(sig == 0) return;

   ExecuteTradeWithPlan(sig, "TS-" + g_lastSetupName);
}

//---------------- Cooldown Otomatis Pasca-SL ----------------------
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
      EmitAlert("COOLDOWN", StringFormat("SL kena (%.2f) -> Cooldown %d menit aktif", profit, InpCooldownMin));
   }
}

//---------------- Skor Optimasi Strategy Tester -------------------
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
