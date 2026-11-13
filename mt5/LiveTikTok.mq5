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
//| Ajout a la strategie du live : reduction de la rafale si elle    |
//| perd, la plus grosse position d'abord : -2 %, -3.5 %, puis tout  |
//| a -5 % du solde. Le reste est identique au live.                 |
//| Sens : jauge des 12 indicateurs lue pendant la pause (ACHAT % /  |
//| VENTE %, sentiment), ou jauge + contre-courant, ou contre-courant|
//| Series de pertes : pause de 15 s apres 3 rafales perdantes,      |
//| arret jusqu'au lendemain a -8 % sur le jour.                     |
//| Options desactivees par defaut : TrendFilter, MaxBurstMinutes.   |
//+------------------------------------------------------------------+
#property version "1.80"
#include <Trade\Trade.mqh>

input int    PauseSeconds   = 5;     // Pause sans position entre deux rafales
input int    LookbackSeconds = 20;   // Mouvement regarde pour choisir le sens (contre-courant)
input double MarginUse      = 0.85;  // Part du solde utilisee en marge par la rafale (live 0.70 ; ici 0.85 = lots plus gros)
input double StartClosePct  = 3.0;   // Debut des fermetures quand la rafale gagne x % du solde
input int    CloseEveryMs   = 700;   // Une fermeture toutes les N millisecondes
input double EmergencyPct   = 0.0;   // Arret d'urgence a -x % du solde (0 = aucun, comme le live)

input bool   TrendFilter    = false; // Option : contre-courant seulement dans le sens de la tendance de fond (EMA 50 H1)
input double ReduceStep1Pct = 0.5;   // Reduction : a -x % (spread d'ouverture non compte) ferme la plus grosse position (0 = off)
input double ReduceStep2Pct = 1.0;   // ... a -x % ferme la plus grosse restante
input double CloseAllPct    = 1.5;   // ... a -x % ferme tout ce qui reste
input int    MaxBurstMinutes = 0;    // Option : ferme la rafale si elle n'est pas en gain apres N minutes (0 = off)

input double BankPct        = 1.0;   // Securisation : a +x % ferme la plus grosse position (gain en poche) (0 = off)
input double LockPct        = 1.0;   // Verrou : des +x %, la rafale ne doit plus finir en perte (0 = off)
input double FloorPct       = 0.2;   // Verrou : ferme tout si la rafale redescend a +x %
input double BEBuffer       = 0.10;  // Verrou : stop chez le courtier au prix d'entree + x (prix de l'or, ex 0.10 $)
input double TrailStartPct  = 1.5;   // Gain suiveur : actif des +x % (0 = off)
input double TrailGiveback  = 40;    // Gain suiveur : ferme tout si on perd x % du meilleur gain
input string NewsTimesParis = "14:30,16:00,20:00"; // Annonces (heure de Paris) : pas de nouvelle rafale autour
input int    NewsWindowMin  = 5;     // Annonces : minutes avant et apres (0 = off)
input int    LossStreak     = 3;     // Apres N rafales perdantes d'affilee...
input int    StreakPauseSec = 15;    // ...pause de N secondes (0 = off)

input int    DirectionMode  = 0;     // Sens : 0 = jauge des 12 indicateurs, 1 = jauge ET contre-courant d'accord, 2 = contre-courant seul
input double MinConfidence  = 60;    // Jauge : confiance minimale (%) pour une direction claire
input int    StableSeconds  = 3;     // Jauge : le sentiment doit etre le meme depuis au moins N secondes
input bool   ShowGaugePanel = true;  // Afficher le tableau de jauge sur le graphique
input double DailyLossPct   = 8.0;   // Arret jusqu'au lendemain si le compte perd x % dans la journee (0 = off)
input long   MagicNumber    = 7777;

CTrade trade;

