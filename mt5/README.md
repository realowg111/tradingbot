# Robot MT5 : Noise Boundary US100

Expert Advisor MetaTrader 5 qui applique la stratégie validée dans `scripts/RESEARCH_REPORT.md` (momentum intraday sur le Nasdaq 100, Zarattini, Aziz et Barbon 2024), avec les mêmes règles que le backtest `scripts/nasdaq_daytrade/qqq_intraday_momentum.py`.

Backtest de référence (QQQ 2014–2024, frais 0,01 %) : +15,5 %/an à la taille 1,0, +7,8 %/an à la taille 0,5, environ 1 trade par jour, 40 % de trades gagnants, gain moyen 1,9 fois la perte moyenne.

## Ce que fait le robot

- **9h30 New York (15h30 Paris) :** il lit l'ouverture du jour et calcule la « zone de bruit » à partir des 14 dernières séances.
- **Toutes les 30 minutes de 10h00 à 15h30 New York :**
  - achat si la clôture de la bougie M1 passe au-dessus de la zone ;
  - vente à découvert si elle passe en dessous ;
  - sortie d'un achat si le prix repasse sous max(zone haute, VWAP), et l'inverse pour une vente.
- **15h59 New York :** tout est fermé. Aucune position la nuit, donc pas de swap.
- **Taille :** `SizeFactor` × min(4, 2 % / volatilité sur 14 jours) × capital.
- **Sécurités :**
  - stop de secours chez le courtier (bord opposé de la zone) ;
  - disjoncteur à -3 % sur la journée ;
  - pas d'entrée si le spread est trop large.
- **Tableau de bord sur le graphique :** zones, VWAP, position, P&L du jour, taux de réussite, gain moyen / perte moyenne, espérance par trade.
- **Journal :** `MQL5/Files/NoiseBoundary_log.csv`, chaque décision horodatée.

## Installation (compte démo)

1. Dans MT5 : **Fichier → Ouvrir le dossier des données**, puis aller dans `MQL5/Experts/`.
2. Y copier `NoiseBoundaryUS100.mq5`.
3. Ouvrir **MetaEditor** (F4), ouvrir le fichier, puis **Compiler** (F7). Il doit afficher « 0 errors ». Sinon, envoyez-moi les erreurs.
4. Dans MT5, ouvrir un graphique **US100** (ou NAS100 / USTEC selon le courtier) en **M1**.
5. Faire glisser le robot depuis le Navigateur sur le graphique, cocher **Autoriser le trading algorithmique**, puis activer le bouton **Algo Trading** de la barre d'outils.
6. Vérifier dans le tableau de bord (en haut à gauche) que l'**heure New York** affichée est juste. Elle doit avoir 6 h de moins que l'heure de Paris, sauf quelques semaines par an où l'écart est de 5 h.

Le robot a besoin d'environ un mois d'historique M1. Faites défiler le graphique M1 vers la gauche si MT5 n'en a pas encore chargé assez.

## Tester d'abord dans le testeur de stratégies

1. **Affichage → Testeur de stratégies**, choisir `NoiseBoundaryUS100`, symbole US100, période M1.
2. Modèle : **« Chaque tick basé sur des ticks réels »**.
3. Dates : au moins les 12 derniers mois.
4. Paramètre `ServerMinusNY` : 7 pour la plupart des courtiers (serveur en GMT+2/+3). Si votre courtier est en GMT+0, mettre 5.
5. Me renvoyer le rapport : profit, nombre de trades, % de gagnants, perte maximale.

## Paramètres

| Paramètre | Défaut | Rôle |
|---|---|---|
| `SizeFactor` | 0,5 | Taille prudente de départ. 1,0 = taille de l'article. |
| `MaxDailyLossPct` | 3 | Disjoncteur : ferme tout et arrête pour la journée au-delà de -3 %. 0 = désactivé. |
| `MaxSpreadPct` | 0,01 | Pas d'entrée si le spread dépasse 0,01 % du prix (≈ 2 points à 20 000). |
| `UseEmergencySL` | true | Stop placé chez le courtier en cas de coupure. |
| `UseTakeProfit` | false | TP fixe. Le backtest n'en a pas : laisser à false pour le reproduire. |
| `Lookback`, `CheckEveryMin`, `BandMult` | 14, 30, 1 | Valeurs de l'article, à ne pas optimiser. |

