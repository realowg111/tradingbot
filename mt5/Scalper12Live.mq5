//+------------------------------------------------------------------+
//| Scalper12Live.mq5                                                |
//| One behaviour only, the one of the TikTok live, with limits:     |
//|  - every 5 s, 12 indicators vote -> gauge BUY % / SELL %         |
//|  - 7 of 10 votes aligned -> a burst of 6 positions at once,      |
//|    without individual SL/TP                                      |
//|  - the burst is managed as one basket:                           |
//|      closed at +1 % of the balance (target)                      |
//|      closed at -0.7 % of the balance (loss limit)                |
//|      once it reached +0.5 %, closed if it falls back to half     |
//|      of its best gain                                            |
//|      closed after 30 minutes or if the signal flips              |
//| Demo first. Python tests of these indicators on 2009-2026 gold   |
//| did not find a lasting edge after costs.                         |
//+------------------------------------------------------------------+
#property copyright "tradingbot"
#property version   "1.00"
#property strict

#include <Trade/Trade.mqh>

input group "Signal"
input int    MinVotes         = 7;      // Votes alignes requis (sur 10)
input int    CycleSeconds     = 5;      // Un calcul toutes les N secondes

input group "Rafale"
input string Lots             = "0.30,0.20,0.15,0.10,0.05,0.05"; // Lots de la rafale
input double LotScale         = 0.2;    // Multiplie tous les lots (0.2 conseille pour 1 000)

input group "Panier (en % du solde)"
input double TargetPct        = 1.0;    // Objectif : ferme toute la rafale a +x %
input double LossLimitPct     = 0.7;    // Limite : ferme toute la rafale a -x %
input double LockStartPct     = 0.5;    // Protection : des que la rafale a atteint +x %...
input double LockKeepPct      = 50.0;   // ...ferme si elle retombe sous ce % de son meilleur gain
input int    MaxMinutes       = 30;     // Duree max d'une rafale
input bool   CloseOnFlip      = true;   // Ferme la rafale si le signal s'inverse

input group "Divers"
input double MaxSpreadATR     = 0.5;    // Pas de rafale si spread > x ATR(14) M1
input long   Magic            = 34343434;

CTrade trade;
int hRSI, hMACD, hEMA20, hEMAH1, hBB, hATR, hATR100;

string g_names[12] = {"RSI 14", "Tendance H1", "Ecart MM20", "MACD", "Structure", "Bollinger",
                      "Volatilite", "VWAP", "Momentum 5", "Momentum 15", "Cassure", "Alignement"};
double g_vals[12];
int    g_votes[12];
int    g_score = 0;
double g_pBuy = 0.5, g_atr = 0;
long   g_calc = 0;
string g_status = "demarrage...";
string g_journal[10];
int    g_jn = 0;
ulong  g_lastCycle = 0;

int    g_side = 0;              // direction of the open burst
double g_ref = 0;               // balance when the burst was opened
double g_best = 0;              // best basket gain in %
datetime g_openTime = 0;
int    g_baskets = 0, g_basketWins = 0;
double g_sumWin = 0, g_sumLoss = 0;

//+------------------------------------------------------------------+
void J(string s)
{
   for(int i = 9; i > 0; i--) g_journal[i] = g_journal[i - 1];
   g_journal[0] = TimeToString(TimeCurrent(), TIME_SECONDS) + "  " + s;
   if(g_jn < 10) g_jn++;
   Print("[Live12] ", s);
}

double Buf(int h, int b, int shift)
{
   double x[];
   if(CopyBuffer(h, b, shift, 1, x) < 1) return EMPTY_VALUE;
   return x[0];
}

