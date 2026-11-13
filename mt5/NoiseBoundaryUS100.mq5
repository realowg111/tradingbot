//+------------------------------------------------------------------+
//| NoiseBoundaryUS100.mq5                                           |
//| Intraday momentum on the Nasdaq 100 CFD (US100 / NAS100 / USTEC) |
//| Rules of Zarattini, Aziz & Barbon (2024), "Beat the Market",     |
//| as backtested in scripts/nasdaq_daytrade/qqq_intraday_momentum.py|
//|                                                                  |
//| Every 30 minutes from 10:00 to 15:30 New York time:              |
//|  - long  if the M1 close is above  max(open, prev close)*(1+s)   |
//|  - short if the M1 close is below  min(open, prev close)*(1-s)   |
//|  s = mean |close/open - 1| at that minute over the last 14 days  |
//|  - a long is closed when the close falls below max(upper, VWAP), |
//|    a short when it rises above min(lower, VWAP)                  |
//| Everything is closed at 15:59 New York. No position overnight.   |
//| Size: SizeFactor x min(4, 2% / 14-day daily volatility) x equity |
//+------------------------------------------------------------------+
#property copyright "tradingbot"
#property version   "1.00"
#property strict

#include <Trade/Trade.mqh>

//--- inputs
input group "Strategie (valeurs de l'article, ne pas optimiser)"
input int    Lookback         = 14;     // Jours pour la zone de bruit
input int    CheckEveryMin    = 30;     // Decision toutes les N minutes
input double BandMult         = 1.0;    // Largeur de la zone de bruit

input group "Taille de position"
input double SizeFactor       = 0.5;    // 0.5 = taille de depart conseillee, 1.0 = article
input double TargetDailyVol   = 0.02;   // Volatilite journaliere visee (2 %)
input double MaxLeverage      = 4.0;    // Levier maximum (avant SizeFactor)

input group "Securite"
input double MaxDailyLossPct  = 3.0;    // Disjoncteur : perte max du jour en % (0 = off)
input double MaxSpreadPct     = 0.01;   // Pas d'entree si spread > x % du prix
input bool   UseEmergencySL   = true;   // Stop de secours chez le courtier (bord oppose de la zone)
input bool   UseTakeProfit    = false;  // TP fixe (absent du backtest, laisser false pour le reproduire)
input double TakeProfitPct    = 1.0;    // TP en % du prix d'entree

input group "Heure"
input bool   AutoDetectOffset = true;   // En reel/demo : detecter le decalage serveur / New York
input int    ServerMinusNY    = 7;      // Decalage (heures) serveur - New York, utilise dans le testeur

input group "Divers"
input long   Magic            = 20240930;
input bool   WriteCsvLog      = true;

//--- constants (minutes after midnight, New York)
#define OPEN_MIN   570   // 09:30
#define FLAT_MIN   959   // 15:59
#define SESSION_N  390

CTrade trade;

//--- day state
int      g_dayKey     = -1;      // yyyymmdd of the prepared NY session
bool     g_ready      = false;
double   g_sigma[SESSION_N];
double   g_prevClose  = 0;
double   g_dayOpen    = 0;
double   g_dailyVol   = 0;
double   g_lev        = 0;
double   g_startEquity= 0;
bool     g_halted     = false;
bool     g_flatDone   = false;
datetime g_lastBar    = 0;
double   g_ub = 0, g_lb = 0, g_vwap = 0;
string   g_lastAction = "";

//+------------------------------------------------------------------+
//| Time helpers                                                     |
//+------------------------------------------------------------------+
bool IsUSDST(datetime gmt)
{
   MqlDateTime d; TimeToStruct(gmt, d);
   int y = d.year;
   // second Sunday of March, 07:00 GMT ; first Sunday of November, 06:00 GMT
   datetime mar1 = StringToTime(StringFormat("%04d.03.01 00:00", y));
   MqlDateTime m; TimeToStruct(mar1, m);
   int firstSunMar = 1 + (7 - m.day_of_week) % 7;
   datetime start = StringToTime(StringFormat("%04d.03.%02d 07:00", y, firstSunMar + 7));
   datetime nov1 = StringToTime(StringFormat("%04d.11.01 00:00", y));
   TimeToStruct(nov1, m);
   int firstSunNov = 1 + (7 - m.day_of_week) % 7;
   datetime end = StringToTime(StringFormat("%04d.11.%02d 06:00", y, firstSunNov));
   return gmt >= start && gmt < end;
}

