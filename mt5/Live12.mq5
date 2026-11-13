//+------------------------------------------------------------------+
//| Live12.mq5 - version simple                                      |
//| 10 indicateurs votent. Si assez de votes : 6 positions ouvertes. |
//| Le groupe est ferme a +0.6 % (gain) ou -0.4 % (perte).          |
//+------------------------------------------------------------------+
#property version "1.00"
#include <Trade\Trade.mqh>

input int    MinVotes   = 5;      // Votes requis (sur 10)
input double LotScale   = 0.2;    // Taille des lots (0.2 pour 1000)
input double TargetPct  = 0.6;    // Ferme tout a +x % du solde
input double LossPct    = 0.4;    // Ferme tout a -x % du solde
input int    MaxMinutes = 10;     // Duree max d'une rafale (minutes)
input bool   VideoMode  = false;  // true = rythme de la video : 2 votes, rafale fermee apres 6 s, objectif +0.3 %
input int    MaxSeconds = 0;      // Ferme la rafale apres N secondes (0 = off)
input long   MagicNumber = 1212;

CTrade trade;
int hRSI, hMACD, hEMA20, hEMAH1, hBB, hATR;
int score = 0;
double startBalance = 0;
datetime openTime = 0;
int burstSide = 0;
// reglages effectifs (VideoMode les remplace)
int    useVotes;
double useTarget, useLoss;
int    useSeconds;
string lastError = "aucune";

//+------------------------------------------------------------------+
double Val(int handle, int buffer)
{
   double v[];
   if(CopyBuffer(handle, buffer, 0, 1, v) < 1) return 0;
   return v[0];
}

int Vote(double a, double b)
{
   if(a > b) return 1;
   if(a < b) return -1;
   return 0;
}

//--- calcule le score (de -10 a +10)
bool ComputeScore()
{
   MqlRates r[];
   ArraySetAsSeries(r, true);
   if(CopyRates(_Symbol, PERIOD_M1, 0, 25, r) < 25) return false;

   double price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double rsi   = Val(hRSI, 0);
   double macd  = Val(hMACD, 0);
   double sig   = Val(hMACD, 1);
   double e20   = Val(hEMA20, 0);
   double eh1   = Val(hEMAH1, 0);
   double mid   = Val(hBB, 0);
   if(rsi == 0 || e20 == 0 || eh1 == 0 || mid == 0) return false;

   double hi = r[1].high, lo = r[1].low;
   for(int i = 1; i <= 20; i++)
   {
      if(r[i].high > hi) hi = r[i].high;
      if(r[i].low < lo) lo = r[i].low;
   }

   score = 0;
   if(rsi > 55) score++;
   if(rsi < 45) score--;
   score += Vote(price, eh1);              // tendance H1
   score += Vote(price, e20);              // ecart MM20
   score += Vote(macd, sig);               // MACD
   score += Vote(price, (hi + lo) / 2);    // structure
   score += Vote(price, mid);              // Bollinger
   score += Vote(price, r[5].close);       // momentum 5
   score += Vote(price, r[15].close);      // momentum 15
   score += Vote(price, r[1].close);       // derniere bougie
   if(price > hi) score++;                 // cassure
   if(price < lo) score--;
   return true;
}

//--- nombre de positions du robot et leur resultat
int CountPositions(double &profit)
{
   int n = 0;
   profit = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      n++;
      profit += PositionGetDouble(POSITION_PROFIT);
   }
   return n;
}

void CloseAll(string reason)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      trade.PositionClose(ticket);
   }
   Print("Rafale fermee : ", reason);
   burstSide = 0;
}

double Lot(double base)
{
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double v = MathFloor(base * LotScale / step) * step;
   if(v < minLot) v = minLot;
   return NormalizeDouble(v, 2);
}