// declarations anticipees
int ClearDirection();
int FlipsLastMinute();

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
double   spreadCost = 0;           // cout du spread a l'ouverture de la rafale (en devise du compte)
bool     banked = false;           // plus grosse position deja encaissee
bool     locked = false;           // verrou de gain actif
double   peakPct = 0;              // meilleur resultat de la rafale (% du solde)
int      hTrend = INVALID_HANDLE;
int      hRSI = INVALID_HANDLE, hMACD = INVALID_HANDLE, hEMA20 = INVALID_HANDLE, hEMAH1 = INVALID_HANDLE, hBB = INVALID_HANDLE;
int      score = 0;                // score des 12 indicateurs (-10 .. +10)
double   gaugeSum = 0;             // lecture de la jauge pendant la pause
int      gaugeN = 0;
int      flips = 0;                // basculements haussier / baissier pendant la pause
int      lastSentiment = 0;
// suivi de la jauge seconde par seconde
ulong    lastGaugeTick = 0;
int      liveSent = 0;               // sentiment de la derniere seconde : 1 haussier, -1 baissier, 0 neutre
datetime liveSentSince = 0;          // debut du sentiment actuel
string   timeline = "";              // 30 dernieres secondes : + haussier, - baissier, . neutre
datetime flipTimes[60];              // heures des dernieres bascules
int      flipHead = 0, flipCount = 0;
string   flipLog[3];                 // 3 dernieres bascules
double   worst = 0;
string   lastEvent = "demarrage";
string   lastError = "aucune";
int      losingStreak = 0;         // rafales perdantes d'affilee
datetime pauseUntil = 0;           // pause apres une serie de pertes (heure serveur)
int      dayKey = -1;
double   dayStartBalance = 0;
bool     dayStopped = false;

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

//--- les 12 indicateurs sur le prix en direct -> score de -10 a +10
string indNames[10] = {"RSI 14", "Tendance H1", "Moyenne 20", "MACD", "Structure", "Bollinger", "Momentum 5", "Momentum 15", "Derniere bougie", "Cassure"};
int    indVotes[10];

bool ComputeScore()
{
   MqlRates r[];
   ArraySetAsSeries(r, true);
   if(CopyRates(_Symbol, PERIOD_M1, 0, 25, r) < 25) return false;
   double price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double rsi = Val(hRSI, 0), macd = Val(hMACD, 0), sig = Val(hMACD, 1);
   double e20 = Val(hEMA20, 0), eh1 = Val(hEMAH1, 0), mid = Val(hBB, 0);
   if(rsi == 0 || e20 == 0 || eh1 == 0 || mid == 0) return false;
   double hi = r[1].high, lo = r[1].low;
   for(int i = 1; i <= 20; i++)
   {
      if(r[i].high > hi) hi = r[i].high;
      if(r[i].low < lo) lo = r[i].low;
   }
   indVotes[0] = 0;
   if(rsi > 55) indVotes[0] = 1;
   if(rsi < 45) indVotes[0] = -1;
   indVotes[1] = Vote(price, eh1);              // tendance H1
   indVotes[2] = Vote(price, e20);              // moyenne 20
   indVotes[3] = Vote(macd, sig);               // MACD
   indVotes[4] = Vote(price, (hi + lo) / 2);    // structure
   indVotes[5] = Vote(price, mid);              // Bollinger
   indVotes[6] = Vote(price, r[5].close);       // momentum 5
   indVotes[7] = Vote(price, r[15].close);      // momentum 15
   indVotes[8] = Vote(price, r[1].close);       // derniere bougie
   indVotes[9] = 0;                             // cassure
   if(price > hi) indVotes[9] = 1;
   if(price < lo) indVotes[9] = -1;
   score = 0;
   for(int k = 0; k < 10; k++) score += indVotes[k];
   return true;
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
   spreadCost = 0;
   banked = false; locked = false; peakPct = 0;
   double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double spreadNow = SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID);
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
      if(ok)
      {
         opened++;
         if(tickSize > 0) spreadCost += spreadNow / tickSize * tickValue * v;
      }
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