## Différences avec le backtest

- **VWAP :** les CFD n'ont pas de vrai volume, le robot utilise le volume de ticks. C'est une approximation.
- **Prix :** CFD US100 du courtier au lieu de QQQ. Les mouvements sont presque identiques, mais le spread et les horaires varient selon le courtier.
- **Exécution :** au marché, juste après la clôture de la bougie de décision. Le backtest utilise l'ouverture de la minute suivante.

## Ce qu'on vérifie pendant la démo (1 à 2 mois)

- Chaque jour, comparer les trades du journal CSV à ceux du backtest Python sur les mêmes dates.
- Glissement moyen par trade inférieur à 0,005 % du prix.
- Gain moyen / perte moyenne autour de 1,9 et taux de réussite autour de 40 %, sur au moins 30 à 40 trades.
- Au-delà, on peut passer en réel à la taille 0,5.

---

# Robot MT5 : Scalper 12 Indicateurs (style de la vidéo)

`Scalper12Indicators.mq5` reproduit le robot de la vidéo TikTok :
- **12 indicateurs** : RSI 14, tendance H1, écart à la MM20, MACD, structure, Bollinger, volatilité, VWAP, momentum 5 et 15, cassure, alignement. Dix d'entre eux votent haussier ou baissier.
- **Jauge de confiance ACHAT % / VENTE %**, calculée à partir des votes.
- **Exécution à chaque cycle** (chaque bougie M1, ou chaque tick en option) dès que 8 votes sur 10 sont alignés.
- **TP et SL automatiques** en multiples de l'ATR, envoyés au courtier avec l'ordre. Jusqu'à 5 positions dans le même sens.
- **Panneau à l'écran :** solde, équité, P&L du jour, taux de réussite, gain moyen comparé à la perte moyenne, espérance par trade, les 12 indicateurs avec leur vote, et un journal en direct.

⚠️ **Avertissement :** la reconstruction de ces règles en Python (`scripts/xau_daytrade/scalper_backtest.py`) a perdu de l'argent sur l'or et l'EUR/USD de 2009 à 2026, avec les 108 réglages testés, même sans frais. Le testeur MT5 en ticks réels chez votre courtier dira la même chose ou non. À tester d'abord en compte démo. En réel, n'engagez que de l'argent que vous acceptez de perdre.

## Installation

Même procédure que le robot Noise Boundary :
1. Copier le fichier dans `MQL5/Experts`.
2. Le compiler avec F7 dans MetaEditor.
3. Le glisser sur un graphique M1 (XAUUSD, US100…) et activer **Algo Trading**.

## Les deux modes (paramètre `Preset`)

| | **TENDANCE** (par défaut) | **VIDEO** |
|---|---|---|
| Idée | Ce que nos backtests ont appris | Le comportement observé dans la vidéo |
| Direction | Seulement dans le sens de la tendance du jour (noise boundary, séance de New York) | Les deux sens |
| Entrée | Repli sur l'EMA9 puis reprise, confirmé par au moins 6 votes sur 10 | 8 votes sur 10, analyse à chaque tick |
| Stop | Sous le dernier creux (5 bougies) | 1,5 ATR |
| Objectif | 5 fois le risque | 0,2 ATR (minuscule, touché en quelques secondes) |
| Durée max | 2 h | 30 min |
| Heures | 10h–12h New York (16h–18h Paris) | Toutes |
| Positions | 1 à la fois | Jusqu'à 5, rapprochées ; tailles croissantes avec `LotProgression` > 1 (grille) |

Résultats Python de référence (Nasdaq 2014–2024, frais réels, 0,5 % de risque par trade) :
- TENDANCE (version sans filtre de votes) : environ -3,6 %/an, 182 trades/an. C'est le meilleur des scalps testés, mais il reste négatif.
- VIDEO : perte nette sur l'or et l'EUR/USD de 2009 à 2026, même sans frais.

Le testeur MT5 en ticks réels chez votre courtier donnera le verdict final.

`PERSONNALISE` (Preset = CUSTOM) : tous les paramètres ci-dessous sont utilisés tels quels.

## Mode SECONDES (`Preset = SECONDES`) : la boucle de la vidéo

