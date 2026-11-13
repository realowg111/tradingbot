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

## Réglages principaux

| Paramètre | Défaut | Rôle |
|---|---|---|
| `Preset` | TENDANCE | TENDANCE, VIDEO, SECONDES ou CUSTOM |
| `RiskPerTradePct` | 1 | Risque par trade en % de l'équité (ou `FixedLot`) |
| `LotProgression` | 1 (désactivé) | Grille : taille × facteur à chaque position ajoutée. Mode VIDEO seulement, en démo. |
| `DailyStopPct` | 0 (désactivé) | Arrêt pour la journée au-delà de x % de perte |
| `ServerMinusNY` | 7 | Décalage serveur − New York, utilisé dans le testeur (le robot le détecte seul en démo et en réel) |
| Autres | — | Utilisés seulement en mode CUSTOM |

## Test conseillé

Dans le testeur de stratégies : modèle **« Chaque tick basé sur des ticks réels »**, XAUUSD et US100, 12 derniers mois, capital de 500. Comparez le résultat avec NoiseBoundaryUS100 sur la même période, et envoyez-moi les deux rapports.