int OffsetHours()
{
   if(AutoDetectOffset && !MQLInfoInteger(MQL_TESTER))
   {
      datetime gmt = TimeGMT();
      int serverMinusGmt = (int)MathRound((double)(TimeTradeServer() - gmt) / 3600.0);
      int nyMinusGmt = IsUSDST(gmt) ? -4 : -5;
      return serverMinusGmt - nyMinusGmt;
   }
   return ServerMinusNY;
}

datetime ToNY(datetime server) { return server - (datetime)(OffsetHours() * 3600); }

int NYMinute(datetime server)
{
   MqlDateTime d; TimeToStruct(ToNY(server), d);
   return d.hour * 60 + d.min;
}

int NYDayKey(datetime server)
{
   MqlDateTime d; TimeToStruct(ToNY(server), d);
   return d.year * 10000 + d.mon * 100 + d.day;
}

int NYDayOfWeek(datetime server)
{
   MqlDateTime d; TimeToStruct(ToNY(server), d);
   return d.day_of_week;
}

//+------------------------------------------------------------------+
//| Logging                                                          |
//+------------------------------------------------------------------+
void Log(string action, string detail)
{
   g_lastAction = TimeToString(ToNY(TimeCurrent()), TIME_MINUTES) + " NY  " + action + "  " + detail;
   Print("[NoiseBoundary] ", g_lastAction);
   if(!WriteCsvLog) return;
   int h = FileOpen("NoiseBoundary_log.csv", FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_SHARE_READ, ';');
   if(h == INVALID_HANDLE) return;
   FileSeek(h, 0, SEEK_END);
   FileWrite(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS), TimeToString(ToNY(TimeCurrent()), TIME_DATE | TIME_MINUTES),
             action, detail, DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2));
   FileClose(h);
}

//+------------------------------------------------------------------+
//| Build the noise area from M1 history (once per NY session)       |
//+------------------------------------------------------------------+
bool PrepareDay(int todayKey)
{
   MqlRates r[];
   ArraySetAsSeries(r, false);
   int need = (Lookback + 12) * 1440;
   int n = CopyRates(_Symbol, PERIOD_M1, 0, need, r);
   if(n < 5000) { Print("[NoiseBoundary] Historique M1 insuffisant : ", n, " barres"); return false; }

   // collect complete past sessions
   double sessMoves[][SESSION_N];
   double sessClose[];
   int    count = 0;
   int    curKey = -1;
   double curOpen = 0, lastC = 0;
   double moves[SESSION_N];
   int    filled = 0;
   bool   hasOpen = false;

   for(int i = 0; i <= n; i++)
   {
      int key = (i < n) ? NYDayKey(r[i].time) : -2;
      if(key != curKey)
      {
         // close the previous session
         if(curKey != -1 && curKey != todayKey && hasOpen && filled >= 300)
         {
            // forward-fill missing minutes
            double last = moves[0];
            for(int m = 0; m < SESSION_N; m++) { if(moves[m] < 0) moves[m] = last; else last = moves[m]; }
            ArrayResize(sessMoves, count + 1);
            ArrayResize(sessClose, count + 1);
            for(int m = 0; m < SESSION_N; m++) sessMoves[count][m] = moves[m];
            sessClose[count] = lastC;
            count++;
         }
         if(i == n) break;
         curKey = key; hasOpen = false; filled = 0;
         for(int m = 0; m < SESSION_N; m++) moves[m] = -1;
      }
      int dow = NYDayOfWeek(r[i].time);
      if(dow == 0 || dow == 6) continue;
      int mm = NYMinute(r[i].time) - OPEN_MIN;
      if(mm < 0 || mm >= SESSION_N) continue;
      if(mm == 0) { curOpen = r[i].open; hasOpen = true; }
      if(!hasOpen) continue;
      moves[mm] = MathAbs(r[i].close / curOpen - 1.0);
      lastC = r[i].close;
      filled++;
   }

   if(count < Lookback + 1) { Print("[NoiseBoundary] Pas assez de seances completes : ", count); return false; }

   for(int m = 0; m < SESSION_N; m++)
   {
      double s = 0;
      for(int k = count - Lookback; k < count; k++) s += sessMoves[k][m];
      g_sigma[m] = s / Lookback * BandMult;
   }
   g_prevClose = sessClose[count - 1];

   // 14-day volatility of daily closes
   int nr = MathMin(14, count - 1);
   double rets[]; ArrayResize(rets, nr);
   double mean = 0;
   for(int k = 0; k < nr; k++) { rets[k] = sessClose[count - nr + k] / sessClose[count - nr + k - 1] - 1.0; mean += rets[k]; }
   mean /= nr;
   double var = 0;
   for(int k = 0; k < nr; k++) var += (rets[k] - mean) * (rets[k] - mean);
   g_dailyVol = MathSqrt(var / (nr - 1));
   g_lev = (g_dailyVol > 0) ? MathMin(MaxLeverage, TargetDailyVol / g_dailyVol) * SizeFactor : 0;

   Log("PREPARE", StringFormat("seances=%d prevClose=%.2f volJ=%.3f%% levier=%.2f", count, g_prevClose, g_dailyVol * 100, g_lev));
   return true;
}

