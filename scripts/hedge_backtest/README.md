# Backtest de stratégies de hedge (MoonX futures)

Données : bougies MoonX, 500 jours (2025-06-14 → 2026-10-26) pour BTC, ETH, SOL en 1d, plus 83 jours en 4h pour BTC/ETH.

Lancer : `python3 hedge_backtest.py` (pandas + numpy).

Hypothèses : frais taker de 0,06 % par côté et par jambe ; funding de 0,01 %/8h payé par les longs et reçu par les shorts ; exécution à la clôture suivante (pas de look-ahead). Les 60 % premiers jours servent à l'entraînement (IS), les 40 % suivants au test (OOS).

## Résultats (période complète)

| Stratégie | Rendement | Max DD | Sharpe |
|---|---|---|---|
| Buy & Hold BTC (perp) | -34 % | -57 % | -0,54 |
| Hedge statique 50 % BTC | -17 % | -33 % | -0,54 |
| **Trend hedge BTC (SMA50)** | **+6 %** | **-26 %** | 0,29 |
| Buy & Hold ETH (perp) | -21 % | -70 % | 0,05 |
| **Trend hedge ETH (SMA50)** | **+85 %** | **-31 %** | 1,24 |
| Pairs ETH/BTC | +4,5 % (OOS -0,7 %) | -5 % | 0,62 |
| Pairs SOL/ETH | +24 % (instable selon les paramètres) | -12 % | 1,30 |
| Beta hedge long ETH / short BTC | +68 % (OOS -12 %) | -18 % | 1,32 |

Le trend hedge consiste à garder le long et à ouvrir un short de couverture à 100 % quand la clôture passe sous la SMA(n), puis à le fermer quand elle repasse au-dessus. Il bat le buy & hold sur les 18 combinaisons testées (3 actifs × SMA 20/30/50/75/100/150). C'est la seule stratégie robuste.

Limites : 500 jours couvrent surtout une phase baissière, qui est le régime le plus favorable à un filtre de tendance. Le slippage n'est pas modélisé, et les frais et le funding réels de MoonX ne sont pas connus.

## Or et argent (`python3 metals_backtest.py`)

Données : XAUUSD et XAGUSD MoonX sur 264 jours de bourse (oct. 2025 → oct. 2026), plus PAXG (or tokenisé, Gemini) 7 jours sur 7 pour comparer avec BTC. Coûts CFD : spread de 0,03 % par côté et swap de 0,01 % par jour sur les deux sens.

| Stratégie | Rendement | Max DD | Période de test (OOS) |
|---|---|---|---|
| Buy & Hold or | -3 % | -28 % | -7 % |
| Trend hedge or (SMA50) | +20 % | -14 % | +0 % |
| Buy & Hold argent | +11 % | -55 % | -18 % |
| Trend hedge argent (SMA50) | +7 % | -57 % | -3 % |
| Pairs argent/or | +7 % | -2 % | 0 trade |
| Beta hedge long argent / short or | +24 % | -27 % | -13 % |
| BTC → or quand BTC < SMA50 | -27 % | -41 % | — |
| Trend hedge BTC (même période) | -17 % | -33 % | — |
| Buy & Hold BTC (même période) | -37 % | -52 % | — |

Sur les métaux, rien n'est robuste. Le trend hedge sur l'or ne gagne qu'avec SMA30/50 (≈ 0 % en SMA20, -4 % en SMA100) et fait zéro sur la période de test. Sur l'argent, les fausses cassures de janvier 2026 l'ont pénalisé. Le pairs argent/or ne gagne qu'avec 4 paramétrages sur 9. Mettre le capital en or quand BTC baisse fait pire que rester à plat : l'or a aussi baissé (corrélation +0,34 avec BTC sur la période).
