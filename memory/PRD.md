# Trading Bot — PRD (v5)

## Itération v5 (current)
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