//--- heure de Paris (heure d'ete europeenne : dernier dimanche de mars -> dernier dimanche d'octobre, 01:00 UTC)
datetime LastSunday(int year, int month)
{
   int ny = year, nm = month + 1;
   if(month == 12) { ny = year + 1; nm = 1; }
   datetime t = StringToTime(StringFormat("%04d.%02d.01 01:00", ny, nm)) - 86400;   // dernier jour du mois, 01:00
   MqlDateTime d;
   TimeToStruct(t, d);
   return t - d.day_of_week * 86400;
}

datetime ParisNow()
{
   datetime gmt = TimeGMT();
   MqlDateTime d; TimeToStruct(gmt, d);
   bool summer = (gmt >= LastSunday(d.year, 3) && gmt < LastSunday(d.year, 10));
   return gmt + (summer ? 7200 : 3600);
}

//--- vrai si on est a moins de NewsWindowMin minutes d'une annonce
bool InNewsWindow()
{
   if(NewsWindowMin <= 0 || StringLen(NewsTimesParis) == 0) return false;
   MqlDateTime p; TimeToStruct(ParisNow(), p);
   int nowMin = p.hour * 60 + p.min;
   string parts[];
   int n = StringSplit(NewsTimesParis, ',', parts);
   for(int i = 0; i < n; i++)
   {
      StringTrimLeft(parts[i]); StringTrimRight(parts[i]);
      string hm[];
      if(StringSplit(parts[i], ':', hm) != 2) continue;
      int t = (int)StringToInteger(hm[0]) * 60 + (int)StringToInteger(hm[1]);
      if(MathAbs(nowMin - t) <= NewsWindowMin) return true;
   }
   return false;
}

