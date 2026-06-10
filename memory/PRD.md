# Trading Bot — PRD (v4)

## Itération v4 (current)
- **Cloudflare Tunnel pour VPS** : Script PowerShell `setup_cloudflare_tunnel.ps1` qui installe `cloudflared.exe` comme service Windows (`TradingBotTunnel`) et expose le backend (port 8001) sur une URL HTTPS publique `*.trycloudflare.com`. Résout définitivement le Mixed Content entre frontend HTTPS et VPS HTTP.
- **Journal AI (Claude Sonnet 4.5)** : Nouvelle feature `/journal` avec analyse intelligente de l'historique de trades.
  - Backend : `services/ai_journal.py` agrège stats (winrate, PF, expectancy, by_symbol, by_strategy) et stream Claude Sonnet 4.5 via Emergent LLM Key + emergentintegrations.
  - API : `GET /api/journal/preview` (stats), `POST /api/journal/analyze` (SSE streaming), `GET /api/journal/reports`, `GET /api/journal/reports/{id}`, `DELETE` (admin).
  - Frontend : écran `/app/journal.tsx` avec sélecteurs période (7j/30j/90j) + mode (Tous/Démo/Réel), aperçu stats en grille, génération IA avec streaming SSE token-par-token, renderer Markdown minimal, historique des rapports cliquables, bouton "Arrêter".
  - Rapport structuré : Synthèse globale → Forces → Faiblesses → Analyse par stratégie/symbole → Recommandations chiffrées → Verdict.

## Itération v3
- Bugfix `bot_runner._step()` daily_reset boucle infinie. Fixed.
- Validation paper trading 100% configurable.
- Live MT5 trading toggle.
- Page Santé du serveur.
- Auto-update endpoint + script Windows.

## Architecture
- Frontend : Expo Router, JWT secure storage, WebSocket live + polling fallback
- Backend : FastAPI + Motor MongoDB, JWT bcrypt, AES-256-GCM, asyncio bot loop
- Trading : interne (simulator) OU MT5 natif Windows OU MT5 bridge
- IA : Claude Sonnet 4.5 via Emergent LLM Key (streaming SSE)
- VPS Windows : `install.ps1` + `auto_update.ps1` + `setup_cloudflare_tunnel.ps1`

## Roadmap
- Splitter `server.py` en routers
- Notifications push (sur demande)
- Tunnel Cloudflare nommé (URL fixe) avec compte CF + domaine
- Marketplace stratégies