//+------------------------------------------------------------------+
//| Today's open and VWAP (tick volume as proxy on CFDs)             |
//+------------------------------------------------------------------+
bool TodayOpenAndVwap(double &openPx, double &vwap, double &lastClose, int uptoMinute)
{
   MqlRates r[];
   ArraySetAsSeries(r, false);
   int n = CopyRates(_Symbol, PERIOD_M1, 1, SESSION_N + 30, r);   // closed bars only
   if(n <= 0) return false;
   int key = NYDayKey(TimeCurrent());
   double pv = 0, v = 0;
   bool found = false;
   for(int i = 0; i < n; i++)
   {
      if(NYDayKey(r[i].time) != key) continue;
      int mm = NYMinute(r[i].time) - OPEN_MIN;
      if(mm < 0 || mm > uptoMinute) continue;
      if(mm == 0) { openPx = r[i].open; found = true; }
      double tp = (r[i].high + r[i].low + r[i].close) / 3.0;
      double vol = (double)MathMax(r[i].tick_volume, 1);
      pv += tp * vol; v += vol;
      lastClose = r[i].close;
   }
   if(!found || v <= 0) return false;
   vwap = pv / v;
   return true;
}

//+------------------------------------------------------------------+
//| Position helpers                                                 |
//+------------------------------------------------------------------+
int CurrentSide(double &entry)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(!PositionSelectByTicket(t)) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol || PositionGetInteger(POSITION_MAGIC) != Magic) continue;
      entry = PositionGetDouble(POSITION_PRICE_OPEN);
      return PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1;
   }
   return 0;
}

void CloseAll(string why)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(!PositionSelectByTicket(t)) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol || PositionGetInteger(POSITION_MAGIC) != Magic) continue;
      if(trade.PositionClose(t)) Log("CLOSE", why);
      else Log("ERROR", "fermeture impossible : " + IntegerToString(trade.ResultRetcode()));
   }
}

double LotsFor(double price)
{
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tickValue <= 0 || tickSize <= 0 || price <= 0) return 0;
   double notionalPerLot = price / tickSize * tickValue;            // in account currency
   double lots = g_lev * AccountInfoDouble(ACCOUNT_EQUITY) / notionalPerLot;
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   lots = MathFloor(lots / step) * step;
   if(lots < vmin) { Log("SKIP", StringFormat("taille %.4f lots < minimum %.2f : capital trop faible", lots, vmin)); return 0; }
   return MathMin(lots, vmax);
}