1. **Cycle toutes les 2 secondes.** Si aucune position n'est ouverte et qu'au moins 6 votes sur 10 sont d'accord **et** que le prix a bougé d'au moins 0,15 ATR dans ce sens au cours des 10 dernières secondes, le robot ouvre **0,05 lot**, avec un stop de départ à 0,5 ATR et sans TP.
2. **Coupe rapide :** si la position n'est pas gagnante au bout de **15 secondes**, elle est fermée. C'est la perte minime de la vidéo.
3. **Protection :** dès +0,10 ATR de gain, le stop passe au prix d'entrée. Dès +0,20 ATR, un stop suiveur à 0,20 ATR accompagne le prix.
4. **Renforts :** à chaque +0,15 ATR depuis la dernière entrée, une nouvelle position plus grosse est ajoutée, jusqu'à 4 renforts : 0,05 → 0,07 → 0,11 → 0,16 → 0,25 lot. Ce sont eux qui font les gros gains quand le mouvement continue.
5. **Durée max :** 3 minutes par position. Ensuite on recommence.

Tous ces nombres sont réglables dans le groupe « Mode SECONDES ». Ce mode ne peut pas être vérifié sur mes données en bougies d'1 minute : il se teste dans le testeur MT5 en **« Chaque tick basé sur des ticks réels »**, puis sur le compte démo.

## Mode RAFALE (`Preset = RAFALE`) : reproduit le journal de la vidéo

Dans la vidéo, à 09:06:12, six achats sont ouverts dans la même seconde (0,05 / 0,05 / 0,10 / 0,15 / 0,20 / 0,30 lot). Ils se ferment un par un entre 09:06:14 et 09:06:18 avec +11,34 €, +6,77 €, +1,89 €, +0,58 €, +2,86 € et +3,81 €, pendant que le prix monte de 3963,9 à 3964,75. Ce mode reproduit cette boucle :

1. **Un calcul toutes les 5 secondes** : les 12 indicateurs donnent ACHAT % / VENTE % et le nombre de votes alignés.
2. **Signal validé** dès que 7 votes sur 10 sont alignés : le robot ouvre une **rafale de 6 positions d'un coup** (`RafaleLots` = 0,30 / 0,20 / 0,15 / 0,10 / 0,05 / 0,05).
3. **Chaque position a son propre TP** (`RafaleTPsATR` = 0,10 / 0,15 / 0,20 / 0,30 / 0,45 / 0,60 ATR). La plus grosse prend son bénéfice en premier, sur le tout début du mouvement, et les petites visent plus loin.
4. **Stop commun** à 0,5 ATR. Après le premier TP, le stop des positions restantes passe au prix d'entrée.
5. **Fermeture rapide** si la rafale n'est pas gagnante au bout de 10 secondes, ou si le signal s'inverse au calcul suivant : ce sont les « Clôture -0,10 € ». Durée maximale : 60 secondes.
6. **Le calcul suivant recommence.**

Sur un compte de 1 000 €, réglez `RafaleLotScale` à 0,2 ou 0,3 : une rafale complète fait 0,85 lot, ce qui est beaucoup pour ce capital. Ce mode se teste dans le testeur MT5 en « ticks réels » puis en démo. Mes données en bougies d'1 minute ne peuvent pas le vérifier.

### Mode RAFALE_RAPIDE : le rythme de la vidéo

Dans la vidéo, les rafales s'ouvrent à 09:06:11, 09:06:21, 09:06:31 et 09:06:44, soit environ une toutes les 10 secondes, en changeant de sens. `Preset = RAFALE_RAPIDE` reprend le mode RAFALE avec ce rythme :

| Réglage | RAFALE | RAFALE_RAPIDE |
|---|---|---|
| Calcul toutes les | 5 s | 5 s |
| Votes requis | 7 sur 10 | **2** (il suit la majorité, comme une jauge à 59 / 42 %) |
| Coupe si la rafale n'est pas gagnante après | 10 s | **5 s** |
| Durée max d'une rafale | 60 s | **10 s** |
| Spread max | 0,3 ATR | **0,5 ATR** |

Les lots, les TP et le stop restent ceux du groupe « Mode RAFALE ». Ce rythme multiplie le nombre de trades, donc les frais : à comparer avec RAFALE sur un 2e graphique avec un autre `Magic`.

### Mode LIVE_PROTEGE : le live TikTok, avec une limite de perte

