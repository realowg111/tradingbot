//+------------------------------------------------------------------+
//| Scalper12Live.mq5                                                |
//| 12 indicateurs votent, rafale de 6 positions, geree comme un     |
//| panier : objectif +0.6 %, limite -0.4 %, gain protege.           |
//| Version simplifiee : uniquement des fonctions MQL5 de base.      |
//+------------------------------------------------------------------+
#property copyright "tradingbot"
#property version   "2.00"

#include <Trade\Trade.mqh>

//--- reglages
input int    MinVotes      = 5;       // Votes alignes requis (sur 10)
input int    CycleSeconds  = 2;       // Un calcul toutes les N secondes
input double LotScale      = 0.2;     // Multiplie les lots (0.2 pour 1000)
input double Lot1          = 0.30;    // Lots de la rafale
input double Lot2          = 0.20;
input double Lot3          = 0.15;
input double Lot4          = 0.10;
input double Lot5          = 0.05;
input double Lot6          = 0.05;
input double TargetPct     = 0.6;     // Ferme la rafale a +x % du solde
input double LossLimitPct  = 0.4;     // Ferme la rafale a -x % du solde
input double LockStartPct  = 0.3;     // Des +x %...
input double LockKeepPct   = 50.0;    // ...ferme si le gain retombe sous ce % du meilleur
input int    MaxMinutes    = 10;      // Duree max d'une rafale
input bool   CloseOnFlip   = true;    // Ferme si le signal s'inverse
input double MaxSpreadATR  = 0.5;     // Pas de rafale si spread > x ATR
input long   MagicNumber   = 34343434;

CTrade trade;

int hRSI   = INVALID_HANDLE;
int hMACD  = INVALID_HANDLE;
int hEMA20 = INVALID_HANDLE;
int hEMAH1 = INVALID_HANDLE;
int hBB    = INVALID_HANDLE;
int hATR   = INVALID_HANDLE;
int hATR100 = INVALID_HANDLE;

string gNames[12];
double gVals[12];
int    gVotes[12];
int    gScore = 0;
double gBuy = 0.5;
double gAtr = 0.0;
int    gCalc = 0;
string gStatus = "demarrage";
string gLog[8];

int      gSide = 0;
double   gRef = 0.0;
double   gBest = 0.0;
datetime gOpenTime = 0;
int      gBaskets = 0;
int      gWins = 0;
double   gSumWin = 0.0;
double   gSumLoss = 0.0;

//+------------------------------------------------------------------+
void AddLog(string s)
{
   for(int i = 7; i > 0; i--)
      gLog[i] = gLog[i - 1];
   gLog[0] = TimeToString(TimeCurrent(), TIME_SECONDS) + "  " + s;
   Print("[Live12] ", s);
}

double ReadBuf(int handle, int buffer, int shift)
{
   double v[];
   if(CopyBuffer(handle, buffer, shift, 1, v) < 1)
      return EMPTY_VALUE;
   return v[0];
}

int Sign(double x)
{
   if(x > 0) return 1;
   if(x < 0) return -1;
   return 0;
}

