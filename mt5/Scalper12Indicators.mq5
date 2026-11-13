//+------------------------------------------------------------------+
//| Scalper12Indicators.mq5  (v2)                                    |
//| 12 indicators vote, a confidence gauge (buy % / sell %),         |
//| automatic execution with TP/SL, on-screen panel.                 |
//|                                                                  |
//| Two presets:                                                     |
//|  TENDANCE : what the backtests taught us. Trades only in the     |
//|    direction of the day (noise-boundary regime, New York session)|
//|    on a pullback confirmed by the votes; stop under the last     |
//|    swing, target 5 R, up to 2 h, 10:00-12:00 New York only,      |
//|    one position at a time.                                       |
//|  VIDEO    : the behaviour seen in the TikTok video: analysis on  |
//|    every tick, tiny TP, up to 5 close positions, optional        |
//|    growing lot sizes (grid). Demo only.                          |
//|  CUSTOM   : every setting below is used as entered.              |
//|                                                                  |
//| Backtests (scripts/scalping_lab, scripts/xau_daytrade): the      |
//| VIDEO rules lost money 2009-2026 even without costs; the         |
//| TENDANCE rules were close to break-even but still negative       |
//| (about -4 %/yr at 0.5 % risk, Nasdaq 2014-2024). Demo first.     |
//+------------------------------------------------------------------+
#property copyright "tradingbot"
#property version   "2.00"
#property strict

#include <Trade/Trade.mqh>

enum ENUM_PRESET { PRESET_CUSTOM = 0, PRESET_VIDEO = 1, PRESET_TENDANCE = 2 };

input group "Mode"
input ENUM_PRESET Preset       = PRESET_TENDANCE; // Preregage (CUSTOM = utiliser les valeurs ci-dessous)

input group "Signal (CUSTOM)"
input int    MinVotes          = 8;      // Votes alignes requis (sur 10)
input double GaugeSlope        = 0.35;   // Pente de la jauge (score -> probabilite)
input double MinVolRatio       = 0.8;    // Filtre volatilite : ATR14 / ATR100 minimum
input bool   CycleOnEveryTick  = false;  // Analyse a chaque tick (sinon 1 fois par bougie M1)
input bool   TrendFilter       = false;  // Seulement dans le sens de la tendance du jour (noise boundary)
input bool   PullbackTrigger   = false;  // Entree sur repli a l'EMA9 puis reprise

input group "Sorties (CUSTOM)"
input bool   SwingStop         = false;  // Stop sous le dernier creux (sinon SL_ATR)
input int    SwingBars         = 5;      // Bougies pour le creux / sommet
input double TP_R              = 5.0;    // Objectif en multiple du risque (avec SwingStop)
input double TP_ATR            = 0.5;    // Take profit en ATR(14) M1 (sans SwingStop)
input double SL_ATR            = 1.5;    // Stop loss en ATR(14) M1 (sans SwingStop)
input int    MaxHoldMinutes    = 60;     // Fermeture forcee apres N minutes (0 = off)
input bool   CloseOnOpposite   = true;   // Fermer si le signal s'inverse

input group "Taille et risque"
input double RiskPerTradePct   = 1.0;    // Risque par trade en % de l'equite (si FixedLot = 0)
input double FixedLot          = 0.0;    // Lot fixe (0 = calcul par le risque)
input int    MaxPositions      = 5;      // Positions simultanees max, meme sens (CUSTOM)
input double MinSpacingATR     = 0.3;    // Ecart minimum entre deux entrees, en ATR (CUSTOM)
input double LotProgression    = 1.0;    // Taille x ce facteur a chaque position ajoutee (1 = off, grille si > 1)
input double MaxSpreadATR      = 0.3;    // Pas d'entree si spread > x ATR
input double DailyStopPct      = 0.0;    // Arret pour la journee si perte > x % (0 = off)

input group "Horaires (heure de New York)"
input bool   UseNYWindow       = false;  // Limiter aux heures ci-dessous (CUSTOM)
input int    WindowStartNY     = 600;    // Debut en minutes apres minuit NY (600 = 10:00)
input int    WindowEndNY       = 720;    // Fin (720 = 12:00)
input bool   AutoDetectOffset  = true;   // Detecter le decalage serveur / New York (reel/demo)
input int    ServerMinusNY     = 7;      // Decalage serveur - New York en heures (testeur)