//+------------------------------------------------------------------+
//| 12 indicators -> votes, score and gauge                          |
//+------------------------------------------------------------------+
bool Read()
{
   MqlRates r[];
   ArraySetAsSeries(r, true);
   if(CopyRates(_Symbol, PERIOD_M1, 0, 40, r) < 40) return false;
   double c = r[1].close;
   double rsi = Buf(hRSI, 0, 1), macd = Buf(hMACD, 0, 1), sig = Buf(hMACD, 1, 1);
   double e20 = Buf(hEMA20, 0, 1), eh1 = Buf(hEMAH1, 0, 1), mid = Buf(hBB, 0, 1);
   double atr = Buf(hATR, 0, 1), atr100 = Buf(hATR100, 0, 1);
   if(rsi == EMPTY_VALUE || macd == EMPTY_VALUE || e20 == EMPTY_VALUE || eh1 == EMPTY_VALUE ||
      mid == EMPTY_VALUE || atr == EMPTY_VALUE || atr100 == EMPTY_VALUE || atr <= 0) return false;

   // VWAP of the day (tick volume)
   MqlDateTime d; TimeToStruct(TimeCurrent(), d); d.hour = 0; d.min = 0; d.sec = 0;
   MqlRates day[];
   double vwap = c;
   int n = CopyRates(_Symbol, PERIOD_M1, StructToTime(d), TimeCurrent(), day);
   if(n > 1)
   {
      double pv = 0, v = 0;
      for(int i = 0; i < n - 1; i++)
      {
         double vol = (double)MathMax(day[i].tick_volume, 1);
         pv += (day[i].high + day[i].low + day[i].close) / 3.0 * vol; v += vol;
      }
      vwap = pv / v;
   }
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
   double m12 = (hi12 + lo12) / 2;
   g_vals[4] = (c - m12) / atr;         g_votes[4] = c > m12 ? 1 : (c < m12 ? -1 : 0);
   g_vals[5] = (c - mid) / atr;         g_votes[5] = c > mid ? 1 : (c < mid ? -1 : 0);
   g_vals[6] = atr / atr100;            g_votes[6] = 0;
   g_vals[7] = (c - vwap) / atr;        g_votes[7] = c > vwap ? 1 : (c < vwap ? -1 : 0);
   g_vals[8] = (c - r[6].close) / atr;  g_votes[8] = c > r[6].close ? 1 : (c < r[6].close ? -1 : 0);
   g_vals[9] = (c - r[16].close) / atr; g_votes[9] = c > r[16].close ? 1 : (c < r[16].close ? -1 : 0);
   g_vals[10] = c > hi20 ? 1 : (c < lo20 ? -1 : 0); g_votes[10] = (int)g_vals[10];
   g_score = 0;
   for(int i = 0; i < 11; i++) g_score += g_votes[i];
   g_vals[11] = g_score;                g_votes[11] = g_score > 0 ? 1 : (g_score < 0 ? -1 : 0);
   g_pBuy = 1.0 / (1.0 + MathExp(-0.35 * g_score));
   return true;
}

//+------------------------------------------------------------------+
//| Basket helpers                                                   |
//+------------------------------------------------------------------+
int Basket(double &pnl)
{
   int n = 0; pnl = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(!PositionSelectByTicket(t)) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol || PositionGetInteger(POSITION_MAGIC) != Magic) continue;
      n++; pnl += PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
   }
   return n;
}

void CloseBasket(string why)
{
   double pnl; int n = Basket(pnl);
   if(n == 0) return;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(!PositionSelectByTicket(t)) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol || PositionGetInteger(POSITION_MAGIC) != Magic) continue;
      if(!trade.PositionClose(t)) J("Fermeture refusee : code " + IntegerToString(trade.ResultRetcode()));
   }
   g_baskets++;
   if(pnl > 0) { g_basketWins++; g_sumWin += pnl; } else g_sumLoss += -pnl;
   J(StringFormat("%s : rafale fermee %+.2f %s", why, pnl, AccountInfoString(ACCOUNT_CURRENCY)));
   g_side = 0;
}

double NormLot(double lots)
{
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN), vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   lots = MathFloor(lots / step + 1e-9) * step;
   return MathMin(MathMax(lots, vmin), vmax);
}

void OpenBurst(int side)
{
   string parts[];
   int n = StringSplit(Lots, ',', parts);
   if(n <= 0) { J("Reglage Lots invalide"); return; }
   g_ref = AccountInfoDouble(ACCOUNT_BALANCE); g_best = 0; g_side = side; g_openTime = TimeCurrent();
   J(StringFormat("Signal %s valide : %d/10 votes, confiance %.0f%%", side > 0 ? "d'achat" : "de vente",
                  MathAbs(g_score), (side > 0 ? g_pBuy : 1 - g_pBuy) * 100));
   int opened = 0;
   for(int i = 0; i < n; i++)
   {
      StringTrimLeft(parts[i]); StringTrimRight(parts[i]);
      double lot = NormLot(StringToDouble(parts[i]) * LotScale);
      bool ok = side > 0 ? trade.Buy(lot, _Symbol, 0, 0, 0, "Live12") : trade.Sell(lot, _Symbol, 0, 0, 0, "Live12");
      if(ok) opened++;
      else J(StringFormat("Ordre refuse : code %d (%s)", trade.ResultRetcode(), trade.ResultRetcodeDescription()));
   }
   if(opened > 0) J(StringFormat("Rafale ouverte : %d %s", opened, side > 0 ? "achats" : "ventes"));
   else g_side = 0;
}