//+------------------------------------------------------------------+
//| Les 12 indicateurs                                               |
//+------------------------------------------------------------------+
bool ReadIndicators()
{
   MqlRates r[];
   ArraySetAsSeries(r, true);
   if(CopyRates(_Symbol, PERIOD_M1, 0, 40, r) < 40)
      return false;

   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double c = (bid + ask) / 2.0;                       // prix en direct

   double rsi    = ReadBuf(hRSI, 0, 0);
   double macd   = ReadBuf(hMACD, 0, 0);
   double sig    = ReadBuf(hMACD, 1, 0);
   double e20    = ReadBuf(hEMA20, 0, 0);
   double eh1    = ReadBuf(hEMAH1, 0, 0);
   double mid    = ReadBuf(hBB, 0, 0);
   double atr    = ReadBuf(hATR, 0, 1);
   double atr100 = ReadBuf(hATR100, 0, 1);
   if(rsi == EMPTY_VALUE || macd == EMPTY_VALUE || sig == EMPTY_VALUE || e20 == EMPTY_VALUE ||
      eh1 == EMPTY_VALUE || mid == EMPTY_VALUE || atr == EMPTY_VALUE || atr100 == EMPTY_VALUE)
      return false;
   if(atr <= 0.0 || atr100 <= 0.0)
      return false;

   // VWAP du jour (volume de ticks)
   double vwap = c;
   MqlDateTime d;
   TimeToStruct(TimeCurrent(), d);
   d.hour = 0; d.min = 0; d.sec = 0;
   MqlRates day[];
   int n = CopyRates(_Symbol, PERIOD_M1, StructToTime(d), TimeCurrent(), day);
   if(n > 1)
   {
      double pv = 0.0, vv = 0.0;
      for(int i = 0; i < n - 1; i++)
      {
         double vol = 1.0;
         if(day[i].tick_volume > 0) vol = (double)day[i].tick_volume;
         pv += (day[i].high + day[i].low + day[i].close) / 3.0 * vol;
         vv += vol;
      }
      if(vv > 0.0) vwap = pv / vv;
   }

   double hi12 = r[1].high, lo12 = r[1].low, hi20 = r[1].high, lo20 = r[1].low;
   for(int k = 1; k <= 20; k++)
   {
      if(k <= 12)
      {
         if(r[k].high > hi12) hi12 = r[k].high;
         if(r[k].low < lo12) lo12 = r[k].low;
      }
      if(r[k].high > hi20) hi20 = r[k].high;
      if(r[k].low < lo20) lo20 = r[k].low;
   }
   gAtr = atr;

   gVals[0] = rsi;
   gVotes[0] = 0;
   if(rsi > 55.0) gVotes[0] = 1;
   if(rsi < 45.0) gVotes[0] = -1;
   gVals[1] = (c - eh1) / atr;          gVotes[1] = Sign(c - eh1);
   gVals[2] = (c - e20) / atr;          gVotes[2] = Sign(c - e20);
   gVals[3] = (macd - sig) / atr;       gVotes[3] = Sign(macd - sig);
   gVals[4] = (c - (hi12 + lo12) / 2.0) / atr; gVotes[4] = Sign(c - (hi12 + lo12) / 2.0);
   gVals[5] = (c - mid) / atr;          gVotes[5] = Sign(c - mid);
   gVals[6] = atr / atr100;             gVotes[6] = 0;
   gVals[7] = (c - vwap) / atr;         gVotes[7] = Sign(c - vwap);
   gVals[8] = (c - r[5].close) / atr;   gVotes[8] = Sign(c - r[5].close);
   gVals[9] = (c - r[15].close) / atr;  gVotes[9] = Sign(c - r[15].close);
   gVotes[10] = 0;
   if(c > hi20) gVotes[10] = 1;
   if(c < lo20) gVotes[10] = -1;
   gVals[10] = gVotes[10];

   gScore = 0;
   for(int j = 0; j < 11; j++)
      gScore += gVotes[j];
   gVals[11] = gScore;
   gVotes[11] = Sign(gScore);
   gBuy = 1.0 / (1.0 + MathExp(-0.35 * gScore));
   return true;
}

//+------------------------------------------------------------------+
//| Panier                                                           |
//+------------------------------------------------------------------+
int CountBasket(double &pnl)
{
   int n = 0;
   pnl = 0.0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      n++;
      pnl += PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
   }
   return n;
}

void CloseBasket(string why)
{
   double pnl = 0.0;
   int n = CountBasket(pnl);
   if(n == 0) return;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      if(!trade.PositionClose(t))
         AddLog("Fermeture refusee, code " + IntegerToString((int)trade.ResultRetcode()));
   }
   gBaskets++;
   if(pnl > 0.0) { gWins++; gSumWin += pnl; }
   else gSumLoss += -pnl;
   AddLog(why + " : rafale fermee " + DoubleToString(pnl, 2));
   gSide = 0;
}

double NormLot(double lots)
{
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(step <= 0.0) step = 0.01;
   double v = MathFloor(lots / step + 0.000001) * step;
   if(v < vmin) v = vmin;
   if(v > vmax) v = vmax;
   return NormalizeDouble(v, 2);
}