input group "Divers"
input long   Magic             = 12121212;
input bool   WriteCsvLog       = true;

#define OPEN_MIN  570
#define SESSION_N 390

CTrade trade;

// effective settings (after preset)
int    p_minVotes, p_maxPos, p_hold, p_wStart, p_wEnd;
double p_tpAtr, p_slAtr, p_spacing, p_tpR, p_lotProg;
bool   p_tick, p_trend, p_pullback, p_swing, p_closeOpp, p_window;
string p_name;

int hRSI, hMACD, hEMA20, hEMA9, hEMAH1, hBB, hATR, hATR100;
datetime g_lastBar = 0;
double   g_dayStartEq = 0;
int      g_day = -1;
bool     g_halted = false;
string   g_journal[12];
int      g_jn = 0;

string   g_names[12] = {"RSI 14", "Tendance H1", "Ecart MM20", "MACD", "Structure", "Bollinger",
                        "Volatilite", "VWAP", "Momentum 5", "Momentum 15", "Cassure", "Alignement"};
double   g_vals[12];
int      g_votes[12];
double   g_pBuy = 0.5;
int      g_score = 0;
double   g_atr = 0;

// noise-boundary regime
int      g_nbDay = -1;
bool     g_nbReady = false;
double   g_sigma[SESSION_N];
double   g_prevClose = 0, g_dayOpen = 0;
int      g_regime = 0;

//+------------------------------------------------------------------+
void ApplyPreset()
{
   p_minVotes = MinVotes; p_tick = CycleOnEveryTick; p_trend = TrendFilter; p_pullback = PullbackTrigger;
   p_swing = SwingStop; p_tpR = TP_R; p_tpAtr = TP_ATR; p_slAtr = SL_ATR; p_hold = MaxHoldMinutes;
   p_closeOpp = CloseOnOpposite; p_maxPos = MaxPositions; p_spacing = MinSpacingATR; p_lotProg = LotProgression;
   p_window = UseNYWindow; p_wStart = WindowStartNY; p_wEnd = WindowEndNY; p_name = "PERSONNALISE";
   if(Preset == PRESET_TENDANCE)
   {
      p_name = "TENDANCE"; p_minVotes = 6; p_tick = false; p_trend = true; p_pullback = true;
      p_swing = true; p_tpR = 5.0; p_hold = 120; p_closeOpp = false; p_maxPos = 1; p_lotProg = 1.0;
      p_window = true; p_wStart = 600; p_wEnd = 720;
   }
   else if(Preset == PRESET_VIDEO)
   {
      p_name = "VIDEO"; p_minVotes = 8; p_tick = true; p_trend = false; p_pullback = false;
      p_swing = false; p_tpAtr = 0.2; p_slAtr = 1.5; p_hold = 30; p_closeOpp = true;
      p_maxPos = 5; p_spacing = 0.1; p_window = false;
   }
}

//+------------------------------------------------------------------+
//| Time (New York)                                                  |
//+------------------------------------------------------------------+
bool IsUSDST(datetime gmt)
{
   MqlDateTime d; TimeToStruct(gmt, d);
   int y = d.year;
   MqlDateTime m;
   datetime mar1 = StringToTime(StringFormat("%04d.03.01 00:00", y)); TimeToStruct(mar1, m);
   datetime start = StringToTime(StringFormat("%04d.03.%02d 07:00", y, 1 + (7 - m.day_of_week) % 7 + 7));
   datetime nov1 = StringToTime(StringFormat("%04d.11.01 00:00", y)); TimeToStruct(nov1, m);
   datetime end = StringToTime(StringFormat("%04d.11.%02d 06:00", y, 1 + (7 - m.day_of_week) % 7));
   return gmt >= start && gmt < end;
}

int OffsetHours()
{
   if(AutoDetectOffset && !MQLInfoInteger(MQL_TESTER))
   {
      datetime gmt = TimeGMT();
      int serverMinusGmt = (int)MathRound((double)(TimeTradeServer() - gmt) / 3600.0);
      return serverMinusGmt - (IsUSDST(gmt) ? -4 : -5);
   }
   return ServerMinusNY;
}