void Open(int side, double ub, double lb)
{
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK), bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double mid = (ask + bid) / 2.0;
   if((ask - bid) / mid * 100.0 > MaxSpreadPct)
   { Log("SKIP", StringFormat("spread %.4f%% > %.4f%%", (ask - bid) / mid * 100.0, MaxSpreadPct)); return; }
   double lots = LotsFor(mid);
   if(lots <= 0) return;

   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double minDist = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   double sl = 0, tp = 0;
   if(side > 0)
   {
      if(UseEmergencySL) sl = NormalizeDouble(MathMin(lb, bid - minDist), digits);
      if(UseTakeProfit)  tp = NormalizeDouble(MathMax(ask * (1 + TakeProfitPct / 100.0), ask + minDist), digits);
      if(trade.Buy(lots, _Symbol, 0, sl, tp, "NB long")) Log("BUY", StringFormat("%.2f lots a %.2f SL %.2f TP %.2f", lots, ask, sl, tp));
      else Log("ERROR", "achat refuse : " + IntegerToString(trade.ResultRetcode()));
   }
   else
   {
      if(UseEmergencySL) sl = NormalizeDouble(MathMax(ub, ask + minDist), digits);
      if(UseTakeProfit)  tp = NormalizeDouble(MathMin(bid * (1 - TakeProfitPct / 100.0), bid - minDist), digits);
      if(trade.Sell(lots, _Symbol, 0, sl, tp, "NB short")) Log("SELL", StringFormat("%.2f lots a %.2f SL %.2f TP %.2f", lots, bid, sl, tp));
      else Log("ERROR", "vente refusee : " + IntegerToString(trade.ResultRetcode()));
   }
}

//+------------------------------------------------------------------+
//| Statistics of this EA's closed trades (for the dashboard)        |
//+------------------------------------------------------------------+
void Stats(int &trades, double &winRate, double &avgWin, double &avgLoss, double &expectancy, double &total)
{
   trades = 0; winRate = 0; avgWin = 0; avgLoss = 0; expectancy = 0; total = 0;
   if(!HistorySelect(0, TimeCurrent())) return;
   int wins = 0, losses = 0; double sw = 0, sl = 0;
   for(int i = 0; i < HistoryDealsTotal(); i++)
   {
      ulong d = HistoryDealGetTicket(i);
      if(HistoryDealGetInteger(d, DEAL_MAGIC) != Magic || HistoryDealGetString(d, DEAL_SYMBOL) != _Symbol) continue;
      if(HistoryDealGetInteger(d, DEAL_ENTRY) != DEAL_ENTRY_OUT) continue;
      double p = HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_COMMISSION) + HistoryDealGetDouble(d, DEAL_SWAP);
      trades++; total += p;
      if(p > 0) { wins++; sw += p; } else { losses++; sl += -p; }
   }
   if(trades == 0) return;
   winRate = 100.0 * wins / trades;
   avgWin = wins ? sw / wins : 0;
   avgLoss = losses ? sl / losses : 0;
   expectancy = total / trades;
}

void DrawLine(string name, double price, color c)
{
   if(price <= 0) return;
   if(ObjectFind(0, name) < 0) ObjectCreate(0, name, OBJ_HLINE, 0, 0, price);
   ObjectSetDouble(0, name, OBJPROP_PRICE, price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, c);
   ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_DASH);
}

void Dashboard()
{
   int trades; double wr, aw, al, ex, tot;
   Stats(trades, wr, aw, al, ex, tot);
   double entry = 0; int side = CurrentSide(entry);
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double dayPnl = g_startEquity > 0 ? eq - g_startEquity : 0;
   string s = "=== NOISE BOUNDARY US100 ===\n";
   s += StringFormat("Heure New York : %s  (decalage serveur %+dh)\n", TimeToString(ToNY(TimeCurrent()), TIME_MINUTES), OffsetHours());
   s += StringFormat("Etat : %s\n", g_halted ? "DISJONCTEUR - arret pour la journee" : (g_ready ? "actif" : "en attente de la seance"));
   s += StringFormat("Zone haute %.2f | zone basse %.2f | VWAP %.2f\n", g_ub, g_lb, g_vwap);
   s += StringFormat("Ouverture %.2f | cloture veille %.2f | vol 14 j %.2f%% | levier %.2f\n", g_dayOpen, g_prevClose, g_dailyVol * 100, g_lev);
   s += StringFormat("Position : %s\n", side == 0 ? "aucune" : (side > 0 ? "ACHAT" : "VENTE") + StringFormat(" depuis %.2f", entry));
   s += StringFormat("P&L du jour : %+.2f | equite %.2f\n", dayPnl, eq);
   s += StringFormat("Trades : %d | gagnants %.0f%% | gain moy %.2f | perte moy %.2f | ratio %.2f\n", trades, wr, aw, al, al > 0 ? aw / al : 0);
   s += StringFormat("Esperance par trade : %+.2f | total %+.2f\n", ex, tot);
   s += "Dernier evenement : " + g_lastAction;
   Comment(s);
   DrawLine("NB_UB", g_ub, clrDodgerBlue);
   DrawLine("NB_LB", g_lb, clrOrangeRed);
   DrawLine("NB_VWAP", g_vwap, clrGold);
}