void OpenBurst(int side)
{
   double lots[6];
   lots[0] = Lot1; lots[1] = Lot2; lots[2] = Lot3; lots[3] = Lot4; lots[4] = Lot5; lots[5] = Lot6;
   gRef = AccountInfoDouble(ACCOUNT_BALANCE);
   gBest = 0.0;
   gSide = side;
   gOpenTime = TimeCurrent();
   if(side > 0) AddLog("Signal d'achat valide, votes " + IntegerToString(gScore));
   else AddLog("Signal de vente valide, votes " + IntegerToString(gScore));
   int opened = 0;
   for(int i = 0; i < 6; i++)
   {
      if(lots[i] <= 0.0) continue;
      double v = NormLot(lots[i] * LotScale);
      bool ok;
      if(side > 0) ok = trade.Buy(v, _Symbol, 0.0, 0.0, 0.0, "Live12");
      else ok = trade.Sell(v, _Symbol, 0.0, 0.0, 0.0, "Live12");
      if(ok) opened++;
      else AddLog("Ordre refuse, code " + IntegerToString((int)trade.ResultRetcode()));
   }
   if(opened > 0) AddLog("Rafale ouverte : " + IntegerToString(opened) + " positions");
   else gSide = 0;
}

void ManageBasket()
{
   double pnl = 0.0;
   int n = CountBasket(pnl);
   if(n == 0) { gSide = 0; return; }
   if(gRef <= 0.0) gRef = AccountInfoDouble(ACCOUNT_BALANCE);
   if(gOpenTime == 0) gOpenTime = TimeCurrent();
   double pct = 100.0 * pnl / gRef;
   if(pct > gBest) gBest = pct;
   if(TargetPct > 0.0 && pct >= TargetPct) { CloseBasket("Objectif"); return; }
   if(LossLimitPct > 0.0 && pct <= -LossLimitPct) { CloseBasket("Limite de perte"); return; }
   if(LockStartPct > 0.0 && gBest >= LockStartPct && pct <= gBest * LockKeepPct / 100.0) { CloseBasket("Gain protege"); return; }
   long age = (long)(TimeCurrent() - gOpenTime);
   if(MaxMinutes > 0 && age >= (long)MaxMinutes * 60) { CloseBasket("Duree max"); return; }
}

//+------------------------------------------------------------------+
//| Un calcul                                                        |
//+------------------------------------------------------------------+
void RunCycle()
{
   if(!ReadIndicators()) { gStatus = "indicateurs pas prets (historique M1)"; return; }
   gCalc++;
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   int side = 0;
   if(gScore >= MinVotes) side = 1;
   if(gScore <= -MinVotes) side = -1;
   string base = "calcul " + IntegerToString(gCalc) + " | votes " + IntegerToString(gScore) + " (requis " + IntegerToString(MinVotes) + ")";

   double pnl = 0.0;
   int n = CountBasket(pnl);
   if(n > 0)
   {
      if(CloseOnFlip && side != 0 && gSide != 0 && side != gSide)
         CloseBasket("Signal inverse");
      else
      {
         double ref = gRef;
         if(ref <= 0.0) ref = AccountInfoDouble(ACCOUNT_BALANCE);
         gStatus = base + " | rafale de " + IntegerToString(n) + " : " + DoubleToString(pnl, 2) +
                   " (" + DoubleToString(100.0 * pnl / ref, 2) + " %)";
         return;
      }
   }
   if(TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) == 0 || MQLInfoInteger(MQL_TRADE_ALLOWED) == 0)
   { gStatus = base + " | BLOQUE : activer Trading Algo"; return; }
   if(side == 0) { gStatus = base + " | attend : pas assez de votes"; return; }
   if(ask - bid > MaxSpreadATR * gAtr) { gStatus = base + " | attend : spread trop large"; return; }
   gStatus = base + " | RAFALE";
   OpenBurst(side);
}