datetime ToNY(datetime server) { return server - (datetime)(OffsetHours() * 3600); }
int NYMinute(datetime s) { MqlDateTime d; TimeToStruct(ToNY(s), d); return d.hour * 60 + d.min; }
int NYDayKey(datetime s) { MqlDateTime d; TimeToStruct(ToNY(s), d); return d.year * 10000 + d.mon * 100 + d.day; }
int NYDow(datetime s)    { MqlDateTime d; TimeToStruct(ToNY(s), d); return d.day_of_week; }

//+------------------------------------------------------------------+
void J(string s)
{
   string line = TimeToString(TimeCurrent(), TIME_SECONDS) + "  " + s;
   for(int i = 11; i > 0; i--) g_journal[i] = g_journal[i - 1];
   g_journal[0] = line;
   if(g_jn < 12) g_jn++;
   Print("[Scalper12] ", line);
   if(!WriteCsvLog) return;
   int h = FileOpen("Scalper12_log.csv", FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_SHARE_READ, ';');
   if(h == INVALID_HANDLE) return;
   FileSeek(h, 0, SEEK_END);
   FileWrite(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS), p_name, s, DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2));
   FileClose(h);
}

double Buf(int handle, int buffer, int shift)
{
   double b[];
   if(CopyBuffer(handle, buffer, shift, 1, b) < 1) return EMPTY_VALUE;
   return b[0];
}

//+------------------------------------------------------------------+
//| Noise-boundary regime (direction of the day)                     |
//+------------------------------------------------------------------+
bool PrepareRegime(int todayKey)
{
   MqlRates r[];
   ArraySetAsSeries(r, false);
   int n = CopyRates(_Symbol, PERIOD_M1, 0, 26 * 1440, r);
   if(n < 5000) return false;
   double sessMoves[][SESSION_N];
   double sessClose[];
   int count = 0, curKey = -1, filled = 0;
   double curOpen = 0, lastC = 0, moves[SESSION_N];
   bool hasOpen = false;
   for(int i = 0; i <= n; i++)
   {
      int key = (i < n) ? NYDayKey(r[i].time) : -2;
      if(key != curKey)
      {
         if(curKey != -1 && curKey != todayKey && hasOpen && filled >= 300)
         {
            double last = moves[0];
            for(int m = 0; m < SESSION_N; m++) { if(moves[m] < 0) moves[m] = last; else last = moves[m]; }
            ArrayResize(sessMoves, count + 1); ArrayResize(sessClose, count + 1);
            for(int m = 0; m < SESSION_N; m++) sessMoves[count][m] = moves[m];
            sessClose[count] = lastC; count++;
         }
         if(i == n) break;
         curKey = key; hasOpen = false; filled = 0;
         for(int m = 0; m < SESSION_N; m++) moves[m] = -1;
      }
      int dow = NYDow(r[i].time);
      if(dow == 0 || dow == 6) continue;
      int mm = NYMinute(r[i].time) - OPEN_MIN;
      if(mm < 0 || mm >= SESSION_N) continue;
      if(mm == 0) { curOpen = r[i].open; hasOpen = true; }
      if(!hasOpen) continue;
      moves[mm] = MathAbs(r[i].close / curOpen - 1.0); lastC = r[i].close; filled++;
   }
   if(count < 15) { J(StringFormat("Tendance du jour indisponible : %d seances d'historique", count)); return false; }
   for(int m = 0; m < SESSION_N; m++)
   {
      double s = 0;
      for(int k = count - 14; k < count; k++) s += sessMoves[k][m];
      g_sigma[m] = s / 14.0;
   }
   g_prevClose = sessClose[count - 1];
   return true;
}

