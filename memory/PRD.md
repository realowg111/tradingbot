# Trading Bot — PRD (v6)

## Itération v6 (current) — Déblocage login + reconnexion VPS + fix IPC timeout + suppression verrous mode réel
- **Suppression des verrous de passage en réel** (demande utilisateur explicite) :
  - VPS : `paper_validation_enabled=false` appliqué à distance via POST /api/bot/config-flags.
  - `server.py` : check de la phrase "JE CONFIRME LE PASSAGE EN REEL" supprimé (la phrase reste acceptée/ignorée).
  - `models.py` : `paper_validation_enabled` default → False.
  - `bot.tsx` : modal + saisie de phrase supprimés ; bouton "Réel" bascule en 1 tap (la phrase est envoyée automatiquement en arrière-plan pour compatibilité avec le backend VPS non mis à jour) ; hint texte mis à jour.
  - Testé e2e sur le VPS : passage en RÉEL en 1 clic, badge "RÉEL DÉBLOQUÉ" ✅.
- **État VPS après bascule** : mode=real, real_unlocked=true, bot DÉSACTIVÉ (sécurité post-switch), `live_mt5_trading_enabled=false` → pour trader réellement sur MT5 : activer le toggle dans l'écran Risque + bouton ON.
- **Réinitialisation mot de passe admin VPS** : script infaillible `scripts/vps_windows/reset_password.ps1` (Python encodé Base64). Credentials : `admin@trading.bot` / `Trading2025!` (VPS + sandbox).
- **Fix critique 1** : le fork avait réinitialisé `EXPO_PUBLIC_BACKEND_URL` sur le backend sandbox Linux → cause du "identifiants invalides" ET du bandeau "backend Linux". Restauré vers le tunnel : `https://cult-spa-projectors-exceptional.trycloudflare.com`.
- **Fix critique 2 — IPC timeout (-10005)** : le chemin terminal sauvegardé avait été perdu (POST /mt5/credentials écrasait le path) et l'autodétection choisissait le MAUVAIS terminal (`C:\Program Files\MetaTrader 5` au lieu de `C:\Program Files\RoboForex MT5 Terminal`). Réparé à distance via API (credentials corrigés + connect) → **MT5 CONNECTÉ en natif (compte 68323992, RoboForex-Pro, 500 USD, levier 1:1000)**.
- **Correctifs code (anti-récurrence, testés)** :
  - `models.py` : validators trim espaces/guillemets sur login/server/broker/path (MT5CredentialsIn + MT5PathPatch).
  - `server.py` : POST /mt5/credentials préserve désormais le path existant si non fourni (comme le password).
  - `mt5_broker.py` : message FR actionnable pour l'erreur -10005 IPC timeout ; la boucle de reconnexion réutilise le terminal_path.
  - `mt5.tsx` : le polling 3s n'écrase plus les champs du formulaire (préremplissage unique) ; trim des champs avant envoi.
- ⚠️ Le VPS tourne encore l'ANCIEN code (fonctionne car la DB est corrigée). Les correctifs s'appliqueront au prochain update VPS (Save to GitHub + git pull). Note : `auto_update.ps1` utilise encore `Restart-Service TradingBotBackend` — obsolète depuis la migration en Tâche planifiée, à mettre à jour.
- ⚠️ Tunnel "quick" éphémère : si cloudflared redémarre, l'URL change → mettre à jour `EXPO_PUBLIC_BACKEND_URL`.
- État bot VPS : actif, mode DEMO/paper (10 000 USD virtuel), `real_unlocked: false`. Prochaine étape : passage en live / micro-trade test.

## Itération v5
- **Détection dynamique du régime de marché** + **adaptation automatique** : nouveau module `services/market_regime.py`.
  - 4 régimes détectés par symbole (TREND_UP / TREND_DOWN / RANGE / VOLATILE) à partir de la stddev relative, du slope EMA et du range.
  - Filtrage adaptatif des stratégies : TREND → EMA_MACD+Multi, RANGE → Bollinger+RSI, VOLATILE → Multi (consensus).
  - Sizing adaptatif : risk_per_trade multiplié par 0.5 (VOLATILE), 0.75 (RANGE), 1.0 (TREND).
  - Cache in-memory `regime_store` rafraîchi à chaque tick du bot.
  - Toggle global `adaptive_enabled` dans `BotConfig` (default ON).
- **API** : `GET /api/market/regime` (état par symbole) + `POST /api/bot/adaptive` (toggle).
- **Frontend** : nouvel écran `/regime` accessible depuis "Plus → Régime de marché" — toggle, légende des règles, état par symbole avec badge couleur + confiance + métriques (σ, slope, range), refresh auto 6s + pull-to-refresh.

## Itération v4
- Cloudflare Tunnel pour VPS (`setup_cloudflare_tunnel.ps1`).
- Journal AI (Claude Sonnet 4.5) avec streaming SSE.

## Itération v3
- Bugfix `daily_reset` boucle infinie.
- Validation paper trading configurable.
- Live MT5 trading toggle.
- Page Santé du serveur.
- Auto-update endpoint.

## Architecture
- Frontend : Expo Router, JWT secure storage, WS live + polling fallback
- Backend : FastAPI + Motor MongoDB, JWT bcrypt, AES-256-GCM, asyncio bot loop
- Trading : interne (simulator) OU MT5 natif Windows OU MT5 bridge
- IA : Claude Sonnet 4.5 via Emergent LLM Key (streaming SSE)
- Adaptatif : détection régime + filtrage stratégies + sizing dynamique
- VPS Windows : `install.ps1` + `auto_update.ps1` + `setup_cloudflare_tunnel.ps1`

## Roadmap
- Splitter `server.py` en routers
- Notifications push (sur demande)
- Tunnel Cloudflare nommé (URL fixe)
- Backtest de l'adaptation (comparer adaptive ON vs OFF)
- Marketplace stratégies
