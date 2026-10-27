# Charte du bot : règles de décision

Ce document est le « prompt » du bot : les règles qu'il applique seul, sans validation humaine. Chaque règle correspond à du code (`bot/strategy.py`, `bot/risk.py`, `bot/manager.py`). Un LLM n'est pas utilisé pour décider en direct : il serait trop lent pour du scalping, coûteux, et ses décisions ne seraient pas reproductibles en backtest. Les règles ci-dessous sont celles qu'un trader discipliné applique, écrites pour qu'une machine les suive sans exception.

## 1. Identité

Scalper agressif sur l'or (XAUUSD) et les cryptos majeures (BTC, ETH). Il cherche des mouvements courts (quelques minutes à 4 heures) dans le sens des institutions. L'agressivité porte sur la fréquence et la rapidité d'exécution, jamais sur la taille du risque.

**Priorité absolue : survivre.** Un trade raté coûte une opportunité, un compte détruit coûte tout.

## 2. Lecture du marché (dans cet ordre)

1. **Biais institutionnel (H1).** Haussier si clôture > EMA50 > EMA200 et EMA50 montante. Baissier à l'inverse. Sinon, **pas de trade** : le bot ne trade jamais contre le biais H1 et ne force rien en range.
2. **Structure (H1).** Plus hauts et plus bas croissants (HH/HL) ou décroissants (LH/LL), mesurés sur des swings confirmés.
3. **Inter-marché (paires).** Pour ETH et les altcoins, BTC est l'actif directeur : si BTC a un biais H1 opposé, le trade est refusé. Pour l'or, on peut déclarer un actif de référence inversé (ex. indice dollar) dans la config.
4. **Liquidité.** Les ordres stop des particuliers s'accumulent sous les plus bas évidents (swing low M5, plus bas de la veille, bas de la session asiatique) et au-dessus des plus hauts. Les institutions vont chercher cette liquidité avant de pousser dans leur sens.
5. **Empreintes institutionnelles.** Bougies de déplacement (grand corps, clôture près de l'extrême), fair value gaps (déséquilibres de prix), volume relatif élevé.
6. **Moment.** London open (7h-10h UTC) et New York (12h-16h UTC) concentrent le volume. L'or ne se trade qu'entre 7h et 17h UTC, jamais le vendredi soir.

## 3. Déclencheurs d'entrée (M5, sens du biais uniquement)

- **Balayage de liquidité + reprise** : la mèche passe sous un niveau de liquidité, la bougie clôture au-dessus, puis une bougie de confirmation clôture au-dessus du plus haut précédent. Stop sous la mèche du balayage.
- **Pullback de tendance** : EMA9 > EMA21 > EMA50, le prix revient toucher la zone EMA21, le RSI se recharge (35-52), puis une bougie de confirmation repart dans le sens du biais. Stop sous le plus bas du pullback.

## 4. Score de confluence (sur 14) : il faut au moins 8

| Élément | Points |
|---|---|
| Biais H1 aligné (obligatoire) | 2 |
| Structure H1 alignée | 1 |
| Balayage de liquidité / pullback | 2 / 1 |
| Bon côté du VWAP du jour | 1 |
| Killzone London / New York | 1 |
| Fair value gap récent | 1 |
| Bougie de déplacement récente | 1 |
| RSI non extrême | 1 |
| ADX H1 ≥ 20 (tendance réelle) | 1 |
| Actif directeur aligné | 1 |
| Volume relatif ≥ 1,5 | 1 |
| Zone discount (achat) / premium (vente) | 1 |

## 5. Vetos (aucun score ne les contourne)

- Spread > 15 % de l'ATR ;
- volatilité trop faible (marché mort) ou extrême (panique) ;
- fenêtre d'annonce économique (± 30 min) ;
- moins de 1,2R de place avant la prochaine liquidité H1 (on ne vise pas dans un mur) ;
- stop nécessaire > 2,5 ATR ;
- actif directeur dans le sens opposé ;
- flux de prix figé ou marché fermé.

## 6. Taille de position

- Risque par trade : **0,5 % du capital** (plafond 1 %). Le lot est calculé pour que la perte au stop, frais et spread compris, ne dépasse pas ce montant.
- Si même le lot minimum risque trop, le trade est ignoré : le bot n'augmente jamais le risque pour « rentrer quand même ».
- Après 2 pertes de suite : risque divisé par 2. En drawdown de plus de 4 % : risque divisé par 2.
- **Jamais de martingale, jamais de moyenne à la baisse, jamais de stop élargi.**
- Levier effectif plafonné à 10.

## 7. Gestion du trade (automatique)

- Le SL et le TP final sont posés **chez le broker** dès l'ouverture : si le bot, le PC ou internet tombent, la position reste protégée.
- **+0,6R** : le stop remonte à -0,5R (risque divisé par deux).
- **+1R (TP1)** : 50 % de la position est encaissée, le stop passe à +0,1R. À partir d'ici, le trade ne peut plus perdre.
- **+1,5R** : stop à +0,7R. **+2R** : stop à +1,2R.
- Après TP1 : trailing stop à 1,2 ATR derrière le prix.
- **TP2 à 2,5R** pour le reste.
- Un scalp qui ne part pas est un mauvais scalp : après 12 bougies (1 h) sans avoir atteint +0,3R, sortie. Durée max : 4 h.
- Le stop ne recule jamais.

## 8. Protection du capital

| Règle | Effet |
|---|---|
| Perte du jour ≥ 2,5 % (flottant inclus) | Plus aucun trade jusqu'au lendemain |
| 3 pertes de suite | Pause de 2 heures |
| Drawdown ≥ 8 % depuis le plus haut | **Kill switch** : tout est fermé, le bot s'arrête de trader. Seul un humain peut le relancer (`python -m bot reset-halt`) |
| 1 seule position par groupe corrélé | BTC et ETH ne s'additionnent pas |
| 3 positions max, 20 trades max par jour | Pas de sur-trading |

## 9. Autonomie

- Boucle continue : gestion des positions toutes les 5 s, analyse à chaque clôture de bougie M5.
- Reconnexion automatique avec délai croissant en cas de coupure broker.
- État sauvegardé à chaque cycle : après un redémarrage, le bot reprend ses positions là où il les avait laissées.
- Toute position du bot sans stop trouvée au démarrage est fermée immédiatement.
- Journal CSV de chaque trade et notifications Telegram (facultatives).

## 10. Sur le taux de réussite

Un taux de réussite de 70-85 % n'est pas une promesse que ce bot (ni aucun autre) peut tenir sur le marché réel. Et à lui seul, il ne veut rien dire : un bot qui gagne 85 % du temps avec +0,2R et perd 15 % du temps avec -1,5R perd de l'argent.

Ce qui compte, c'est l'**espérance** (gain moyen par trade, en R) et le **drawdown max**. La gestion ci-dessus pousse le taux de trades **non perdants** vers le haut (TP1 + break-even) tout en gardant des gains plus gros que les pertes. Les vrais chiffres ne se connaissent qu'avec un backtest sur plusieurs mois de vos données M5, puis plusieurs semaines en paper trading.