void UpdateRegime()
{
   g_regime = 0;
   datetime now = TimeCurrent();
   int key = NYDayKey(now), nyMin = NYMinute(now), dow = NYDow(now);
   if(dow == 0 || dow == 6 || nyMin < OPEN_MIN + 1 || nyMin >= OPEN_MIN + SESSION_N) return;
   if(key != g_nbDay) { g_nbDay = key; g_nbReady = PrepareRegime(key); g_dayOpen = 0; }
   if(!g_nbReady) return;
   MqlRates r[];
   ArraySetAsSeries(r, false);
   int n = CopyRates(_Symbol, PERIOD_M1, 1, SESSION_N + 10, r);
   double lastClose = 0;
   int idx = -1;
   for(int i = 0; i < n; i++)
   {
      if(NYDayKey(r[i].time) != key) continue;
      int mm = NYMinute(r[i].time) - OPEN_MIN;
      if(mm < 0 || mm >= SESSION_N) continue;
      if(mm == 0) g_dayOpen = r[i].open;
      lastClose = r[i].close; idx = mm;
   }
   if(g_dayOpen <= 0 || idx < 0) return;
   double top = MathMax(g_dayOpen, g_prevClose), bot = MathMin(g_dayOpen, g_prevClose);
   if(lastClose > top * (1 + g_sigma[idx])) g_regime = 1;
   else if(lastClose < bot * (1 - g_sigma[idx])) g_regime = -1;
}

//+------------------------------------------------------------------+
//| 12 indicators                                                    |
//+------------------------------------------------------------------+
bool DayVWAP(double &vwap)
{
   MqlDateTime d; TimeToStruct(TimeCurrent(), d);
   d.hour = 0; d.min = 0; d.sec = 0;
   MqlRates r[];
   int n = CopyRates(_Symbol, PERIOD_M1, StructToTime(d), TimeCurrent(), r);
   if(n <= 1) return false;
   double pv = 0, v = 0;
   for(int i = 0; i < n - 1; i++)
   {
      double vol = (double)MathMax(r[i].tick_volume, 1);
      pv += (r[i].high + r[i].low + r[i].close) / 3.0 * vol; v += vol;
   }
   vwap = pv / v;
   return true;
}

bool Read(MqlRates &r[])
{
   ArraySetAsSeries(r, true);
   if(CopyRates(_Symbol, PERIOD_M1, 0, 40, r) < 40) return false;
   double c = r[1].close;
   double rsi = Buf(hRSI, 0, 1), macd = Buf(hMACD, 0, 1), sig = Buf(hMACD, 1, 1);
   double e20 = Buf(hEMA20, 0, 1), eh1 = Buf(hEMAH1, 0, 1), bbMid = Buf(hBB, 0, 1);
   double atr = Buf(hATR, 0, 1), atr100 = Buf(hATR100, 0, 1);
   if(rsi == EMPTY_VALUE || macd == EMPTY_VALUE || e20 == EMPTY_VALUE || eh1 == EMPTY_VALUE ||
      bbMid == EMPTY_VALUE || atr == EMPTY_VALUE || atr100 == EMPTY_VALUE || atr <= 0) return false;
   double vwap = c;
   DayVWAP(vwap);
   double hi12 = r[2].high, lo12 = r[2].low, hi20 = r[2].high, lo20 = r[2].low;
   for(int i = 2; i <= 21; i++)
   {
      if(i <= 13) { hi12 = MathMax(hi12, r[i].high); lo12 = MathMin(lo12, r[i].low); }
      hi20 = MathMax(hi20, r[i].high); lo20 = MathMin(lo20, r[i].low);
   }
   g_atr = atr;
   g_vals[0] = rsi;                     g_votes[0] = rsi > 55 ? 1 : (rsi < 45 ? -1 : 0);
   g_vals[1] = (c - eh1) / atr;         g_votes[1] = c > eh1 ? 1 : (c < eh1 ? -1 : 0);
   g_vals[2] = (c - e20) / atr;         g_votes[2] = c > e20 ? 1 : (c < e20 ? -1 : 0);
   g_vals[3] = (macd - sig) / atr;      g_votes[3] = macd > sig ? 1 : (macd < sig ? -1 : 0);
   double mid12 = (hi12 + lo12) / 2;
   g_vals[4] = (c - mid12) / atr;       g_votes[4] = c > mid12 ? 1 : (c < mid12 ? -1 : 0);
   g_vals[5] = (c - bbMid) / atr;       g_votes[5] = c > bbMid ? 1 : (c < bbMid ? -1 : 0);
   g_vals[6] = atr / atr100;            g_votes[6] = 0;
   g_vals[7] = (c - vwap) / atr;        g_votes[7] = c > vwap ? 1 : (c < vwap ? -1 : 0);
   g_vals[8] = (c - r[6].close) / atr;  g_votes[8] = c > r[6].close ? 1 : (c < r[6].close ? -1 : 0);
   g_vals[9] = (c - r[16].close) / atr; g_votes[9] = c > r[16].close ? 1 : (c < r[16].close ? -1 : 0);
   g_vals[10] = c > hi20 ? 1 : (c < lo20 ? -1 : 0); g_votes[10] = (int)g_vals[10];
   g_score = 0;
   for(int i = 0; i < 11; i++) g_score += g_votes[i];
   g_vals[11] = g_score;                g_votes[11] = g_score > 0 ? 1 : (g_score < 0 ? -1 : 0);
   g_pBuy = 1.0 / (1.0 + MathExp(-GaugeSlope * g_score));
   return true;
}

