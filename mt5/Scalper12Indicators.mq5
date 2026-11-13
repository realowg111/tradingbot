//+------------------------------------------------------------------+
//| Scalper12Indicators.mq5                                          |
//| Video-style scalper: 12 indicators vote, a confidence gauge      |
//| (buy % / sell %), execution on every cycle with automatic TP/SL. |
//|                                                                  |
//| WARNING: the Python rebuild of these rules                       |
//| (scripts/xau_daytrade/scalper_backtest.py) lost money on gold    |
//| 2009-2026 and EURUSD 2009-2026 with every tested setting, even   |
//| without costs. Test on a demo account first.                     |
//+------------------------------------------------------------------+
#property copyright "tradingbot"
#property version   "1.00"
#property strict

#include <Trade/Trade.mqh>

input group "Signal"
input int    MinVotes          = 8;      // Votes alignes requis (sur 10) pour trader
input double GaugeSlope        = 0.35;   // Pente de la jauge (score -> probabilite)
input double MinVolRatio       = 0.8;    // Filtre volatilite : ATR14 / ATR100 minimum
input bool   CycleOnEveryTick  = false;  // false = 1 cycle par bougie M1 ; true = a chaque tick

input group "Sorties"
input double TP_ATR            = 0.5;    // Take profit en ATR(14) M1
input double SL_ATR            = 1.5;    // Stop loss en ATR(14) M1
input int    MaxHoldMinutes    = 60;     // Fermeture forcee apres N minutes (0 = off)
input bool   CloseOnOpposite   = true;   // Fermer si le signal s'inverse

input group "Taille et risque"
input double RiskPerTradePct   = 2.0;    // Risque par trade en % de l'equite (si FixedLot = 0)
input double FixedLot          = 0.0;    // Lot fixe (0 = calcul par le risque)
input int    MaxPositions      = 5;      // Positions simultanees max (meme sens)
input double MinSpacingATR     = 0.3;    // Ecart minimum entre deux entrees, en ATR
input double MaxSpreadATR      = 0.3;    // Pas d'entree si spread > x ATR
input double DailyStopPct      = 0.0;    // Arret pour la journee si perte > x % (0 = off)

input group "Horaires (heure du serveur)"
input int    StartHour         = 0;
input int    EndHour           = 24;

input group "Divers"
input long   Magic             = 12121212;
input bool   WriteCsvLog       = true;

CTrade trade;

int hRSI, hMACD, hEMA20, hEMAH1, hBB, hATR, hATR100;
datetime g_lastBar = 0;
double   g_dayStartEq = 0;
int      g_day = -1;
bool     g_halted = false;
string   g_journal[12];
int      g_jn = 0;

// last reading (for the panel)
string   g_names[12] = {"RSI 14", "Tendance H1", "Ecart MM20", "MACD", "Structure", "Bollinger",
                        "Volatilite", "VWAP", "Momentum 5", "Momentum 15", "Cassure", "Alignement"};
double   g_vals[12];
int      g_votes[12];
double   g_pBuy = 0.5;
int      g_score = 0;
double   g_atr = 0;

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
   FileWrite(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS), s, DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2));
   FileClose(h);
}

double Buf(int handle, int buffer, int shift)
{
   double b[];
   if(CopyBuffer(handle, buffer, shift, 1, b) < 1) return EMPTY_VALUE;
   return b[0];
}

bool DayVWAP(double &vwap)
{
   MqlDateTime d; TimeToStruct(TimeCurrent(), d);
   d.hour = 0; d.min = 0; d.sec = 0;
   datetime start = StructToTime(d);
   MqlRates r[];
   int n = CopyRates(_Symbol, PERIOD_M1, start, TimeCurrent(), r);
   if(n <= 0) return false;
   double pv = 0, v = 0;
   for(int i = 0; i < n - 1; i++)                      // closed bars only
   {
      double vol = (double)MathMax(r[i].tick_volume, 1);
      pv += (r[i].high + r[i].low + r[i].close) / 3.0 * vol; v += vol;
   }
   if(v <= 0) return false;
   vwap = pv / v;
   return true;
}

