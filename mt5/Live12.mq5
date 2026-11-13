//+------------------------------------------------------------------+
//| Live12.mq5 - boucle continue comme dans la video                 |
//|                                                                  |
//| 1. ANALYSE  : 3 a 5 s de lecture des 12 indicateurs (jauge       |
//|               ACHAT % / VENTE %), seule pause du robot           |
//| 2. RAFALE   : 6 positions du cote dominant                       |
//| 3. SORTIES  : chaque position a son TP ; la plus grosse a le TP  |
//|               le plus proche et se ferme en premier en profit,   |
//|               puis le reste suit (stop a l'entree, puis suiveur) |
//| 4. PERTES   : rafale fermee si le prix n'est pas parti dans le   |
//|               bon sens apres N s, ou s'il va contre elle de      |
//|               x ATR (le spread n'est pas compte comme une perte) |
//| 5. retour a l'analyse, en boucle                                 |
//+------------------------------------------------------------------+
#property version "2.00"
#include <Trade\Trade.mqh>

input int    ReadSeconds  = 4;      // Analyse avant chaque rafale (secondes)
input double LotScale     = 0.1;    // Taille des lots (0.1 pour 600, 0.2 pour 1000)
input double TPScale      = 1.0;    // Multiplie toutes les distances de TP
input double LossATR      = 0.6;    // Ferme tout si le prix va contre la rafale de x ATR (spread non compte)
input double HardLossPct  = 3.0;    // Securite : ferme tout si la perte atteint x % du solde
input int    CutSeconds   = 30;     // Ferme tout si le prix n'est pas alle dans le bon sens apres N s
input int    MaxSeconds   = 180;    // Duree max d'une rafale
input double TrailATR     = 0.3;    // Distance du stop suiveur du reste, en ATR
input double SafetySL_ATR = 2.0;    // Stop de securite chez le courtier, en ATR (coupure)
input long   MagicNumber  = 1212;
input bool   LiveTikTok   = false;  // true = exactement comme le live : lots du live, sans stop, ferme tout a +TikTokTargetPct
input double TikTokTargetPct = 3.0; // Live : ferme toute la rafale quand le gain atteint x % du solde
input double TikTokStopPct   = 0.0; // Live : arret d'urgence a -x % du solde (0 = aucun, comme le live)

CTrade trade;
int hRSI, hMACD, hEMA20, hEMAH1, hBB, hATR;

// lots de la rafale : le 1er (le plus gros) a le TP le plus proche
double lots[6]  = {0.30, 0.20, 0.15, 0.10, 0.05, 0.05};
double tpATR[6] = {0.15, 0.25, 0.35, 0.50, 0.70, 1.00};
// lots vus dans le live TikTok pour un compte d'environ 500
double liveLots[6] = {0.08, 0.08, 0.05, 0.10, 0.15, 0.05};

int    score = 0;
double atr = 0;
int    phase = 0;          // 0 = analyse, 1 = rafale ouverte
int    readCount = 0;
int    readSum = 0;
int    burstSide = 0;
int    burstSize = 0;
double startBalance = 0;
datetime openTime = 0;
int    bursts = 0, winBursts = 0;
double totalResult = 0;
string lastEvent = "demarrage";
string lastError = "aucune";

//+------------------------------------------------------------------+
double Val(int handle, int buffer, int shift)
{
   double v[];
   if(CopyBuffer(handle, buffer, shift, 1, v) < 1) return 0;
   return v[0];
}

int Vote(double a, double b)
{
   if(a > b) return 1;
   if(a < b) return -1;
   return 0;
}