//+------------------------------------------------------------------+
//| Positions                                                        |
//+------------------------------------------------------------------+
int CountPositions(int side, double &nearest, double price)
{
   int n = 0; nearest = DBL_MAX;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(!PositionSelectByTicket(t)) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol || PositionGetInteger(POSITION_MAGIC) != Magic) continue;
      int s = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1;
      if(side != 0 && s != side) continue;
      n++;
      nearest = MathMin(nearest, MathAbs(PositionGetDouble(POSITION_PRICE_OPEN) - price));
   }
   return n;
}

void CloseSide(int side, string why)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(!PositionSelectByTicket(t)) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol || PositionGetInteger(POSITION_MAGIC) != Magic) continue;
      int s = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1;
      if(side != 0 && s != side) continue;
      double p = PositionGetDouble(POSITION_PROFIT);
      if(trade.PositionClose(t)) J(StringFormat("Cloture %s (%s) : %+.2f", s > 0 ? "Buy" : "Sell", why, p));
   }
}

void CloseExpired()
{
   if(p_hold <= 0) return;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(!PositionSelectByTicket(t)) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol || PositionGetInteger(POSITION_MAGIC) != Magic) continue;
      if(TimeCurrent() - (datetime)PositionGetInteger(POSITION_TIME) >= p_hold * 60)
      {
         double p = PositionGetDouble(POSITION_PROFIT);
         if(trade.PositionClose(t)) J(StringFormat("Cloture (duree max) : %+.2f", p));
      }
   }
}

double Lots(double slDist, int existing)
{
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN), vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double lots = FixedLot;
   if(lots <= 0)
   {
      double tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE), ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
      if(tv <= 0 || ts <= 0 || slDist <= 0) return 0;
      lots = AccountInfoDouble(ACCOUNT_EQUITY) * RiskPerTradePct / 100.0 / (slDist / ts * tv);
   }
   if(p_lotProg > 1.0 && existing > 0) lots *= MathPow(p_lotProg, existing);
   lots = MathFloor(lots / step) * step;
   if(lots < vmin) lots = vmin;
   return MathMin(lots, vmax);
}