//+------------------------------------------------------------------+
//| 12 indicators -> 10 directional votes + volatility + alignment   |
//+------------------------------------------------------------------+
bool Read()
{
   MqlRates r[];
   ArraySetAsSeries(r, true);
   if(CopyRates(_Symbol, PERIOD_M1, 0, 40, r) < 40) return false;
   double c = r[1].close;                               // last closed M1 bar

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

   g_vals[0] = rsi;                g_votes[0] = rsi > 55 ? 1 : (rsi < 45 ? -1 : 0);
   g_vals[1] = (c - eh1) / atr;    g_votes[1] = c > eh1 ? 1 : (c < eh1 ? -1 : 0);
   g_vals[2] = (c - e20) / atr;    g_votes[2] = c > e20 ? 1 : (c < e20 ? -1 : 0);
   g_vals[3] = (macd - sig) / atr; g_votes[3] = macd > sig ? 1 : (macd < sig ? -1 : 0);
   double mid12 = (hi12 + lo12) / 2;
   g_vals[4] = (c - mid12) / atr;  g_votes[4] = c > mid12 ? 1 : (c < mid12 ? -1 : 0);
   g_vals[5] = (c - bbMid) / atr;  g_votes[5] = c > bbMid ? 1 : (c < bbMid ? -1 : 0);
   g_vals[6] = atr / atr100;       g_votes[6] = 0;                         // filter, not a direction
   g_vals[7] = (c - vwap) / atr;   g_votes[7] = c > vwap ? 1 : (c < vwap ? -1 : 0);
   g_vals[8] = (c - r[6].close) / atr;  g_votes[8] = c > r[6].close ? 1 : (c < r[6].close ? -1 : 0);
   g_vals[9] = (c - r[16].close) / atr; g_votes[9] = c > r[16].close ? 1 : (c < r[16].close ? -1 : 0);
   g_vals[10] = c > hi20 ? 1 : (c < lo20 ? -1 : 0); g_votes[10] = (int)g_vals[10];

   g_score = 0;
   for(int i = 0; i < 11; i++) g_score += g_votes[i];
   g_vals[11] = g_score;          g_votes[11] = g_score > 0 ? 1 : (g_score < 0 ? -1 : 0);
   g_pBuy = 1.0 / (1.0 + MathExp(-GaugeSlope * g_score));
   return true;
}

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
      if(s != side) continue;
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
   if(MaxHoldMinutes <= 0) return;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(!PositionSelectByTicket(t)) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol || PositionGetInteger(POSITION_MAGIC) != Magic) continue;
      if(TimeCurrent() - (datetime)PositionGetInteger(POSITION_TIME) >= MaxHoldMinutes * 60)
      {
         double p = PositionGetDouble(POSITION_PROFIT);
         if(trade.PositionClose(t)) J(StringFormat("Cloture (duree max) : %+.2f", p));
      }
   }
}

double Lots(double slDist)
{
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN), vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double lots = FixedLot;
   if(lots <= 0)
   {
      double tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE), ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
      if(tv <= 0 || ts <= 0 || slDist <= 0) return 0;
      double riskMoney = AccountInfoDouble(ACCOUNT_EQUITY) * RiskPerTradePct / 100.0;
      lots = riskMoney / (slDist / ts * tv);
   }
   lots = MathFloor(lots / step) * step;
   if(lots < vmin) lots = vmin;
   return MathMin(lots, vmax);
}