//+------------------------------------------------------------------+
//| Panneau                                                          |
//+------------------------------------------------------------------+
void SetLabel(string name, int y, string text, color clr)
{
   if(ObjectFind(0, name) < 0)
   {
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_XDISTANCE, 10);
      ObjectSetString(0, name, OBJPROP_FONT, "Consolas");
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 9);
   }
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   if(StringLen(text) == 0) text = " ";
   ObjectSetString(0, name, OBJPROP_TEXT, text);
}

void DrawPanel()
{
   int y = 20;
   SetLabel("L12_t", y, "LIVE 12 INDICATEURS - " + _Symbol, clrAqua); y += 18;
   SetLabel("L12_a", y, "Solde " + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) +
            "   Equite " + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2), clrWhite); y += 16;
   color tc = clrLime;
   if(gSumLoss > gSumWin) tc = clrOrangeRed;
   SetLabel("L12_b", y, "Rafales " + IntegerToString(gBaskets) + "   gagnantes " + IntegerToString(gWins) +
            "   total " + DoubleToString(gSumWin - gSumLoss, 2), tc); y += 16;
   SetLabel("L12_s", y, gStatus, clrYellow); y += 18;
   color gc = clrLime;
   if(gBuy < 0.5) gc = clrOrangeRed;
   SetLabel("L12_g", y, "ACHAT " + DoubleToString(gBuy * 100.0, 1) + " %   |   VENTE " +
            DoubleToString((1.0 - gBuy) * 100.0, 1) + " %", gc); y += 18;
   for(int i = 0; i < 12; i++)
   {
      string v = "neutre";
      color c = clrSilver;
      if(gVotes[i] > 0) { v = "HAUSSIER"; c = clrLime; }
      if(gVotes[i] < 0) { v = "BAISSIER"; c = clrOrangeRed; }
      SetLabel("L12_i" + IntegerToString(i), y, gNames[i] + "  " + DoubleToString(gVals[i], 2) + "  " + v, c);
      y += 14;
   }
   y += 6;
   for(int k = 0; k < 8; k++)
   {
      SetLabel("L12_l" + IntegerToString(k), y, gLog[k], clrSilver);
      y += 14;
   }
}

//+------------------------------------------------------------------+
int OnInit()
{
   gNames[0] = "RSI 14";      gNames[1] = "Tendance H1"; gNames[2] = "Ecart MM20";  gNames[3] = "MACD";
   gNames[4] = "Structure";   gNames[5] = "Bollinger";   gNames[6] = "Volatilite";  gNames[7] = "VWAP";
   gNames[8] = "Momentum 5";  gNames[9] = "Momentum 15"; gNames[10] = "Cassure";    gNames[11] = "Alignement";
   for(int i = 0; i < 8; i++) gLog[i] = "";

   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetDeviationInPoints(30);

   hRSI    = iRSI(_Symbol, PERIOD_M1, 14, PRICE_CLOSE);
   hMACD   = iMACD(_Symbol, PERIOD_M1, 12, 26, 9, PRICE_CLOSE);
   hEMA20  = iMA(_Symbol, PERIOD_M1, 20, 0, MODE_EMA, PRICE_CLOSE);
   hEMAH1  = iMA(_Symbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE);
   hBB     = iBands(_Symbol, PERIOD_M1, 20, 0, 2.0, PRICE_CLOSE);
   hATR    = iATR(_Symbol, PERIOD_M1, 14);
   hATR100 = iATR(_Symbol, PERIOD_M1, 100);
   if(hRSI == INVALID_HANDLE || hMACD == INVALID_HANDLE || hEMA20 == INVALID_HANDLE || hEMAH1 == INVALID_HANDLE ||
      hBB == INVALID_HANDLE || hATR == INVALID_HANDLE || hATR100 == INVALID_HANDLE)
   {
      Print("Erreur de creation des indicateurs");
      return INIT_FAILED;
   }
   int secs = CycleSeconds;
   if(secs < 1) secs = 1;
   EventSetTimer(secs);
   AddLog("Demarrage sur " + _Symbol);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   ObjectsDeleteAll(0, "L12_");
}

void OnTick()
{
   ManageBasket();
}

void OnTimer()
{
   ManageBasket();
   RunCycle();
   DrawPanel();
}
//+------------------------------------------------------------------+