void OpenBurst(int side)
{
   double lots[6] = {0.30, 0.20, 0.15, 0.10, 0.05, 0.05};
   startBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   openTime = TimeCurrent();
   burstSide = side;
   for(int i = 0; i < 6; i++)
   {
      bool ok;
      if(side > 0) ok = trade.Buy(Lot(lots[i]), _Symbol);
      else ok = trade.Sell(Lot(lots[i]), _Symbol);
      if(!ok)
      {
         lastError = IntegerToString((int)trade.ResultRetcode()) + " " + trade.ResultComment();
         Print("Ordre refuse : ", lastError);
      }
   }
   Print("Rafale ouverte, score ", score);
}

//--- gestion du groupe de positions
void Manage()
{
   double profit;
   int n = CountPositions(profit);
   if(n == 0) return;
   if(startBalance <= 0) startBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   if(openTime == 0) openTime = TimeCurrent();
   double pct = 100.0 * profit / startBalance;
   if(pct >= useTarget) { CloseAll("objectif"); return; }
   if(pct <= -useLoss) { CloseAll("limite de perte"); return; }
   if(useSeconds > 0 && (long)(TimeCurrent() - openTime) >= (long)useSeconds) { CloseAll("duree max (secondes)"); return; }
   if((long)(TimeCurrent() - openTime) >= (long)MaxMinutes * 60) { CloseAll("duree max"); return; }
}

//+------------------------------------------------------------------+
int OnInit()
{
   useVotes = MinVotes; useTarget = TargetPct; useLoss = LossPct; useSeconds = MaxSeconds;
   if(VideoMode) { useVotes = 2; useTarget = 0.3; useLoss = 0.4; useSeconds = 6; }
   trade.SetExpertMagicNumber((ulong)MagicNumber);
   trade.SetDeviationInPoints(50);
   // mode d'execution accepte par le courtier (sinon les ordres sont refuses)
   long filling = SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   if((filling & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK) trade.SetTypeFilling(ORDER_FILLING_FOK);
   else if((filling & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC) trade.SetTypeFilling(ORDER_FILLING_IOC);
   else trade.SetTypeFilling(ORDER_FILLING_RETURN);
   hRSI   = iRSI(_Symbol, PERIOD_M1, 14, PRICE_CLOSE);
   hMACD  = iMACD(_Symbol, PERIOD_M1, 12, 26, 9, PRICE_CLOSE);
   hEMA20 = iMA(_Symbol, PERIOD_M1, 20, 0, MODE_EMA, PRICE_CLOSE);
   hEMAH1 = iMA(_Symbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE);
   hBB    = iBands(_Symbol, PERIOD_M1, 20, 0, 2.0, PRICE_CLOSE);
   EventSetTimer(1);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   Comment("");
}

void OnTick()
{
   Manage();
}

void OnTimer()
{
   Manage();
   if(!ComputeScore()) { Comment("Indicateurs pas encore prets"); return; }

   double profit;
   int n = CountPositions(profit);
   int side = 0;
   if(score >= useVotes) side = 1;
   if(score <= -useVotes) side = -1;

   if(n > 0 && side != 0 && side != burstSide) { CloseAll("signal inverse"); n = 0; }
   if(n == 0 && side != 0) OpenBurst(side);

   string allowed = "OUI";
   if(TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) == 0) allowed = "NON : bouton Trading Algo";
   else if(MQLInfoInteger(MQL_TRADE_ALLOWED) == 0) allowed = "NON : cocher 'Autoriser le trading algorithmique'";

   double buyPct = 50.0 + 5.0 * score;
   Comment("LIVE 12  -  ", _Symbol,
           "\nTrading autorise : ", allowed,
           "\nDerniere erreur d'ordre : ", lastError,
           "\nScore : ", score, " (requis +/-", useVotes, ")",
           "\nMode video : ", (VideoMode ? "OUI" : "non"), "   duree max rafale : ", (useSeconds > 0 ? IntegerToString(useSeconds) + " s" : IntegerToString(MaxMinutes) + " min"),
           "\nACHAT ", DoubleToString(buyPct, 0), " %   VENTE ", DoubleToString(100 - buyPct, 0), " %",
           "\nPositions : ", n, "   Resultat : ", DoubleToString(profit, 2),
           "\nSolde : ", DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2));
}
//+------------------------------------------------------------------+