void Cycle()
{
   // new day
   MqlDateTime d; TimeToStruct(TimeCurrent(), d);
   if(d.day_of_year != g_day) { g_day = d.day_of_year; g_dayStartEq = AccountInfoDouble(ACCOUNT_EQUITY); g_halted = false; }
   if(DailyStopPct > 0 && !g_halted && AccountInfoDouble(ACCOUNT_EQUITY) < g_dayStartEq * (1 - DailyStopPct / 100.0))
   { g_halted = true; CloseSide(0, "arret journalier"); J("Arret pour la journee (perte max atteinte)"); }

   CloseExpired();
   if(!Read()) return;
   if(g_halted || d.hour < StartHour || d.hour >= EndHour) return;

   int side = g_score >= MinVotes ? 1 : (g_score <= -MinVotes ? -1 : 0);
   if(CloseOnOpposite && side != 0) CloseSide(-side, "signal inverse");
   if(side == 0) return;
   if(g_vals[6] < MinVolRatio) return;

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK), bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(ask - bid > MaxSpreadATR * g_atr) { J(StringFormat("Signal ignore : spread %.2f > %.2f", ask - bid, MaxSpreadATR * g_atr)); return; }
   double price = side > 0 ? ask : bid, nearest;
   if(CountPositions(side, nearest, price) >= MaxPositions) return;
   if(nearest < MinSpacingATR * g_atr) return;

   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double minDist = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   double slD = MathMax(SL_ATR * g_atr, minDist), tpD = MathMax(TP_ATR * g_atr, minDist);
   double lots = Lots(slD);
   if(lots <= 0) return;
   double sl = NormalizeDouble(price - side * slD, digits), tp = NormalizeDouble(price + side * tpD, digits);
   J(StringFormat("Signal %s valide : %d/10 votes, confiance %.0f%%", side > 0 ? "d'achat" : "de vente", MathAbs(g_score), (side > 0 ? g_pBuy : 1 - g_pBuy) * 100));
   bool ok = side > 0 ? trade.Buy(lots, _Symbol, 0, sl, tp, "S12") : trade.Sell(lots, _Symbol, 0, sl, tp, "S12");
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
   Label("S12_t", x, y, "SCALPER 12 INDICATEURS  -  " + _Symbol, clrAqua, 11); y += 22;
   Label("S12_a", x, y, StringFormat("Solde %.2f   Equite %.2f   P&L jour %+.2f", bal, eq, today), clrWhite); y += 16;
   Label("S12_b", x, y, StringFormat("Trades %d   Reussite %.0f%%   Gain moy %.2f   Perte moy %.2f", trades, trades ? 100.0 * wins / trades : 0, aw, al), clrWhite); y += 16;
   Label("S12_c", x, y, StringFormat("Esperance par trade %+.2f   (gains totaux %.2f / pertes totales %.2f)", trades ? (sw - sl) / trades : 0, sw, sl),
         sw >= sl ? clrLime : clrOrangeRed); y += 22;
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
   trade.SetExpertMagicNumber(Magic);
   trade.SetTypeFillingBySymbol(_Symbol);
   trade.SetDeviationInPoints(30);
   hRSI = iRSI(_Symbol, PERIOD_M1, 14, PRICE_CLOSE);
   hMACD = iMACD(_Symbol, PERIOD_M1, 12, 26, 9, PRICE_CLOSE);
   hEMA20 = iMA(_Symbol, PERIOD_M1, 20, 0, MODE_EMA, PRICE_CLOSE);
   hEMAH1 = iMA(_Symbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE);
   hBB = iBands(_Symbol, PERIOD_M1, 20, 0, 2.0, PRICE_CLOSE);
   hATR = iATR(_Symbol, PERIOD_M1, 14);
   hATR100 = iATR(_Symbol, PERIOD_M1, 100);
   if(hRSI == INVALID_HANDLE || hMACD == INVALID_HANDLE || hEMA20 == INVALID_HANDLE || hEMAH1 == INVALID_HANDLE ||
      hBB == INVALID_HANDLE || hATR == INVALID_HANDLE || hATR100 == INVALID_HANDLE) return INIT_FAILED;
   J("Demarrage sur " + _Symbol);
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
   if(CycleOnEveryTick || bar != g_lastBar)
   {
      g_lastBar = bar;
      Cycle();
   }
}

void OnTimer() { Panel(); }
//+------------------------------------------------------------------+