Dans le live, le robot ouvre 6 à 7 positions sans stop, laisse la rafale descendre (-23 €, -37 €, avec une marge jusqu'à 105 %), puis ferme tout dès que le total redevient positif. Les pertes ne sont jamais encaissées, jusqu'au jour où le prix ne revient pas.

`Preset = LIVE_PROTEGE` garde la mécanique, mais avec des limites, en % du solde au moment de la rafale :

| Règle | Valeur |
|---|---|
| Rafale | 6 positions (lots de `RafaleLots` × `RafaleLotScale`), **sans SL ni TP individuels** |
| Signal | 7 votes sur 10, calcul toutes les 5 s |
| Objectif du panier | toute la rafale est fermée à **+1 %** |
| Limite de perte du panier | toute la rafale est fermée à **-0,7 %** : la perte est encaissée, petite et connue |
| Protection du gain | dès que la rafale a atteint +0,5 %, fermeture si elle retombe sous la moitié de son meilleur gain |
| Durée max | 30 minutes |

Comme le gain visé (+1 %) est plus grand que la perte maximale (-0,7 %), le compte monte dès que plus de 41 % des rafales atteignent leur objectif. Les mêmes règles de panier existent pour tous les modes RAFALE, dans le groupe « Panier » (0 = désactivé).

Sur 1 000 €, gardez `RafaleLotScale` à 0,2 : une perte de 0,7 % (7 €) correspond alors à un mouvement de l'or de quelques dollars contre la rafale.

## Réglages principaux

| Paramètre | Défaut | Rôle |
|---|---|---|
| `Preset` | TENDANCE | TENDANCE, VIDEO, SECONDES, RAFALE, RAFALE_RAPIDE, LIVE_PROTEGE ou CUSTOM |
| `RiskPerTradePct` | 1 | Risque par trade en % de l'équité (ou `FixedLot`) |
| `LotProgression` | 1 (désactivé) | Grille : taille × facteur à chaque position ajoutée. Mode VIDEO seulement, en démo. |
| `DailyStopPct` | 0 (désactivé) | Arrêt pour la journée au-delà de x % de perte |
| `ServerMinusNY` | 7 | Décalage serveur − New York, utilisé dans le testeur (le robot le détecte seul en démo et en réel) |
| Autres | — | Utilisés seulement en mode CUSTOM |

## Test conseillé

Dans le testeur de stratégies : modèle **« Chaque tick basé sur des ticks réels »**, XAUUSD et US100, 12 derniers mois, capital de 500. Comparez le résultat avec NoiseBoundaryUS100 sur la même période, et envoyez-moi les deux rapports.

---

# Robot simple : Scalper12Live (un seul comportement, celui du live)

`Scalper12Live.mq5` est un robot à part, sans préréglage à choisir :
1. Toutes les **2 secondes**, les 12 indicateurs votent **sur le prix en direct** (bougie en cours) et donnent la jauge ACHAT % / VENTE %. Les votes changent donc toutes les quelques secondes, comme dans la vidéo. Avec `LiveVotes` = false, ils ne changent qu'à la clôture de chaque bougie d'1 minute.
2. Dès que **5 votes sur 10** sont alignés, il ouvre une **rafale de 6 positions** (0,30 / 0,20 / 0,15 / 0,10 / 0,05 / 0,05 × `LotScale`), sans SL ni TP individuels.
3. La rafale est gérée **comme un tout**, en % du solde :
   - fermée à **+0,6 %** (objectif) ;
   - fermée à **-0,4 %** (limite de perte : la perte est encaissée, petite et connue) ;
   - si elle a atteint +0,3 % puis retombe sous la moitié de son meilleur gain, fermée pour protéger le gain ;
   - fermée après 10 minutes ou si le signal s'inverse.
4. Puis il recommence.

Le spread se paie à chaque rafale. Avec `LotScale` = 0,2 sur 1 000 €, une rafale fait 0,17 lot, et 0,20 $ de spread sur l'or coûte environ 3,4 €, soit 0,34 % du compte. C'est pour ça que l'objectif ne doit pas descendre sous environ 0,5 % : en dessous, le spread mange presque tout le gain.

Installation : copier le fichier dans `MQL5/Experts`, compiler (F7), le glisser sur **XAUUSD M1**, garder `LotScale` = 0,2 pour 1 000 €, activer **Trading Algo**. Retirez les autres robots de ce graphique.

La ligne jaune du panneau dit à chaque calcul ce que fait le robot : votes, « attend : … », « RAFALE », ou l'état de la rafale ouverte. Si le trading automatique n'est pas autorisé, elle affiche « BLOQUE ». Si un ordre est refusé, le journal affiche le code et sa description.

---

# LiveTikTok.mq5 : reproduction du live « HFT ROBOT » (démo uniquement)

Lecture image par image du live (95 images, 2 par seconde, 4 rafales en 42 s, solde de 489,75 € à 766,99 €) :

| | Rafale 1 | Rafale 2 | Rafale 3 | Rafale 4 |
|---|---|---|---|---|
| Ouverture | 4,5 s | 17 s | 28,5 s | 41 s |
| Pause avant (sans position) | — | 5 s | 5,5 s | 5,5 s |
| Sens | achat | vente | achat (après une baisse de 4 $) | vente (après une hausse de 2 $) |
| Positions | 6 | 6 | 7 | 7 |
| Lots au total / solde | 0,42 / 490 | 0,46 / 527 | 0,64 / 563 | 0,90 / 619 |
| Pire moment | -22,68 | -21,30 | -37,50 (marge 105 %) | -9,55 (marge 95 %) |
| Ordre de fermeture | gros lots d'abord | 0,10 → 0,10 → 0,08 → 0,08 → 0,05 → 0,05 | 0,15 → 0,15 → 0,08… | 0,30 → 0,15 → 0,20 → 0,10 → 0,05… |
| Résultat | +37 | +36 | +56 | +148 |

Règles codées :
1. Pause de 5 s sans position.
2. Sens à contre-courant du mouvement des 20 dernières secondes : achat après une baisse, vente après une hausse.
3. Rafale de 7 positions (proportions 0,30 / 0,20 / 0,15 / 0,10 / 0,05 / 0,05 / 0,05), dont le total est calculé pour utiliser 70 % du solde en marge.
4. Aucun stop, aucun TP.
5. À +3 % du solde, fermeture progressive : la plus grosse position gagnante d'abord, une toutes les 0,7 s, uniquement les positions en gain.
6. Retour à la pause.

`EmergencyPct` (0 par défaut, comme le live) permet un arrêt d'urgence.

Simulation des mêmes règles sur l'or 2024–2025 (`scripts/xau_daytrade/tiktok_live_sim.py`, 99 essais de 30 jours, levier 1:500) : 89 % des rafales gagnantes, mais 100 % des comptes perdus, en 0,42 jour en médiane (0,26 jour en utilisant 88 % de la marge, comme dans la 4e rafale).

## LiveTikTok, version protégée (1.10)

Protections ajoutées sans changer le style (pause, contre-courant, rafale, fermeture progressive de la plus grosse position) :
1. contre-courant seulement dans le sens de la tendance de fond (EMA 50 en H1) ;
2. réduction de la rafale si elle perd, la plus grosse position d'abord : à -2 %, puis à -3,5 %, puis tout à -5 % ;
3. fermeture après 15 minutes sans gain ;
4. rafales plus petites : 20 % du solde en marge au lieu de 70 %.

Simulation sur l'or 2024–2025 (`scripts/xau_daytrade/tiktok_protected_sim.py`, 99 essais de 30 jours, 500 au départ) :

| Version | Comptes perdus | Durée médiane avant la perte | Rafales gagnantes |
|---|---|---|---|
| Live (70 % de marge, aucune protection) | 100 % | 0,4 jour | 90 % |
| 20 % de marge | 100 % | 2,1 jours | 96 % |
| 20 % + filtre de tendance | 100 % | 2,5 jours | 96 % |
| 20 % + réduction -2 / -3,5 / -5 % | 100 % | 3,3 jours | 48 % |
| 20 % + tendance + réduction + 15 min | 100 % | 3,1 jours | 37 % |
| 10 % + tendance + réduction + 15 min | 100 % | 8,4 jours | 34 % |

Les protections ralentissent la perte, de quelques heures à plus d'une semaine, mais ne l'empêchent pas. La stratégie elle-même n'a pas d'avantage : entrer à contre-courant toutes les quelques minutes gagne en moyenne autant que ça perd, et chaque rafale paie un spread d'environ 0,6 % du compte à 20 % de marge. Les protections changent seulement la façon de perdre : soit de rares grosses pertes, soit des pertes moyennes plus fréquentes.