//+------------------------------------------------------------------+
//| Main logic, on each new closed M1 bar                            |
//+------------------------------------------------------------------+
void OnNewBar()
{
   datetime now = TimeCurrent();
   int dow = NYDayOfWeek(now);
   int nyMin = NYMinute(now);
   int key = NYDayKey(now);
   if(dow == 0 || dow == 6) return;

   // new NY session
   if(key != g_dayKey && nyMin >= OPEN_MIN + 1 && nyMin < FLAT_MIN)
   {
      g_dayKey = key; g_halted = false; g_flatDone = false;
      g_startEquity = AccountInfoDouble(ACCOUNT_EQUITY);
      g_ready = PrepareDay(key);
   }
   if(key != g_dayKey || !g_ready) return;

   // daily circuit breaker
   if(!g_halted && MaxDailyLossPct > 0 && AccountInfoDouble(ACCOUNT_EQUITY) < g_startEquity * (1 - MaxDailyLossPct / 100.0))
   {
      g_halted = true;
      CloseAll("disjoncteur perte journaliere");
      Log("HALT", StringFormat("perte du jour > %.1f%%", MaxDailyLossPct));
   }

   // flat at the end of the session
   if(nyMin >= FLAT_MIN)
   {
      if(!g_flatDone) { CloseAll("fin de seance 15:59 NY"); g_flatDone = true; }
      return;
   }
   if(g_halted) return;

   // index of the bar that just closed, in session minutes
   int closedIdx = nyMin - 1 - OPEN_MIN;
   if(closedIdx < 0) return;
   double lastClose = 0;
   if(!TodayOpenAndVwap(g_dayOpen, g_vwap, lastClose, closedIdx)) return;
   double top = MathMax(g_dayOpen, g_prevClose), bot = MathMin(g_dayOpen, g_prevClose);
   g_ub = top * (1 + g_sigma[closedIdx]);
   g_lb = bot * (1 - g_sigma[closedIdx]);

   int m = nyMin - OPEN_MIN;                        // decision times 10:00 ... 15:30
   if(m < CheckEveryMin || m > 360 || m % CheckEveryMin != 0) return;

   double entry = 0;
   int side = CurrentSide(entry);
   double x = lastClose;
   if(side > 0 && x < MathMax(g_ub, g_vwap)) { CloseAll(StringFormat("long : cloture %.2f < max(zone %.2f, VWAP %.2f)", x, g_ub, g_vwap)); side = 0; }
   else if(side < 0 && x > MathMin(g_lb, g_vwap)) { CloseAll(StringFormat("short : cloture %.2f > min(zone %.2f, VWAP %.2f)", x, g_lb, g_vwap)); side = 0; }
   if(side == 0)
   {
      if(x > g_ub) Open(1, g_ub, g_lb);
      else if(x < g_lb) Open(-1, g_ub, g_lb);
   }
}

//+------------------------------------------------------------------+
int OnInit()
{
   trade.SetExpertMagicNumber(Magic);
   trade.SetTypeFillingBySymbol(_Symbol);
   trade.SetDeviationInPoints(50);
   Print("[NoiseBoundary] Demarrage sur ", _Symbol, ", decalage serveur - New York = ", OffsetHours(), " h");
   EventSetTimer(5);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   Comment("");
   ObjectDelete(0, "NB_UB"); ObjectDelete(0, "NB_LB"); ObjectDelete(0, "NB_VWAP");
}

void OnTick()
{
   datetime bar = iTime(_Symbol, PERIOD_M1, 0);
   if(bar != g_lastBar)
   {
      g_lastBar = bar;
      OnNewBar();
   }
}

void OnTimer() { Dashboard(); }
//+------------------------------------------------------------------+
