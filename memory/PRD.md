# Trading Bot — PRD (v8)

## Itération v8 (current) — MOTEUR MULTI-FACTEURS + SÉLECTION DES MARCHÉS ✅ DÉPLOYÉ, BOT TRADE EN RÉEL
- **BUG CRITIQUE corrigé** : l'ancien moteur décidait sur les prix du SIMULATEUR (random walk) même en réel. Nouveau: `services/market_data.py` (bougies MT5 réelles M15/H1, cache 15s, fallback sim en démo) + sécurité bot_runner: jamais d'exécution live si source != mt5.
- **`services/decision_engine.py`** : scoring 0-100 sur 6 facteurs (Tendance M15+H1 25pts, Momentum RSI+MACD 15, Structure cassures/S&R 20, Volatilité ATR 15, Spread & session 15, Régime 10). Seuil configurable `min_confidence_score` (70). Explications françaises par facteur. Throttle 1 éval/min/symbole. `latest_evals` en mémoire + persistance signals_col (EXECUTE + presque-signaux). NO_SIGNAL si pas de direction EMA; REJECT si blocking (volatilité extrême, spread anormal, marché fermé) ou score < seuil.
- **Sélection des marchés** : `GET/POST /api/market/symbols` (catalogue MT5 réel: 94 instruments RoboForex catégorisés forex/crypto/métaux/indices/énergie/actions via `categorize_symbol`), max 10 sélectionnés, `POST /api/market/single-mode` (marché unique à chaud). `effective_symbols(cfg)` = seule source des marchés analysés.
- **Sizing pro** : lots calculés via specs broker réelles (`get_symbol_info`: contract_size, volume_min/step/max), SL = max(1.5×ATR réel, 0.05% prix), TP = RR×SL, hard cap 1 lot.
- **Garde-fous live/sim séparés** (fix critique: les refs sim 9442 empoisonnaient les guards vs equity réelle 532 → faux drawdown 94%): BotState.daily_start_live / week_start_equity_live / peak_equity_live, initialisés au 1er tick connecté.
- **mt5_broker**: get_candles (copy_rates_from_pos M1-D1), get_symbol_info, list_symbols, categorize_symbol.
- **Frontend**: `markets.tsx` (recherche, chips catégories, toggles, mode unique, seuil) + `signals.tsx` (score barre+seuil, badge EXÉCUTÉ/REJETÉ/PAS DE SIGNAL, 6 facteurs dépliables, refresh 15s) + liens dans "Plus". Fix bug risk.tsx (apiPost manquant → bouton Enregistrer plantait) + nouveaux champs garde-fous exposés.
- **Endpoints système**: POST /api/system/restart (PowerShell détaché, amélioré avec log C:\trading-bot\restart.log — 1ère version n'a pas fonctionné, à retester), POST /api/mt5/test-trade (micro-trade 0.01 ouvre+ferme 3s, VALIDÉ en réel ticket 2030179949), boucle auto-reconnect MT5 60s (VALIDÉE: reconnecte seul après restart).
- **VPS scripts**: setup_autologon.ps1 (AutoAdminLogon + tâche restart-on-crash 99×1min + tunnel auto).
- **Tests**: 65 pytest (decision engine 9, live_account, backend api). VÉRIFIÉ EN PRODUCTION: bot a ouvert 3 positions réelles (EURUSD/GBPUSD/XAUUSD SELL 0.01 lot, score 71/70, SL/TP ATR posés), BTCUSD rejeté 62<70, US100 bloqué par la sécurité anti-sim (bougies indisponibles → src=sim).
- État VPS: mode real, bot ACTIF, live_mt5 ON, MT5 connecté auto, balance ~532 USD.
- ⚠️ Limites connues: US100/indices sans bougies MT5 (vérifier nom symbole RoboForex), restart à distance v1 défaillant (v2 logguée à tester), trades_today compté en interne (pas les manuels), conversion devise profit non-USD approximative.

## Itération v7 (current) — REFONTE "MT5 = source de vérité" ✅ DÉPLOYÉE SUR VPS
- **Nouveau service `services/live_account.py`** : résolveur central. `is_live()` = mode real + MT5 connecté → balance/equity/marge/marge libre/P&L flottant depuis MT5 ; positions = MT5 (avec origin bot/manual depuis le comment) ; trades = historique deals MT5 groupés par position_id (inclut trades manuels, choix utilisateur) ; `period_pnl` (jour/7j/30j). Cache 10s sur le daily P&L.
- **`/api/bot/state` unifié** = `_build_snapshot_data()` partagé avec le WS (state résolu + positions + mt5_status + mt5_account). state inclut: source (mt5/sim), margin, free_margin, account_currency, leverage, daily_start_balance précis (balance - realized_today).
- **`/api/positions/open`** : MT5 en live, sinon sim filtré par mode (bug "positions fantômes" corrigé). `/api/positions/{id}/close` ferme via MT5 si live.
- **`/api/trades`, `/trades/metrics`, `/trades/equity-curve`** : source MT5 en réel. Nouvelles métriques: pnl_today/week/month, avg_win, avg_loss, win_loss_ratio, source.
- **`bot_runner.py` sécurité** : en réel exige real_unlocked + live_mt5_trading_enabled + MT5 connecté (sinon pause explicite, AUCUNE position interne) ; _manage_positions ne simule QUE le mode demo, sync les positions MT5 (ticket disparu → CLOSED local, pas de mutation balance), archive les positions "real" internes legacy ; sizing sur la VRAIE balance MT5 ; garde-fous : perte hebdo (weekly_loss_limit_pct=10), drawdown max vs peak (max_total_drawdown_pct=20), spread anormal (max_spread_pct=0.1), reset hebdo + peak_equity ; kill switch ferme AUSSI les positions MT5.
- **Dashboard** : badge LIVE MT5/SIMULATION, devise du compte, Marge libre, tuiles P&L jour/7j/30j, métriques Ratio G/P, chip MANUEL sur les positions manuelles.
- **Tests** : 56 pytest (`/app/backend/tests/`) ciblant le backend LOCAL uniquement (conftest → localhost:8001, ne JAMAIS pointer les tests sur le VPS live). Vérifié e2e sur le VPS : source=mt5, balance 532.60 USD, daily_pnl +32.60, 2 trades manuels XAUUSD dans l'historique, metrics OK, dashboard screenshot OK.
- `auto_update.ps1` corrigé (tâche planifiée au lieu du Service).
- ⚠️ En attente du prochain déploiement (déjà dans le code sandbox, PAS encore sur VPS) : daily_start_balance précis en live (% jour exact).

## Historique v6
- Reset mot de passe admin (script Base64 `reset_password.ps1`) : admin@trading.bot / Trading2025!
- Fix EXPO_PUBLIC_BACKEND_URL (fork l'avait remis sur le sandbox) → tunnel VPS
- Fix IPC timeout -10005 : mauvais chemin terminal (vanilla vs RoboForex), réparé à distance via API ; trim espaces/guillemets ; path/password préservés au re-save ; formulaire non écrasé par le polling
- Suppression verrous mode réel (validation paper + phrase de confirmation) à la demande de l'utilisateur ; bouton "Réel" bascule en 1 tap (phrase envoyée en arrière-plan pour compat)

## Versions antérieures (v1-v5)
- Moteur simulateur paper trading, stratégies, kill switch, audit logs, WS temps réel
- Auth JWT (bcrypt/passlib), AES pour credentials MT5
- Journal IA (Claude Sonnet 4.5, clé Emergent, SSE), Régime de marché (trend/range/volatile + adaptation)
- Tunnel Cloudflare, migration Service → Tâche planifiée (fix IPC), scripts VPS (`/app/scripts/vps_windows/`)

## État actuel VPS
- mode=real, real_unlocked=true, bot DÉSACTIVÉ, live_mt5_trading_enabled=FALSE
- MT5 connecté (native), 532.60 USD
- Pour trader réel : activer toggle "Trading live MT5" (écran Risque) + bouton ON

## Backlog priorisé
- P1 : activer live_mt5_trading_enabled + micro-trade test bot (0.01 lot) end-to-end
- P1 : auto-reconnexion MT5 au démarrage du backend (actuellement reconnexion manuelle après restart VPS)
- P1 : AutoLogon Windows (bot autonome après reboot VPS)
- P2 : endpoint /api/system/restart (redémarrage tâche à distance, détaché)
- P2 : tunnel Cloudflare nommé (URL fixe — quick tunnel éphémère actuellement)
- P2 : écran Risque : exposer les nouveaux garde-fous (weekly/max DD/spread) + explications débutant
- P2 : split server.py en routers (auth, mt5, bot, trades, journal)
- P3 : backtests avancés/optimisation, builds APK/Web, label 'real_no_mt5' UI, pin bcrypt<4
