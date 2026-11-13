# Laboratoire de scalping / « HFT » particulier

Données : Nasdaq (QQQ 1 min, 2014–2024) et or (1 min, 2009–2026). Frais réels : 0,01 % (US100 / MNQ) et 0,007 % (or en compte ECN). Risque de 0,5 % par trade. Un trade à la fois, et si le stop et l'objectif tombent dans la même bougie, on compte le stop.

## 1. Trois familles de scalps (`scalping_lab.py`)

| Scalp | Marché | Trades/an | Gagnants | Sans frais | Frais réels | Variantes positives |
|---|---|---|---|---|---|---|
| S1 repli dans la tendance du jour | Nasdaq | 867 | 43 % | +6 %/an | -30 %/an | 0/6 |
| S2 retour au VWAP (ordres limites) | Nasdaq | 2 267 | 47 % | +291 %/an | +154 %/an, mais **-31 %/an depuis 2019** | 6/6 |
| S3 explosion de volatilité | Nasdaq | 38 | 45 % | -0,5 %/an | -1,3 %/an | 0/6 |
| S2 retour au VWAP | Or | 2 529 | 37 % | -38 %/an | -215 %/an | 0/6 |
| S3 explosion de volatilité | Or | 861 | 45 % | -11 %/an | -48 %/an | 0/6 |

S2 sur le Nasdaq fait +340 %/an avant 2019, puis -31 %/an depuis, et perd avec des frais ×3. Il échoue donc au critère des deux périodes. C'est le profil typique de l'effet bid-ask (le dernier prix échangé oscille entre l'achat et la vente, ce qui crée des retournements impossibles à capturer en réel) ou d'une anomalie disparue. Il est rejeté.

## 2. Jauge de probabilité directionnelle (`probability_model.py`)

C'est la version sérieuse de la jauge « Achat 15 % / Vente 85 % » de la vidéo :
- un modèle de gradient boosting lit les 12 indicateurs de la vidéo plus le régime de tendance validé ;
- toutes les 5 minutes, il estime la probabilité de toucher +3 ATR avant -3 ATR dans les 30 minutes ;
- test walk-forward : pour chaque année de 2017 à 2024, le modèle n'apprend que sur les années précédentes.

Calibration hors échantillon (confiance annoncée → réussite réelle) :

| Confiance annoncée | Décisions | Réussite réelle |
|---|---|---|
| 50–55 % | 77 263 | 52,0 % |
| 55–60 % | 33 883 | 53,7 % |
| 60–65 % | 5 411 | 53,7 % |
| 65–70 % | 610 | 54,6 % |
| 70 % et plus | 32 | 65,6 % |

Trading avec frais réels :

| Seuil | Trades/an | Gagnants | Résultat |
|---|---|---|---|
| 55 % | 1 969 | 51 % | -13 %/an |
| 60 % | 467 | 51 % | -4 %/an |
| 65 % | 64 | 51 % | -1 %/an |
| 70 % | 5 | 61 % | +0,5 %/an (trop peu de trades) |

Le modèle est trop confiant : quand il annonce 60 à 70 %, il ne gagne que 54 % du temps. Ce n'est pas assez pour couvrir les frais d'un trade à 1:1.

## Conclusion

Aucun scalp ne passe les critères. Le seul avantage qui survit aux frais et aux deux périodes reste la noise boundary (`../nasdaq_daytrade`), avec environ 1 trade par jour.

Limite : bougies d'1 minute. Un vrai test à la seconde demande les ticks du courtier, par exemple dans le testeur MT5 en mode « ticks réels ».
