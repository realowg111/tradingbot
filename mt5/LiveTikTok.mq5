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
//| Protections (le style reste le meme) :                           |
//|  - contre-courant seulement dans le sens de la tendance de fond  |
//|  - reduction de la rafale si elle perd : plus grosse position    |
//|    fermee a -2 %, puis -3.5 %, tout a -5 %                        |
//|  - fermeture apres 15 min sans gain                              |
//|  - rafales plus petites (20 % de la marge au lieu de 70 %)       |
//| Pour la version exacte du live : MarginUse 0.70, TrendFilter     |
//| false, ReduceStep1Pct/ReduceStep2Pct/CloseAllPct 0,              |
//| MaxBurstMinutes 0.                                               |
//+------------------------------------------------------------------+
#property version "1.10"
#include <Trade\Trade.mqh>

input int    PauseSeconds   = 5;     // Pause sans position entre deux rafales
input int    LookbackSeconds = 20;   // Mouvement regarde pour choisir le sens (contre-courant)
input double MarginUse      = 0.20;  // Part du solde utilisee en marge par la rafale (live : 0.70 ; protege : 0.20)
input double StartClosePct  = 3.0;   // Debut des fermetures quand la rafale gagne x % du solde
input int    CloseEveryMs   = 700;   // Une fermeture toutes les N millisecondes
input double EmergencyPct   = 0.0;   // Arret d'urgence a -x % du solde (0 = aucun, comme le live)

input bool   TrendFilter    = true;  // Protection 1 : contre-courant seulement dans le sens de la tendance de fond (EMA 50 H1)
input double ReduceStep1Pct = 2.0;   // Protection 2 : a -x % ferme la plus grosse position (0 = off)
input double ReduceStep2Pct = 3.5;   // ... a -x % ferme la plus grosse restante
input double CloseAllPct    = 5.0;   // ... a -x % ferme tout ce qui reste
input int    MaxBurstMinutes = 15;   // Protection 3 : ferme la rafale si elle n'est pas en gain apres N minutes (0 = off)
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
int      reduceStage = 0;          // paliers de reduction deja appliques a la rafale
int      hTrend = INVALID_HANDLE;
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
   reduceStage = 0;
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

//--- ferme la plus grosse position, gagnante ou non (reduction de la rafale)
void CloseBiggest(string why)
{
   ulong best = 0;
   double bestVol = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      double v = PositionGetDouble(POSITION_VOLUME);
      if(v > bestVol) { bestVol = v; best = t; }
   }
   if(best == 0) return;
   double p = 0;
   if(PositionSelectByTicket(best)) p = PositionGetDouble(POSITION_PROFIT);
   if(trade.PositionClose(best))
   {
      lastEvent = why + " : " + DoubleToString(bestVol, 2) + " lot ferme a " + DoubleToString(p, 2);
      Print(lastEvent);
   }
}

//--- sens de la tendance de fond : 1 haussiere, -1 baissiere, 0 inconnue
int TrendSide()
{
   double v[];
   if(hTrend == INVALID_HANDLE || CopyBuffer(hTrend, 0, 0, 1, v) < 1) return 0;
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(bid > v[0]) return 1;
   if(bid < v[0]) return -1;
   return 0;
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
      if(TrendFilter)
      {
         int tr = TrendSide();
         if(tr != 0 && side != tr) { lastEvent = "attend : contre-courant oppose a la tendance de fond"; return; }
      }
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

   // protection 2 : reduction de la rafale, la plus grosse position d'abord
   if(phase == 1)
   {
      if(CloseAllPct > 0 && pct <= -CloseAllPct)
      {
         CloseAll();
         lastEvent = "limite de la rafale " + DoubleToString(pct, 1) + " % : tout ferme";
         Print(lastEvent);
         return;
      }
      if(reduceStage == 0 && ReduceStep1Pct > 0 && pct <= -ReduceStep1Pct) { reduceStage = 1; CloseBiggest("reduction 1"); return; }
      if(reduceStage == 1 && ReduceStep2Pct > 0 && pct <= -ReduceStep2Pct) { reduceStage = 2; CloseBiggest("reduction 2"); return; }
      // protection 3 : duree maximale sans gain
      if(MaxBurstMinutes > 0 && now - phaseStart >= (ulong)MaxBurstMinutes * 60000 && profit <= 0)
      {
         CloseAll();
         lastEvent = "rafale fermee apres " + IntegerToString(MaxBurstMinutes) + " min sans gain";
         Print(lastEvent);
         return;
      }
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
   hTrend = iMA(_Symbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE);
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
   Comment("LIVE TIKTOK  -  ", _Symbol, "   (version protegee)",
           "\nPhase : ", ph,
           "\nPositions : ", n, "   resultat en cours : ", DoubleToString(profit, 2),
           "   (", (startBalance > 0 ? DoubleToString(100.0 * profit / startBalance, 2) : "0"), " %)",
           "\nMouvement du prix sur ", LookbackSeconds, " s : ", DoubleToString(PriceMove(LookbackSeconds), 2),
           "   tendance de fond : ", (TrendSide() > 0 ? "HAUSSIERE (achats sur les creux)" : (TrendSide() < 0 ? "BAISSIERE (ventes sur les rebonds)" : "-")),
           "\nProtections : reduction a -", DoubleToString(ReduceStep1Pct, 1), " % / -", DoubleToString(ReduceStep2Pct, 1),
           " %, tout ferme a -", DoubleToString(CloseAllPct, 1), " %, duree max ", MaxBurstMinutes, " min",
           "\nNiveau de marge : ", (ml > 0 ? DoubleToString(ml, 0) + " %" : "-"),
           "\nRafales : ", bursts, "   dernier evenement : ", lastEvent,
           "\nDerniere erreur : ", lastError,
           "\nSolde : ", DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2),
           "   Equite : ", DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2));
}
//+------------------------------------------------------------------+