//--- verrou : stop chez le courtier au prix d'entree + BEBuffer sur chaque position
void PlaceBreakEvenStops()
{
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double minDist = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID), ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      double open = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl = 0;
      if(PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY)
      {
         sl = NormalizeDouble(open + BEBuffer, digits);
         if(bid - sl <= minDist) continue;             // le prix n'est pas assez loin : verrou gere par le robot
      }
      else
      {
         sl = NormalizeDouble(open - BEBuffer, digits);
         if(sl - ask <= minDist) continue;
      }
      trade.PositionModify(t, sl, PositionGetDouble(POSITION_TP));
   }
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
      // limite par jour et pause apres une serie de pertes
      MqlDateTime dt; TimeToStruct(TimeTradeServer(), dt);
      if(dt.day_of_year != dayKey) { dayKey = dt.day_of_year; dayStartBalance = AccountInfoDouble(ACCOUNT_BALANCE); dayStopped = false; }
      if(DailyLossPct > 0 && !dayStopped && AccountInfoDouble(ACCOUNT_BALANCE) <= dayStartBalance * (1.0 - DailyLossPct / 100.0))
      {
         dayStopped = true;
         lastEvent = "limite du jour atteinte (-" + DoubleToString(DailyLossPct, 1) + " %) : arret jusqu'a demain";
         Print(lastEvent);
      }
      if(dayStopped) return;
      if(InNewsWindow()) { lastEvent = "annonce economique proche : pas de nouvelle rafale"; return; }
      if(TimeTradeServer() < pauseUntil) { gaugeSum = 0; gaugeN = 0; flips = 0; return; }

      // lecture de la jauge pendant la pause (toutes les 250 ms)
      if(ComputeScore())
      {
         gaugeSum += score; gaugeN++;
         int sent = (score > 0 ? 1 : (score < 0 ? -1 : 0));
         if(sent != 0 && lastSentiment != 0 && sent != lastSentiment) flips++;
         if(sent != 0) lastSentiment = sent;
      }
      if(now - phaseStart < (ulong)PauseSeconds * 1000 || !allowed) return;

      // cote de la jauge (moyenne pendant la pause)
      double avg = (gaugeN > 0 ? gaugeSum / gaugeN : 0);
      double buyPct = 50.0 + 5.0 * avg;
      int gaugeSide = ClearDirection();             // direction claire : sentiment stable + confiance
      // cote du contre-courant
      double move = PriceMove(LookbackSeconds);
      int counterSide = 0;
      if(move < 0) counterSide = 1;                    // le prix a baisse : achat
      if(move > 0) counterSide = -1;                   // le prix a monte : vente
      if(counterSide == 0) counterSide = -lastSide;    // pas de mouvement : on alterne

      int side = 0;
      if(DirectionMode == 0) side = gaugeSide;
      if(DirectionMode == 1 && gaugeSide == counterSide) side = gaugeSide;
      if(DirectionMode == 2) side = counterSide;
      if(side == 0)
      {
         lastEvent = "attend : jauge " + DoubleToString(buyPct, 0) + " % achat / " + DoubleToString(100.0 - buyPct, 0) +
                     " % vente, confiance insuffisante ou pas d'accord";
         phaseStart = now - (ulong)PauseSeconds * 1000 + 1000;      // nouvelle lecture d'1 s
         gaugeSum = 0; gaugeN = 0; flips = 0;
         return;
      }
      gaugeSum = 0; gaugeN = 0; flips = 0;
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
      // serie de pertes : pause
      if(result < 0) losingStreak++; else losingStreak = 0;
      if(StreakPauseSec > 0 && LossStreak > 0 && losingStreak >= LossStreak)
      {
         pauseUntil = TimeTradeServer() + StreakPauseSec;
         lastEvent = IntegerToString(losingStreak) + " rafales perdantes d'affilee : pause de " + IntegerToString(StreakPauseSec) + " s";
         Print(lastEvent);
         losingStreak = 0;
      }
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

   // securisation des gains (resultat total de la rafale, gains deja encaisses compris)
   double totalPct = 100.0 * (AccountInfoDouble(ACCOUNT_EQUITY) - startBalance) / startBalance;
   if(totalPct > peakPct) peakPct = totalPct;
   if(!banked && BankPct > 0 && totalPct >= BankPct)
   {
      banked = true;
      CloseBiggest("gain securise");
      return;
   }
   if(!locked && LockPct > 0 && peakPct >= LockPct)
   {
      locked = true;
      PlaceBreakEvenStops();
      lastEvent = "verrou actif : stops au prix d'entree chez le courtier";
      Print(lastEvent);
   }
   if(locked && totalPct <= FloorPct)
   {
      CloseAll();
      lastEvent = "verrou : rafale fermee a " + DoubleToString(totalPct, 2) + " % (max " + DoubleToString(peakPct, 2) + " %)";
      Print(lastEvent);
      return;
   }
   if(TrailStartPct > 0 && peakPct >= TrailStartPct && totalPct <= peakPct * (1.0 - TrailGiveback / 100.0))
   {
      CloseAll();
      lastEvent = "gain suiveur : rafale fermee a " + DoubleToString(totalPct, 2) + " % (max " + DoubleToString(peakPct, 2) + " %)";
      Print(lastEvent);
      return;
   }

   // protection 2 : reduction de la rafale, la plus grosse position d'abord
   // (le spread paye a l'ouverture n'est pas compte : seul le mouvement du prix declenche les paliers)
   double movePct = 100.0 * (profit + spreadCost) / startBalance;
   if(phase >= 1)
   {
      if(CloseAllPct > 0 && movePct <= -CloseAllPct)
      {
         CloseAll();
         lastEvent = "limite de la rafale " + DoubleToString(pct, 1) + " % : tout ferme";
         Print(lastEvent);
         return;
      }
      if(reduceStage == 0 && ReduceStep1Pct > 0 && movePct <= -ReduceStep1Pct) { reduceStage = 1; CloseBiggest("reduction 1"); return; }
      if(reduceStage == 1 && ReduceStep2Pct > 0 && movePct <= -ReduceStep2Pct) { reduceStage = 2; CloseBiggest("reduction 2"); return; }
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
   hRSI   = iRSI(_Symbol, PERIOD_M1, 14, PRICE_CLOSE);
   hMACD  = iMACD(_Symbol, PERIOD_M1, 12, 26, 9, PRICE_CLOSE);
   hEMA20 = iMA(_Symbol, PERIOD_M1, 20, 0, MODE_EMA, PRICE_CLOSE);
   hEMAH1 = iMA(_Symbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE);
   hBB    = iBands(_Symbol, PERIOD_M1, 20, 0, 2.0, PRICE_CLOSE);
   EventSetMillisecondTimer(250);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   Comment("");
   ObjectsDeleteAll(0, "G_");
}

