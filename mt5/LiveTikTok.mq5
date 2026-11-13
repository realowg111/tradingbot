//+------------------------------------------------------------------+
//| LiveTikTok.mq5                                                   |
//| Reproduction du robot du live TikTok "HFT ROBOT", d'apres une    |
//| lecture image par image de la video (4 rafales en 42 s) :        |
//|  1. pause d'environ 5 s sans position                            |
//|  2. sens a contre-courant : achat apres une baisse, vente apres  |
//|     une hausse (sens alterne dans la video)                      |
//|  3. rafale de 7 positions ouverte en moins d'une seconde, tailles |
//|     0.30/0.20/0.15/0.10/0.05/0.05/0.05 (proportions du live),    |
//|     total calcule pour utiliser une part de la marge disponible  |
//|  4. aucun stop, aucun TP : on attend que la rafale soit en gain   |
//|  5. des que le gain atteint +x % : fermeture progressive, la plus |
//|     grosse position gagnante d'abord, une toutes les 0.7 s       |
//|  6. retour a la pause, en boucle                                 |
//| DEMO UNIQUEMENT : sans stop et avec ce levier, une rafale qui ne |
//| revient pas fait perdre la plus grande partie du compte.         |
//+------------------------------------------------------------------+
#property version "1.00"
#include <Trade\Trade.mqh>

input int    PauseSeconds   = 5;     // Pause sans position entre deux rafales
input int    LookbackSeconds = 20;   // Mouvement regarde pour choisir le sens (contre-courant)
input double MarginUse      = 0.70;  // Part du solde utilisee en marge par la rafale (0.70 = niveau de marge ~140 %)
input double StartClosePct  = 3.0;   // Debut des fermetures quand la rafale gagne x % du solde
input int    CloseEveryMs   = 700;   // Une fermeture toutes les N millisecondes
input double EmergencyPct   = 0.0;   // Arret d'urgence a -x % du solde (0 = aucun, comme le live)
input long   MagicNumber    = 7777;

CTrade trade;

// proportions des lots de la 4e rafale du live (0.30 / 0.20 / 0.15 / 0.10 / 0.05 / 0.05 / 0.05)
double weights[7] = {0.30, 0.20, 0.15, 0.10, 0.05, 0.05, 0.05};

// prix des dernieres secondes (pour le contre-courant)
double   pxBuf[600];
ulong    pxTime[600];
int      pxHead = 0, pxCount = 0;

int      phase = 0;                // 0 = pause, 1 = rafale ouverte, 2 = fermeture progressive
ulong    phaseStart = 0;
ulong    lastClose = 0;
int      lastSide = 0;
double   startBalance = 0;
int      bursts = 0;
double   worst = 0;
string   lastEvent = "demarrage";
string   lastError = "aucune";

//+------------------------------------------------------------------+
void RecordPrice()
{
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(bid <= 0) return;
   pxBuf[pxHead] = bid;
   pxTime[pxHead] = GetTickCount64();
   pxHead = (pxHead + 1) % 600;
   if(pxCount < 600) pxCount++;
}

//--- variation du prix sur les N dernieres secondes
double PriceMove(int seconds)
{
   if(pxCount < 2) return 0;
   int last = (pxHead + 599) % 600;
   ulong limit = pxTime[last] - (ulong)seconds * 1000;
   double ref = pxBuf[last];
   for(int k = 1; k < pxCount; k++)
   {
      int i = (last - k + 600) % 600;
      if(pxTime[i] < limit) break;
      ref = pxBuf[i];
   }
   return pxBuf[last] - ref;
}

int CountPositions(double &profit)
{
   int n = 0;
   profit = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      n++;
      profit += PositionGetDouble(POSITION_PROFIT);
   }
   return n;
}

int PendingOrders()
{
   int k = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t == 0) continue;
      if(OrderGetString(ORDER_SYMBOL) != _Symbol) continue;
      if(OrderGetInteger(ORDER_MAGIC) != MagicNumber) continue;
      k++;
   }
   return k;
}

//--- ouvre la rafale : total des lots fixe par la marge disponible
void OpenBurst(int side)
{
   double price = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double marginPerLot = 0;
   if(!OrderCalcMargin(ORDER_TYPE_BUY, _Symbol, 1.0, price, marginPerLot) || marginPerLot <= 0)
   { lastError = "marge par lot inconnue"; return; }
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double totalLots = MarginUse * balance / marginPerLot;
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);

   startBalance = balance;
   worst = 0;
   int opened = 0;
   for(int i = 0; i < 7; i++)
   {
      double v = MathFloor(totalLots * weights[i] / step) * step;
      if(v < minLot) v = minLot;
      if(v > maxLot) v = maxLot;
      v = NormalizeDouble(v, 2);
      bool ok;
      if(side > 0) ok = trade.Buy(v, _Symbol, 0, 0, 0, "LiveTikTok");
      else ok = trade.Sell(v, _Symbol, 0, 0, 0, "LiveTikTok");
      if(ok) opened++;
      else lastError = IntegerToString((int)trade.ResultRetcode()) + " " + trade.ResultComment();
   }
   if(opened > 0)
   {
      bursts++;
      lastSide = side;
      phase = 1;
      phaseStart = GetTickCount64();
      string s = "VENTE";
      if(side > 0) s = "ACHAT";
      lastEvent = s + " : rafale " + IntegerToString(bursts) + " de " + IntegerToString(opened) + " positions, " +
                  DoubleToString(totalLots, 2) + " lot au total";
      Print(lastEvent);
   }
}

