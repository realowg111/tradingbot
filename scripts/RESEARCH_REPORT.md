# Recherche : meilleure stratégie de day trading / scalping pour un particulier

Toutes les stratégies ci-dessous ont été recodées et testées avec les mêmes règles :
- pas de look-ahead : un signal est exécuté à l'ouverture de la bougie suivante ;
- si le stop et l'objectif sont dans la même bougie, on compte le stop ;
- frais à trois niveaux (sans frais, frais réels, frais ×3) ;
- paramètres de la source fixés avant de voir les résultats, puis une grille de sensibilité ;
- deux périodes séparées ;
- fuseaux horaires vérifiés, heure d'été comprise.

## Données

| Marché | Source | Période |
|---|---|---|
| Nasdaq 100 (QQQ, 1 min) | Hugging Face `Maxim37/timeseries-1m-QQQ-10y` | 2014-01 → 2024-01 |
| Or (XAUUSD, 1 min) | HistData (Hugging Face `fokan/xauusd-2009-2026`) | 2009-03 → 2026-01 |
| EUR/USD (1 min) | OANDA (Hugging Face `bunqi/OANDA_EURUSD_EURUSD`) | 2009-01 → 2026-10 |
| Bitcoin (BTCUSDT, 1 min) | Binance (Hugging Face `vaquum/binance_btcusdt_1m_klines`) | 2020-01 → 2026-11 |

Je n'ai pas trouvé de données minute gratuites sur 10 ans pour le S&P 500 (SPY/MES) : il n'est pas testé.

## Critères de sélection

1. Positive après frais réels sur les deux périodes.
2. Au moins 75 % des variantes de la grille positives.
3. Sharpe ≥ 0,8 après frais.
4. Pire baisse ≤ 25 %.
5. Au moins 200 trades.
6. Résultat qui ne dépend pas d'une seule année.

## Tableau comparatif (frais réels)

| Stratégie | Source | Marché | Rendement/an | Sharpe | Pire baisse | 2 périodes + | Grille + | Verdict |
|---|---|---|---|---|---|---|---|---|
| **Noise boundary, momentum intraday** | Zarattini, Aziz & Barbon 2024 (SSRN) | **Nasdaq** | **+15,5 %** | **1,06** | **-23 %** | ✅ (+14,9 / +16,2) | ✅ 7/7 | ✅ **RETENUE** |
| ORB 5 minutes, objectif 10R | Zarattini & Aziz 2023 (SSRN) | Nasdaq | -5,3 % | -0,06 | -74 % | ❌ | ❌ 0/12 | ❌ |
| Momentum de la dernière demi-heure | Gao, Han, Li & Zhou 2018 (JFE) | Nasdaq | -7,7 % | -0,98 | -58 % | ❌ | ❌ 0/7 | ❌ |
| 9am CR model (IFVG + order block) | TikTok | Nasdaq | ≈ +5,9 % (1 % de risque) | — | -61 % | ⚠️ (+1 / +11) | ✅ 24/24 | ❌ pire baisse, irrégulière |
| Cassure + retest | TikTok | Nasdaq | -4,7 % (1 % de risque) | — | -56 % | ❌ | ❌ 0/36 | ❌ |
| ORB 1re bougie 08h20 | Zarattini & Aziz (adapté) | Or (ECN) | +2,3 % | 0,41 | ≈ -30 % | ✅ | ❌ | ❌ Sharpe trop faible |
| Cassure du range asiatique | pratique courante | Or (ECN) | +2,1 % | 0,31 | ≈ -40 % | ✅ | ⚠️ | ❌ Sharpe trop faible |
| Noise boundary | Zarattini 2024 (adapté) | Or | -5,9 % | -0,67 | -67 % | ❌ | ❌ 0/27 | ❌ |
| Momentum intraday 13h | Gao / Baltussen (adapté) | Or | -3,9 % | -1,48 | -50 % | ❌ | ❌ 0/8 | ❌ |
| Scalper « HFT neural » à 12 indicateurs | TikTok | Or | -46 % | -9,5 | -100 % | ❌ | ❌ 0/108 | ❌ perd même sans frais |
| Nyao Scalper (MT5 open source) | GitHub | Or | perd 11 années sur 13 (2009-2021) | — | — | ❌ | — | ❌ |
| 9am CR model | TikTok | Or (ECN) | ≈ +2,4 % | — | -87 % | ⚠️ | ✅ | ❌ |
| Cassure + retest | TikTok | Or | -10 % | — | — | ❌ | ❌ 0/36 | ❌ |
| Les 4 stratégies intraday ci-dessus | — | EUR/USD | toutes négatives | -0,07 à -1,1 | — | ❌ | ❌ | ❌ |
| Scalper 12 indicateurs, 9am CR, cassure + retest | TikTok | EUR/USD | -13 à -40 % | — | — | ❌ | ❌ | ❌ |
| Momentum de la dernière demi-heure | Shen, Urquhart & Wang 2022 | BTC | -29 % | -5,8 | -90 % | ❌ | ❌ 0/6 | ❌ perd même sans frais |
| Noise boundary | Zarattini 2024 (adapté) | BTC | -61 % (+31 % sans frais) | -2,5 | -100 % | ❌ | ❌ 0/6 | ❌ les frais tuent tout |