void OnTick() { Step(); }

//--- direction claire : meme sentiment depuis StableSeconds et confiance >= MinConfidence
int ClearDirection()
{
   if(liveSent == 0) return 0;
   double conf = 50.0 + 5.0 * MathAbs((double)score);
   if((int)(TimeTradeServer() - liveSentSince) < StableSeconds) return 0;
   if(conf < MinConfidence) return 0;
   if(liveSent > 0 && score <= 0) return 0;
   if(liveSent < 0 && score >= 0) return 0;
   return liveSent;
}

//--- tableau de jauge sur le graphique
void Rect(string name, int x, int y, int w, int h, color bg)
{
   if(ObjectFind(0, name) < 0)
   {
      ObjectCreate(0, name, OBJ_RECTANGLE_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_BORDER_TYPE, BORDER_FLAT);
      ObjectSetInteger(0, name, OBJPROP_BACK, false);
   }
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, name, OBJPROP_XSIZE, w < 1 ? 1 : w);
   ObjectSetInteger(0, name, OBJPROP_YSIZE, h);
   ObjectSetInteger(0, name, OBJPROP_BGCOLOR, bg);
   ObjectSetInteger(0, name, OBJPROP_COLOR, bg);
}

void Text(string name, int x, int y, string txt, color c, int size)
{
   if(ObjectFind(0, name) < 0)
   {
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetString(0, name, OBJPROP_FONT, "Arial Bold");
   }
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, size);
   ObjectSetInteger(0, name, OBJPROP_COLOR, c);
   if(StringLen(txt) == 0) txt = " ";
   ObjectSetString(0, name, OBJPROP_TEXT, txt);
}

void DrawGaugePanel()
{
   if(!ShowGaugePanel) return;
   int x0 = 10, y0 = 330, w = 330;
   color navy = C'14,21,70', green = C'51,245,160', red = C'255,77,109', grey = C'143,155,214';
   double buyPct = 50.0 + 5.0 * score;
   Rect("G_bg", x0, y0, w, 440, navy);
   Text("G_t", x0 + 10, y0 + 8, "SENTIMENT & CONFIANCE  (chaque seconde)", grey, 9);
   string sent = "NEUTRE"; color sc = grey;
   if(liveSent > 0) { sent = "HAUSSIER"; sc = green; }
   if(liveSent < 0) { sent = "BAISSIER"; sc = red; }
   Text("G_s", x0 + 10, y0 + 28, sent, sc, 22);
   Text("G_c", x0 + 190, y0 + 38, "confiance " + DoubleToString(MathMax(buyPct, 100.0 - buyPct), 0) + " %", clrWhite, 10);
   Text("G_d", x0 + 10, y0 + 66, "depuis " + IntegerToString((int)(TimeTradeServer() - liveSentSince)) + " s   |   bascules sur 1 min : " +
        IntegerToString(FlipsLastMinute()), grey, 9);
   // barres ACHAT / VENTE
   int bw = w - 20;
   Text("G_ba", x0 + 10, y0 + 88, "ACHAT " + DoubleToString(buyPct, 0) + " %", green, 11);
   Rect("G_bab", x0 + 10, y0 + 108, bw, 12, C'40,50,110');
   Rect("G_baf", x0 + 10, y0 + 108, (int)(bw * buyPct / 100.0), 12, green);
   Text("G_bv", x0 + 10, y0 + 126, "VENTE " + DoubleToString(100.0 - buyPct, 0) + " %", red, 11);
   Rect("G_bvb", x0 + 10, y0 + 146, bw, 12, C'40,50,110');
   Rect("G_bvf", x0 + 10, y0 + 146, (int)(bw * (100.0 - buyPct) / 100.0), 12, red);
   // frise des 30 dernieres secondes
   Text("G_tl", x0 + 10, y0 + 166, "30 dernieres secondes", grey, 8);
   int n = StringLen(timeline);
   for(int i = 0; i < 30; i++)
   {
      color cc = C'40,50,110';
      int k = n - 30 + i;
      if(k >= 0)
      {
         ushort ch = StringGetCharacter(timeline, k);
         if(ch == '+') cc = green;
         else if(ch == '-') cc = red;
         else cc = grey;
      }
      Rect("G_tq" + IntegerToString(i), x0 + 10 + i * 10, y0 + 182, 8, 12, cc);
   }
   // direction
   int dir = ClearDirection();
   string ds = "PAS DE DIRECTION CLAIRE"; color dc = grey;
   if(dir > 0) { ds = "DIRECTION : ACHAT CLAIR"; dc = green; }
   if(dir < 0) { ds = "DIRECTION : VENTE CLAIRE"; dc = red; }
   Text("G_dir", x0 + 10, y0 + 202, ds, dc, 12);
   Text("G_dr", x0 + 10, y0 + 222, "(meme sentiment depuis " + IntegerToString(StableSeconds) + " s et confiance >= " +
        DoubleToString(MinConfidence, 0) + " %)", grey, 8);
   // les 10 indicateurs
   for(int j = 0; j < 10; j++)
   {
      string arrow = "•"; color ac = grey;
      if(indVotes[j] > 0) { arrow = "▲ haussier"; ac = green; }
      if(indVotes[j] < 0) { arrow = "▼ baissier"; ac = red; }
      Text("G_in" + IntegerToString(j), x0 + 10, y0 + 244 + j * 18, indNames[j], clrWhite, 9);
      Text("G_iv" + IntegerToString(j), x0 + 170, y0 + 244 + j * 18, arrow, ac, 9);
   }
   ChartRedraw();
}

