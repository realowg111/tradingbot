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