//--- ferme la plus grosse position gagnante ; renvoie false s'il n'y en a pas
bool CloseBiggestWinner()
{
   ulong best = 0;
   double bestVol = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      if(PositionGetDouble(POSITION_PROFIT) <= 0) continue;
      double v = PositionGetDouble(POSITION_VOLUME);
      if(v > bestVol) { bestVol = v; best = t; }
   }
   if(best == 0) return false;
   if(PositionSelectByTicket(best))
   {
      double p = PositionGetDouble(POSITION_PROFIT);
      if(trade.PositionClose(best))
         Print("Fermeture ", DoubleToString(bestVol, 2), " lot : ", DoubleToString(p, 2));
   }
   return true;
}

void CloseAll()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      trade.PositionClose(t);
   }
}

//+------------------------------------------------------------------+
void Step()
{
   RecordPrice();
   ulong now = GetTickCount64();
   double profit;
   int n = CountPositions(profit);
   bool allowed = (TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) != 0 && MQLInfoInteger(MQL_TRADE_ALLOWED) != 0);

   if(phase == 0)                                    // pause, puis rafale a contre-courant
   {
      if(n > 0) { phase = 1; phaseStart = now; startBalance = AccountInfoDouble(ACCOUNT_BALANCE); return; }
      if(now - phaseStart < (ulong)PauseSeconds * 1000 || !allowed) return;
      double move = PriceMove(LookbackSeconds);
      int side = 0;
      if(move < 0) side = 1;                          // le prix a baisse : achat
      if(move > 0) side = -1;                         // le prix a monte : vente
      if(side == 0) side = -lastSide;                 // pas de mouvement : on alterne
      if(side == 0) side = 1;
      OpenBurst(side);
      return;
   }

   if(PendingOrders() > 0 || now - phaseStart < 1500) return;   // ordres pas encore tous executes

   if(n == 0)                                         // tout est ferme : pause
   {
      double result = AccountInfoDouble(ACCOUNT_BALANCE) - startBalance;
      lastEvent = "rafale " + IntegerToString(bursts) + " terminee : " + DoubleToString(result, 2) +
                  " (pire moment " + DoubleToString(worst, 2) + ")";
      Print(lastEvent);
      phase = 0; phaseStart = now;
      return;
   }

   double pct = 100.0 * profit / startBalance;
   if(profit < worst) worst = profit;

   if(EmergencyPct > 0 && pct <= -EmergencyPct)
   {
      CloseAll();
      lastEvent = "arret d'urgence a " + DoubleToString(pct, 1) + " %";
      Print(lastEvent);
      return;
   }

   if(phase == 1 && pct >= StartClosePct) { phase = 2; lastClose = 0; }

   if(phase == 2 && now - lastClose >= (ulong)CloseEveryMs)
   {
      if(CloseBiggestWinner()) lastClose = now;
   }
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
   phaseStart = GetTickCount64();
   EventSetMillisecondTimer(250);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   Comment("");
}

void OnTick() { Step(); }

void OnTimer()
{
   Step();
   double profit;
   int n = CountPositions(profit);
   string ph = "PAUSE " + IntegerToString((int)((GetTickCount64() - phaseStart) / 1000)) + "/" + IntegerToString(PauseSeconds) + " s";
   if(phase == 1) ph = "RAFALE OUVERTE : on attend +" + DoubleToString(StartClosePct, 1) + " %";
   if(phase == 2) ph = "FERMETURE PROGRESSIVE (plus grosse position gagnante d'abord)";
   double ml = AccountInfoDouble(ACCOUNT_MARGIN_LEVEL);
   Comment("LIVE TIKTOK  -  ", _Symbol, "   (DEMO UNIQUEMENT : aucun stop)",
           "\nPhase : ", ph,
           "\nPositions : ", n, "   resultat en cours : ", DoubleToString(profit, 2),
           "   (", (startBalance > 0 ? DoubleToString(100.0 * profit / startBalance, 2) : "0"), " %)",
           "\nMouvement du prix sur ", LookbackSeconds, " s : ", DoubleToString(PriceMove(LookbackSeconds), 2),
           "\nNiveau de marge : ", (ml > 0 ? DoubleToString(ml, 0) + " %" : "-"),
           "\nRafales : ", bursts, "   dernier evenement : ", lastEvent,
           "\nDerniere erreur : ", lastError,
           "\nSolde : ", DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2),
           "   Equite : ", DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2));
}
//+------------------------------------------------------------------+