Frais réels utilisés : Nasdaq 0,01 % par aller-retour (futures MNQ ou CFD US100 serré), or et EUR/USD 0,007 % (compte ECN), BTC 0,10 % (taker sur futures Binance).

## La stratégie retenue : noise boundary sur le Nasdaq

Code : `nasdaq_daytrade/qqq_intraday_momentum.py`. Règles complètes dans `nasdaq_daytrade/README.md`.

| | Taille ×0,5 (recommandée pour démarrer) | Taille ×1 (article) |
|---|---|---|
| Rendement/an | +7,8 % | +15,5 % |
| Semaine moyenne | +0,15 % | +0,29 % |
| Semaine médiane | +0,06 % | +0,10 % |
| Pire semaine | -2,5 % | -5,0 % |
| Meilleure semaine | +4,0 % | +8,0 % |
| Semaines positives | 53 % | 53 % |
| Mois positifs / pire mois | 62 % / -4,0 % | 60 % / -7,9 % |
| Pire baisse du capital | -12 % | -23 % |
| Sharpe | 1,06 | 1,06 |

- Environ 1 trade par jour (2 350 trades en 10 ans), 40 % de trades gagnants. Le gain moyen vaut 1,9 fois la perte moyenne.
- Les longs et les shorts gagnent tous les deux.
- Années positives : 8 sur 10. 2016 -9 %, 2019 -2 %, 2022 +21 % (alors que le Nasdaq a fait -33 %).
- Plus longue période sous le sommet du capital : 437 jours de bourse, environ 1 an et 9 mois.

## Limites

- **Frais :** avec des frais ×3 (0,03 %), le rendement tombe à +4 %/an et le Sharpe à 0,34. Il faut un courtier très bon marché : futures MNQ, ou Interactive Brokers sur QQQ.
- **Levier :** 2,2 en moyenne à la taille ×1, jusqu'à 4.
- **Données :** elles s'arrêtent en janvier 2024 et recoupent la période de l'article (2007-2024). Ce n'est pas un vrai test hors échantillon pour les auteurs, et rien n'est vérifié après 2024.
- **Exécution :** au prix d'ouverture de la minute suivante, sans glissement supplémentaire en cas de forte volatilité.
- **Rythme :** environ 1 semaine sur 2 est négative. La stratégie gagne par accumulation lente, pas chaque semaine.

## Plan de mise en production

1. **Code :** porter la stratégie sur la plateforme du courtier (Interactive Brokers en Python, ou NinjaTrader / MT5 pour le MNQ). Le backtest et le live doivent utiliser le même code de signal.
2. **Démo, 1 à 2 mois :** comparer chaque jour les trades réels à ceux que donne le backtest sur les mêmes jours : même direction, prix d'entrée, glissement, frais.
3. **Critères d'arrêt :**
   - glissement moyen supérieur à 0,005 % par trade ;
   - plus de 10 % de trades différents du backtest ;
   - baisse de plus de 12 % à la taille ×0,5 (le pire historique), ou de plus de 2 fois le pire historique à la taille testée.
4. **Réel :** commencer à la taille ×0,5 avec une partie du capital, passer à ×1 seulement après 6 mois conformes au backtest, ne jamais dépasser ×1.
5. **Suivi :** tableau de bord avec le rendement réel comparé au backtest, la pire baisse et le cumul des frais.

## Ce que cette recherche montre

Sur 20 stratégies testées sur 4 marchés, une seule passe tous les critères. Elle vient d'une étude publiée, pas d'une vidéo. Les stratégies TikTok testées perdent toutes avec des frais réels, ou ont des baisses supérieures à 60 %. Le scalping (moins d'1 h, beaucoup de trades) n'a passé aucun test : les frais d'un particulier sont trop élevés par rapport à des mouvements aussi courts.

Un objectif réaliste est de 0,15 à 0,3 % par semaine en moyenne, avec des semaines négatives. Pas 1 % par jour.