//--- toutes les secondes : sentiment et pourcentages, bascules
void GaugeEverySecond()
{
   if(GetTickCount64() - lastGaugeTick < 1000) return;
   lastGaugeTick = GetTickCount64();
   if(!ComputeScore()) return;
   int sent = (score > 0 ? 1 : (score < 0 ? -1 : 0));
   timeline += (sent > 0 ? "+" : (sent < 0 ? "-" : "."));
   if(StringLen(timeline) > 30) timeline = StringSubstr(timeline, StringLen(timeline) - 30);
   datetime now = TimeTradeServer();
   if(sent != liveSent)
   {
      if(sent != 0 && liveSent != 0)                     // vraie bascule haussier <-> baissier
      {
         flipTimes[flipHead] = now; flipHead = (flipHead + 1) % 60;
         if(flipCount < 60) flipCount++;
         string line = TimeToString(now, TIME_SECONDS) + "  " + (liveSent > 0 ? "HAUSSIER" : "BAISSIER") + " -> " +
                       (sent > 0 ? "HAUSSIER" : "BAISSIER") + "  (ACHAT " + DoubleToString(50.0 + 5.0 * score, 0) +
                       " % / VENTE " + DoubleToString(50.0 - 5.0 * score, 0) + " %)";
         flipLog[2] = flipLog[1]; flipLog[1] = flipLog[0]; flipLog[0] = line;
         Print("Bascule ", line);
      }
      liveSent = sent;
      liveSentSince = now;
   }
   DrawGaugePanel();
}

int FlipsLastMinute()
{
   int k = 0;
   datetime now = TimeTradeServer();
   for(int i = 0; i < flipCount; i++) if(now - flipTimes[i] <= 60) k++;
   return k;
}

