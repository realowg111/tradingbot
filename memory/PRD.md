# Trading Bot — PRD (v7)

## Problème original
Bot de trading 100% automatisé 24/7 connecté à MetaTrader 5 (Forex/CFD), gestion du risque stricte, mode paper trading, journal IA, adaptation au régime de marché, dashboard fintech pro. Backend déployé sur VPS Windows (lib MT5 = Windows only), frontend Expo React Native.

## Architecture
- **Frontend** : Expo (preview Emergent) → `EXPO_PUBLIC_BACKEND_URL` = tunnel Cloudflare du VPS (`https://cult-spa-projectors-exceptional.trycloudflare.com`)
- **Backend VPS Windows** : `C:\trading-bot`, venv, uvicorn (Tâche planifiée interactive "TradingBotBackend"), MongoDB local, MT5 natif (RoboForex `C:\Program Files\RoboForex MT5 Terminal\terminal64.exe`)
- **Déploiement** : code → "Save to GitHub" (repo realowg111/tradingbot) → `POST /api/system/update` (git pull à distance) → restart tâche par l'utilisateur (PAS de hot reload sur le VPS, et un process python zombie peut survivre → utiliser `Get-Process python* | Stop-Process -Force` avant relance)
- **Compte réel** : RoboForex-Pro, login 68323992, levier 1:1000, ~532 USD

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
