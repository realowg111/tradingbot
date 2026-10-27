# tradingbot

Bot de scalping autonome pour l'or (XAUUSD) et la crypto (BTC, ETH), via MetaTrader 5 ou un exchange crypto (ccxt).

- Règles de décision du bot (sa « charte ») : [STRATEGIE.md](STRATEGIE.md)
- Recherches et backtests précédents : `scripts/hedge_backtest/`

## Ce que fait le bot

- Biais institutionnel H1 (EMA50/200, structure), entrées M5 sur balayage de liquidité ou pullback, score de confluence (VWAP, killzones, fair value gaps, déplacement, volume, actif directeur BTC).
- Lot calculé pour risquer 0,5 % du capital par trade, SL et TP posés chez le broker.
- Sécurisation automatique : stop à -0,5R à +0,6R, 50 % encaissé et break-even à +1R, paliers puis trailing ATR, sortie si le trade ne part pas.
- Arrêt du jour à -2,5 %, pause après 3 pertes, kill switch à -8 % depuis le plus haut.
- Boucle continue, reconnexion automatique, reprise après redémarrage, journal CSV, notifications Telegram.

## Installation (VPS Windows avec MT5)

```bat
git clone https://github.com/realowg111/tradingbot.git
cd tradingbot
pip install -r requirements.txt
copy config.example.toml config.toml
copy .env.example .env
```

Remplir `.env` (identifiants MT5) et vérifier dans `config.toml` les noms des actifs chez votre broker (`XAUUSD`, `BTCUSD`... certains brokers ajoutent un suffixe comme `XAUUSD.m`). Dans MT5, activer le bouton **Algo Trading**.

## Étapes avant l'argent réel

1. **Backtest sur vos données** (au moins 3 à 6 mois de M5) :
   ```bat
   python -m bot fetch --days 180
   python -m bot backtest --data XAUUSD=data/XAUUSD_M5.csv --data BTCUSD=data/BTCUSD_M5.csv --data ETHUSD=data/ETHUSD_M5.csv --out trades.csv
   ```
   Regarder surtout `esperance_R` (doit être > 0), `profit_factor` (> 1,2) et `max_drawdown_%`. Le taux de réussite seul ne suffit pas. Dans MT5, augmenter « Nombre max de barres dans le graphique » (Outils > Options > Graphiques) pour récupérer assez d'historique.
2. **Paper trading** 2 à 4 semaines (`mode = "paper"`, par défaut) : prix réels, ordres simulés.
   ```bat
   python -m bot run
   ```
3. **Live** avec un petit capital : `mode = "live"` dans `config.toml`, puis `python -m bot run --yes-live`.

Pour qu'il tourne en continu, lancer `scripts\vps_windows\start_bot.bat` depuis le Planificateur de tâches Windows (au démarrage) : il relance le bot automatiquement en cas d'arrêt.

## Commandes

| Commande | Rôle |
|---|---|
| `python -m bot run` | Lance le bot |
| `python -m bot backtest --data SYM=fichier.csv` | Backtest (même code que le live) |
| `python -m bot fetch --days 180` | Télécharge l'historique M5 du broker |
| `python -m bot status` | Capital, positions, arrêt éventuel |
| `python -m bot reset-halt` | Relance après un kill switch (décision humaine) |
| `python -m pytest tests` | Tests |

## Limites

- Aucun bot ne peut garantir un taux de réussite ni l'absence de perte. Les protections limitent les pertes, elles ne les suppriment pas (gaps du week-end, annonces, glissement).
- La stratégie n'a été testée ici que sur des prix simulés (les API d'exchange n'étaient pas accessibles depuis l'environnement de développement). Sa rentabilité réelle reste à mesurer avec le backtest et le paper trading ci-dessus.
- Le connecteur ccxt (exchange crypto) n'a pas été testé sur un vrai compte : le valider d'abord sur le testnet (`testnet = true`).
- Le calendrier des annonces économiques est à remplir à la main dans `news_blackout`.