void OnTimer()
{
   GaugeEverySecond();
   Step();
   double profit;
   int n = CountPositions(profit);
   string ph = "PAUSE " + IntegerToString((int)((GetTickCount64() - phaseStart) / 1000)) + "/" + IntegerToString(PauseSeconds) + " s";
   if(phase == 0 && TimeTradeServer() < pauseUntil) ph = "PAUSE apres une serie de pertes, jusqu'a " + TimeToString(pauseUntil, TIME_SECONDS);
   if(phase == 0 && dayStopped) ph = "ARRET POUR LA JOURNEE (limite de perte du jour atteinte)";
   if(phase == 1) ph = "RAFALE OUVERTE : on attend +" + DoubleToString(StartClosePct, 1) + " %";
   if(phase == 2) ph = "FERMETURE PROGRESSIVE (plus grosse position gagnante d'abord)";
   double ml = AccountInfoDouble(ACCOUNT_MARGIN_LEVEL);
   Comment("LIVE TIKTOK  -  ", _Symbol, "   (strategie du live + reduction des pertes)",
           "\nPhase : ", ph,
           "\nPositions : ", n, "   resultat en cours : ", DoubleToString(profit, 2),
           "   (", (startBalance > 0 ? DoubleToString(100.0 * profit / startBalance, 2) : "0"), " %)",
           "\nJAUGE (chaque seconde) : ACHAT ", DoubleToString(50.0 + 5.0 * score, 0), " %   VENTE ", DoubleToString(50.0 - 5.0 * score, 0),
           " %   sentiment : ", (liveSent > 0 ? "HAUSSIER" : (liveSent < 0 ? "BAISSIER" : "NEUTRE")),
           " depuis ", IntegerToString((int)(TimeTradeServer() - liveSentSince)), " s   (score ", score, ")",
           "\n30 dernieres secondes : ", timeline, "   bascules sur 1 min : ", FlipsLastMinute(),
           "\nDernieres bascules : ", flipLog[0], (StringLen(flipLog[1]) > 0 ? "  |  " + flipLog[1] : ""),
           "\nLecture pendant la pause : moyenne ", (gaugeN > 0 ? DoubleToString(50.0 + 5.0 * gaugeSum / gaugeN, 0) + " % achat" : "-"),
           ", basculements ", flips, "   mode : ", (DirectionMode == 0 ? "jauge" : (DirectionMode == 1 ? "jauge + contre-courant" : "contre-courant")),
           " (confiance min ", DoubleToString(MinConfidence, 0), " %)",
           "\nMouvement du prix sur ", LookbackSeconds, " s : ", DoubleToString(PriceMove(LookbackSeconds), 2),
           "   tendance de fond : ", (TrendSide() > 0 ? "HAUSSIERE (achats sur les creux)" : (TrendSide() < 0 ? "BAISSIERE (ventes sur les rebonds)" : "-")),
           "\nSecurisation : ", (banked ? "plus grosse position encaissee" : "en attente de +" + DoubleToString(BankPct, 1) + " %"),
           "   verrou : ", (locked ? "ACTIF (fermeture a +" + DoubleToString(FloorPct, 1) + " %)" : "inactif"),
           "   meilleur gain de la rafale : ", DoubleToString(peakPct, 2), " %",
           "\nAnnonces : ", (InNewsWindow() ? "FENETRE D'ANNONCE (pas de nouvelle rafale)" : "rien a proximite"),
           "   heure de Paris : ", TimeToString(ParisNow(), TIME_MINUTES),
           "\nSpread paye a l'ouverture de la rafale : ", DoubleToString(spreadCost, 2),
           (startBalance > 0 ? " (" + DoubleToString(100.0 * spreadCost / startBalance, 2) + " % du solde)" : ""),
           "\nProtections : reduction a -", DoubleToString(ReduceStep1Pct, 1), " % / -", DoubleToString(ReduceStep2Pct, 1),
           " %, tout ferme a -", DoubleToString(CloseAllPct, 1), " %, duree max ", MaxBurstMinutes, " min",
           "\nNiveau de marge : ", (ml > 0 ? DoubleToString(ml, 0) + " %" : "-"),
           "\nRafales : ", bursts, "   perdantes d'affilee : ", losingStreak,
           "   resultat du jour : ", (dayStartBalance > 0 ? DoubleToString(100.0 * (AccountInfoDouble(ACCOUNT_BALANCE) / dayStartBalance - 1.0), 1) + " %" : "-"),
           "\nDernier evenement : ", lastEvent,
           "\nDerniere erreur : ", lastError,
           "\nSolde : ", DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2),
           "   Equite : ", DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2));
}
//+------------------------------------------------------------------+