//+------------------------------------------------------------------+
//| One analysis / execution cycle                                   |
//+------------------------------------------------------------------+
void Cycle()
{
   MqlDateTime d; TimeToStruct(TimeCurrent(), d);
   if(d.day_of_year != g_day) { g_day = d.day_of_year; g_dayStartEq = AccountInfoDouble(ACCOUNT_EQUITY); g_halted = false; }
   if(DailyStopPct > 0 && !g_halted && AccountInfoDouble(ACCOUNT_EQUITY) < g_dayStartEq * (1 - DailyStopPct / 100.0))
   { g_halted = true; CloseSide(0, "arret journalier"); J("Arret pour la journee (perte max atteinte)"); }

   CloseExpired();
   if(p_trend) UpdateRegime();
   MqlRates r[];
   if(!Read(r)) return;
   if(g_halted) return;
   if(p_window)
   {
      int ny = NYMinute(TimeCurrent());
      if(ny < p_wStart || ny >= p_wEnd) return;
   }

   int side = g_score >= p_minVotes ? 1 : (g_score <= -p_minVotes ? -1 : 0);
   if(p_trend && side != g_regime) side = 0;                     // only with the direction of the day
   if(p_pullback && side != 0)
   {
      double e9 = Buf(hEMA9, 0, 2);
      bool ok = side > 0 ? (r[2].low <= e9 && r[1].close > r[2].high) : (r[2].high >= e9 && r[1].close < r[2].low);
      if(!ok) side = 0;
   }
   if(p_closeOpp && side != 0) CloseSide(-side, "signal inverse");
   if(side == 0 || g_vals[6] < MinVolRatio) return;

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK), bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(ask - bid > MaxSpreadATR * g_atr) { J(StringFormat("Signal ignore : spread %.2f > %.2f", ask - bid, MaxSpreadATR * g_atr)); return; }
   double price = side > 0 ? ask : bid, nearest;
   int existing = CountPositions(side, nearest, price);
   if(existing >= p_maxPos) return;
   if(nearest < p_spacing * g_atr) return;

   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double minDist = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   double slD, tpD;
   if(p_swing)
   {
      double ext = side > 0 ? r[1].low : r[1].high;
      for(int i = 1; i <= SwingBars; i++) ext = side > 0 ? MathMin(ext, r[i].low) : MathMax(ext, r[i].high);
      slD = MathMax(side * (price - ext), minDist);
      tpD = MathMax(p_tpR * slD, minDist);
   }
   else
   {
      slD = MathMax(p_slAtr * g_atr, minDist);
      tpD = MathMax(p_tpAtr * g_atr, minDist);
   }
   double lots = Lots(slD, existing);
   if(lots <= 0) return;
   double sl = NormalizeDouble(price - side * slD, digits), tp = NormalizeDouble(price + side * tpD, digits);
   J(StringFormat("Signal %s valide : %d/10 votes, confiance %.0f%%%s", side > 0 ? "d'achat" : "de vente", MathAbs(g_score),
                  (side > 0 ? g_pBuy : 1 - g_pBuy) * 100, p_trend ? ", tendance du jour OK" : ""));
   bool ok = side > 0 ? trade.Buy(lots, _Symbol, 0, sl, tp, "S12 " + p_name) : trade.Sell(lots, _Symbol, 0, sl, tp, "S12 " + p_name);
   if(ok) J(StringFormat("Position ouverte : %s %.2f lot a %s, TP %s, SL %s", side > 0 ? "Buy" : "Sell", lots,
            DoubleToString(price, digits), DoubleToString(tp, digits), DoubleToString(sl, digits)));
   else J("Ordre refuse : code " + IntegerToString(trade.ResultRetcode()));
}

//+------------------------------------------------------------------+
//| Panel                                                            |
//+------------------------------------------------------------------+
void Label(string name, int x, int y, string text, color c, int size = 9)
{
   if(ObjectFind(0, name) < 0)
   {
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetString(0, name, OBJPROP_FONT, "Consolas");
   }
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, size);
   ObjectSetInteger(0, name, OBJPROP_COLOR, c);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
}

