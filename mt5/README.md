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