//--- les 12 indicateurs -> score de -10 a +10
bool ComputeScore()
{
   MqlRates r[];
   ArraySetAsSeries(r, true);
   if(CopyRates(_Symbol, PERIOD_M1, 0, 25, r) < 25) return false;

   double price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double rsi  = Val(hRSI, 0, 0);
   double macd = Val(hMACD, 0, 0);
   double sig  = Val(hMACD, 1, 0);
   double e20  = Val(hEMA20, 0, 0);
   double eh1  = Val(hEMAH1, 0, 0);
   double mid  = Val(hBB, 0, 0);
   atr = Val(hATR, 0, 1);
   if(rsi == 0 || e20 == 0 || eh1 == 0 || mid == 0 || atr <= 0) return false;

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

//--- positions du robot
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

void EndBurst(string reason)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      trade.PositionClose(ticket);
   }
   double result = AccountInfoDouble(ACCOUNT_BALANCE) - startBalance;
   bursts++;
   totalResult += result;
   if(result > 0) winBursts++;
   lastEvent = reason + " : rafale " + DoubleToString(result, 2) + " a " + TimeToString(TimeTradeServer(), TIME_SECONDS);
   Print(lastEvent);
   phase = 0; readCount = 0; readSum = 0;        // retour a l'analyse
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
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   startBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   openTime = TimeTradeServer();
   burstSide = side;
   burstSize = 0;
   for(int i = 0; i < 6; i++)
   {
      double price, sl, tp;
      bool ok;
      if(LiveTikTok)
      {
         // comme le live : taille proportionnelle au solde (lots du live pour 500), ni stop ni TP
         double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
         double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
         double v = MathFloor(liveLots[i] * startBalance / 500.0 / step) * step;
         if(v < minLot) v = minLot;
         v = NormalizeDouble(v, 2);
         if(side > 0) ok = trade.Buy(v, _Symbol, 0, 0, 0);
         else ok = trade.Sell(v, _Symbol, 0, 0, 0);
         if(ok) burstSize++;
         else lastError = IntegerToString((int)trade.ResultRetcode()) + " " + trade.ResultComment();
         continue;
      }
      if(side > 0)
      {
         price = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
         sl = NormalizeDouble(price - SafetySL_ATR * atr, digits);
         tp = NormalizeDouble(price + tpATR[i] * TPScale * atr, digits);
         ok = trade.Buy(Lot(lots[i]), _Symbol, 0, sl, tp);
      }
      else
      {
         price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
         sl = NormalizeDouble(price + SafetySL_ATR * atr, digits);
         tp = NormalizeDouble(price - tpATR[i] * TPScale * atr, digits);
         ok = trade.Sell(Lot(lots[i]), _Symbol, 0, sl, tp);
      }
      if(ok) burstSize++;
      else lastError = IntegerToString((int)trade.ResultRetcode()) + " " + trade.ResultComment();
   }
   if(burstSize > 0)
   {
      phase = 1;
      string dir = "VENTE";
      if(side > 0) dir = "ACHAT";
      lastEvent = dir + " : rafale de " + IntegerToString(burstSize) + " ouverte a " + TimeToString(openTime, TIME_SECONDS);
      Print(lastEvent);
   }
   else { phase = 0; readCount = 0; readSum = 0; }
}

//--- apres le 1er TP (le plus gros lot) : le reste suit
void FollowRest()
{
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double spread = SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double minDist = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      double open = PositionGetDouble(POSITION_PRICE_OPEN);
      double cur  = PositionGetDouble(POSITION_PRICE_CURRENT);
      double sl   = PositionGetDouble(POSITION_SL);
      double tp   = PositionGetDouble(POSITION_TP);
      double newSl = sl;
      if(PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY)
      {
         double target = open + spread;                   // stop au prix d'entree
         double tr = cur - TrailATR * atr;                // stop suiveur
         if(tr > target) target = tr;
         if(target > newSl && cur - target > minDist) newSl = target;
      }
      else
      {
         double target = open - spread;
         double tr = cur + TrailATR * atr;
         if(tr < target) target = tr;
         if((newSl == 0 || target < newSl) && target - cur > minDist) newSl = target;
      }
      newSl = NormalizeDouble(newSl, digits);
      if(MathAbs(newSl - sl) >= 5 * _Point) trade.PositionModify(ticket, newSl, tp);
   }
}

//--- mouvement du prix en faveur de la rafale, spread exclu (achat : ask vs ask, vente : bid vs bid)
double BasketMove()
{
   double sum = 0, vol = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      double v = PositionGetDouble(POSITION_VOLUME);
      sum += PositionGetDouble(POSITION_PRICE_OPEN) * v;
      vol += v;
   }
   if(vol <= 0) return 0;
   double avgOpen = sum / vol;
   if(burstSide > 0) return SymbolInfoDouble(_Symbol, SYMBOL_ASK) - avgOpen;
   return avgOpen - SymbolInfoDouble(_Symbol, SYMBOL_BID);
}