void Panel()
{
   double bal = AccountInfoDouble(ACCOUNT_BALANCE), eq = AccountInfoDouble(ACCOUNT_EQUITY);
   int trades = 0, wins = 0; double sw = 0, sl = 0, today = 0;
   MqlDateTime d; TimeToStruct(TimeCurrent(), d); d.hour = 0; d.min = 0; d.sec = 0;
   datetime dayStart = StructToTime(d);
   if(HistorySelect(0, TimeCurrent()))
      for(int i = 0; i < HistoryDealsTotal(); i++)
      {
         ulong t = HistoryDealGetTicket(i);
         if(HistoryDealGetInteger(t, DEAL_MAGIC) != Magic || HistoryDealGetInteger(t, DEAL_ENTRY) != DEAL_ENTRY_OUT) continue;
         double p = HistoryDealGetDouble(t, DEAL_PROFIT) + HistoryDealGetDouble(t, DEAL_COMMISSION) + HistoryDealGetDouble(t, DEAL_SWAP);
         trades++; if(p > 0) { wins++; sw += p; } else sl += -p;
         if((datetime)HistoryDealGetInteger(t, DEAL_TIME) >= dayStart) today += p;
      }
   double aw = wins ? sw / wins : 0, al = (trades - wins) ? sl / (trades - wins) : 0;
   int y = 20, x = 10;
   Label("S12_t", x, y, "SCALPER 12 INDICATEURS  -  " + _Symbol + "  -  mode " + p_name, clrAqua, 11); y += 22;
   Label("S12_a", x, y, StringFormat("Solde %.2f   Equite %.2f   P&L jour %+.2f", bal, eq, today), clrWhite); y += 16;
   Label("S12_b", x, y, StringFormat("Trades %d   Reussite %.0f%%   Gain moy %.2f   Perte moy %.2f", trades, trades ? 100.0 * wins / trades : 0, aw, al), clrWhite); y += 16;
   Label("S12_c", x, y, StringFormat("Esperance par trade %+.2f   (gains %.2f / pertes %.2f)", trades ? (sw - sl) / trades : 0, sw, sl),
         sw >= sl ? clrLime : clrOrangeRed); y += 16;
   string reg = !p_trend ? "filtre off" : (g_regime > 0 ? "HAUSSIERE (achats seulement)" : (g_regime < 0 ? "BAISSIERE (ventes seulement)" : "neutre (pas de trade)"));
   Label("S12_r", x, y, "Tendance du jour : " + reg, g_regime > 0 ? clrLime : (g_regime < 0 ? clrOrangeRed : clrSilver)); y += 22;
   Label("S12_g", x, y, StringFormat("ACHAT %.1f%%   |   VENTE %.1f%%   (score %+d)", g_pBuy * 100, (1 - g_pBuy) * 100, g_score),
         g_pBuy >= 0.5 ? clrLime : clrOrangeRed, 11); y += 22;
   for(int i = 0; i < 12; i++)
   {
      string v = g_votes[i] > 0 ? "HAUSSIER" : (g_votes[i] < 0 ? "BAISSIER" : "neutre");
      Label("S12_i" + IntegerToString(i), x, y, StringFormat("%-12s %8.2f   %s", g_names[i], g_vals[i], v),
            g_votes[i] > 0 ? clrLime : (g_votes[i] < 0 ? clrOrangeRed : clrSilver), 8);
      y += 14;
   }
   y += 8;
   Label("S12_j", x, y, "JOURNAL", clrAqua); y += 16;
   for(int i = 0; i < 12; i++) { Label("S12_l" + IntegerToString(i), x, y, i < g_jn ? g_journal[i] : "", clrSilver, 8); y += 13; }
}

//+------------------------------------------------------------------+
int OnInit()
{
   ApplyPreset();
   trade.SetExpertMagicNumber(Magic);
   trade.SetTypeFillingBySymbol(_Symbol);
   trade.SetDeviationInPoints(30);
   hRSI = iRSI(_Symbol, PERIOD_M1, 14, PRICE_CLOSE);
   hMACD = iMACD(_Symbol, PERIOD_M1, 12, 26, 9, PRICE_CLOSE);
   hEMA20 = iMA(_Symbol, PERIOD_M1, 20, 0, MODE_EMA, PRICE_CLOSE);
   hEMA9 = iMA(_Symbol, PERIOD_M1, 9, 0, MODE_EMA, PRICE_CLOSE);
   hEMAH1 = iMA(_Symbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE);
   hBB = iBands(_Symbol, PERIOD_M1, 20, 0, 2.0, PRICE_CLOSE);
   hATR = iATR(_Symbol, PERIOD_M1, 14);
   hATR100 = iATR(_Symbol, PERIOD_M1, 100);
   if(hRSI == INVALID_HANDLE || hMACD == INVALID_HANDLE || hEMA20 == INVALID_HANDLE || hEMA9 == INVALID_HANDLE ||
      hEMAH1 == INVALID_HANDLE || hBB == INVALID_HANDLE || hATR == INVALID_HANDLE || hATR100 == INVALID_HANDLE) return INIT_FAILED;
   J("Demarrage sur " + _Symbol + ", mode " + p_name + StringFormat(", decalage serveur - New York %+d h", OffsetHours()));
   EventSetTimer(1);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   ObjectsDeleteAll(0, "S12_");
}

void OnTick()
{
   datetime bar = iTime(_Symbol, PERIOD_M1, 0);
   if(p_tick || bar != g_lastBar)
   {
      g_lastBar = bar;
      Cycle();
   }
}

void OnTimer() { Panel(); }
//+------------------------------------------------------------------+