//+------------------------------------------------------------------+
//| Basket management (every tick and every second)                  |
//+------------------------------------------------------------------+
void Manage()
{
   double pnl; int n = Basket(pnl);
   if(n == 0) { g_side = 0; return; }
   if(g_ref <= 0) g_ref = AccountInfoDouble(ACCOUNT_BALANCE);       // after a restart
   if(g_openTime == 0) g_openTime = TimeCurrent();
   double pct = 100.0 * pnl / g_ref;
   if(pct > g_best) g_best = pct;
   if(TargetPct > 0 && pct >= TargetPct)            { CloseBasket(StringFormat("Objectif %+.2f%%", pct)); return; }
   if(LossLimitPct > 0 && pct <= -LossLimitPct)     { CloseBasket(StringFormat("Limite de perte %+.2f%%", pct)); return; }
   if(LockStartPct > 0 && g_best >= LockStartPct && pct <= g_best * LockKeepPct / 100.0)
   { CloseBasket(StringFormat("Gain protege %+.2f%% (max %+.2f%%)", pct, g_best)); return; }
   if(MaxMinutes > 0 && TimeCurrent() - g_openTime >= MaxMinutes * 60) { CloseBasket("Duree max"); return; }
}

//+------------------------------------------------------------------+
//| One cycle                                                        |
//+------------------------------------------------------------------+
void Cycle()
{
   if(!Read()) { g_status = "indicateurs pas encore prets (historique M1)"; return; }
   g_calc++;
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK), bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   int side = g_score >= MinVotes ? 1 : (g_score <= -MinVotes ? -1 : 0);
   double pnl; int n = Basket(pnl);
   string base = StringFormat("calcul %I64d | votes %+d (requis +/-%d)", g_calc, g_score, MinVotes);
   if(n > 0)
   {
      if(CloseOnFlip && side != 0 && g_side != 0 && side != g_side) { CloseBasket("Signal inverse"); n = 0; }
      else
      {
         double ref = g_ref > 0 ? g_ref : AccountInfoDouble(ACCOUNT_BALANCE);
         g_status = base + StringFormat(" | rafale de %d : %+.2f (%+.2f%%), objectif +%.2f%%, limite -%.2f%%",
                                        n, pnl, 100.0 * pnl / ref, TargetPct, LossLimitPct);
         return;
      }
   }
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED))
   { g_status = base + " | BLOQUE : activer 'Trading Algo' et 'Autoriser le trading algorithmique'"; return; }
   if(side == 0) { g_status = base + " | attend : pas assez de votes alignes"; return; }
   if(ask - bid > MaxSpreadATR * g_atr) { g_status = base + StringFormat(" | attend : spread %.2f > %.2f", ask - bid, MaxSpreadATR * g_atr); return; }
   g_status = base + " | RAFALE";
   OpenBurst(side);
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
   ObjectSetString(0, name, OBJPROP_TEXT, StringLen(text) > 0 ? text : " ");
}

void Panel()
{
   int x = 10, y = 20;
   double bal = AccountInfoDouble(ACCOUNT_BALANCE), eq = AccountInfoDouble(ACCOUNT_EQUITY);
   Label("L12_t", x, y, "LIVE 12 INDICATEURS  -  " + _Symbol, clrAqua, 11); y += 22;
   Label("L12_a", x, y, StringFormat("Solde %.2f   Equite %.2f", bal, eq), clrWhite); y += 16;
   double aw = g_basketWins ? g_sumWin / g_basketWins : 0, al = (g_baskets - g_basketWins) ? g_sumLoss / (g_baskets - g_basketWins) : 0;
   Label("L12_b", x, y, StringFormat("Rafales %d   gagnantes %d   gain moy %.2f   perte moy %.2f   total %+.2f",
         g_baskets, g_basketWins, aw, al, g_sumWin - g_sumLoss), g_sumWin >= g_sumLoss ? clrLime : clrOrangeRed); y += 16;
   Label("L12_s", x, y, g_status, clrYellow, 8); y += 20;
   Label("L12_g", x, y, StringFormat("ACHAT %.1f%%   |   VENTE %.1f%%   (score %+d)", g_pBuy * 100, (1 - g_pBuy) * 100, g_score),
         g_pBuy >= 0.5 ? clrLime : clrOrangeRed, 11); y += 22;
   for(int i = 0; i < 12; i++)
   {
      string v = g_votes[i] > 0 ? "HAUSSIER" : (g_votes[i] < 0 ? "BAISSIER" : "neutre");
      Label("L12_i" + IntegerToString(i), x, y, StringFormat("%-12s %8.2f   %s", g_names[i], g_vals[i], v),
            g_votes[i] > 0 ? clrLime : (g_votes[i] < 0 ? clrOrangeRed : clrSilver), 8);
      y += 14;
   }
   y += 8;
   Label("L12_j", x, y, "JOURNAL", clrAqua); y += 16;
   for(int i = 0; i < 10; i++) { Label("L12_l" + IntegerToString(i), x, y, i < g_jn ? g_journal[i] : "", clrSilver, 8); y += 13; }
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

void OnDeinit(const int reason) { EventKillTimer(); ObjectsDeleteAll(0, "L12_"); }

void OnTick() { Manage(); }

void OnTimer()
{
   Manage();
   if(GetTickCount64() - g_lastCycle >= (ulong)CycleSeconds * 1000)
   {
      g_lastCycle = GetTickCount64();
      Cycle();
   }
   Panel();
}
//+------------------------------------------------------------------+