//--- gestion de la rafale ouverte
void Manage()
{
   if(phase != 1) return;
   double profit;
   int n = CountPositions(profit);
   if(n == 0) { EndBurst("toutes les positions fermees (TP / stop)"); return; }

   double pct = 100.0 * (AccountInfoDouble(ACCOUNT_EQUITY) - startBalance) / startBalance;
   long age = (long)(TimeTradeServer() - openTime);

   if(LiveTikTok)
   {
      // comme le live : on attend, sans coupure, et on ferme tout en gain
      if(pct >= TikTokTargetPct) { EndBurst("objectif du live atteint"); return; }
      if(TikTokStopPct > 0 && pct <= -TikTokStopPct) { EndBurst("arret d'urgence"); return; }
      return;
   }
   double move = BasketMove();                         // > 0 : le prix va dans le bon sens

   if(atr > 0 && move <= -LossATR * atr) { EndBurst("limite de perte (prix contre la rafale)"); return; }
   if(pct <= -HardLossPct) { EndBurst("securite : perte du compte"); return; }
   if(n == burstSize && age >= CutSeconds && move <= 0) { EndBurst("pas partie dans le bon sens apres " + IntegerToString(CutSeconds) + " s"); return; }
   if(age >= MaxSeconds) { EndBurst("duree max"); return; }
   if(n < burstSize) FollowRest();                 // le gros lot est sorti en profit : le reste suit
}

//+------------------------------------------------------------------+
int OnInit()
{
   trade.SetExpertMagicNumber((ulong)MagicNumber);
   trade.SetDeviationInPoints(50);
   long filling = SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   if((filling & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK) trade.SetTypeFilling(ORDER_FILLING_FOK);
   else if((filling & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC) trade.SetTypeFilling(ORDER_FILLING_IOC);
   else trade.SetTypeFilling(ORDER_FILLING_RETURN);

   hRSI   = iRSI(_Symbol, PERIOD_M1, 14, PRICE_CLOSE);
   hMACD  = iMACD(_Symbol, PERIOD_M1, 12, 26, 9, PRICE_CLOSE);
   hEMA20 = iMA(_Symbol, PERIOD_M1, 20, 0, MODE_EMA, PRICE_CLOSE);
   hEMAH1 = iMA(_Symbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE);
   hBB    = iBands(_Symbol, PERIOD_M1, 20, 0, 2.0, PRICE_CLOSE);
   hATR   = iATR(_Symbol, PERIOD_M1, 14);

   // reprise apres un redemarrage avec des positions deja ouvertes
   double p;
   if(CountPositions(p) > 0)
   {
      phase = 1; burstSize = 6;
      startBalance = AccountInfoDouble(ACCOUNT_BALANCE);
      openTime = TimeTradeServer();
   }

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
   if(!ComputeScore()) { Comment("LIVE 12 : indicateurs pas encore prets"); return; }

   bool allowedOk = (TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) != 0 && MQLInfoInteger(MQL_TRADE_ALLOWED) != 0);

   // phase d'analyse : lire la jauge pendant ReadSeconds, puis ouvrir du cote dominant
   if(phase == 0)
   {
      readCount++;
      readSum += score;
      if(readCount >= ReadSeconds)
      {
         int side = 0;
         if(readSum > 0) side = 1;
         if(readSum < 0) side = -1;
         if(side != 0 && allowedOk) OpenBurst(side);
         else { readCount = 0; readSum = 0; }
      }
   }

   double profit;
   int n = CountPositions(profit);
   double buyPct = 50.0 + 5.0 * score;
   string allowed = "OUI";
   if(TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) == 0) allowed = "NON : bouton Trading Algo";
   else if(MQLInfoInteger(MQL_TRADE_ALLOWED) == 0) allowed = "NON : cocher 'Autoriser le trading algorithmique'";
   string ph = "ANALYSE " + IntegerToString(readCount) + "/" + IntegerToString(ReadSeconds) + " s";
   if(phase == 1)
      ph = "RAFALE : " + IntegerToString(n) + "/" + IntegerToString(burstSize) + " positions, " +
           DoubleToString(profit, 2) + ", depuis " + IntegerToString((int)(TimeTradeServer() - openTime)) + " s";

   double marginLevel = AccountInfoDouble(ACCOUNT_MARGIN_LEVEL);
   Comment("LIVE 12  -  ", _Symbol, (LiveTikTok ? "   [MODE LIVE TIKTOK : sans stop]" : ""),
           "\nNiveau de marge : ", (marginLevel > 0 ? DoubleToString(marginLevel, 0) + " %" : "-"),
           "\nTrading autorise : ", allowed, "   derniere erreur : ", lastError,
           "\nPhase : ", ph,
           "\nACHAT ", DoubleToString(buyPct, 0), " %   VENTE ", DoubleToString(100 - buyPct, 0), " %   (score ", score, ")",
           "\nRafales : ", bursts, "   gagnantes : ", winBursts, "   total : ", DoubleToString(totalResult, 2),
           "\nDernier evenement : ", lastEvent,
           "\nSolde : ", DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2),
           "   Equite : ", DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2));
}
//+------------------------------------------------------------------+
