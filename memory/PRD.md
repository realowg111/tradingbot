# Trading Bot — PRD (v2)

## Vision
Console fintech mobile + backend FastAPI 24/7 pour bot de trading automatisé multi-marchés (Forex/CFD via MT5), avec live WebSocket, design pro et architecture MT5 pluggable.

## Architecture
- **Frontend** : Expo Router (mobile + web), JWT in expo-secure-store, **WebSocket live data** avec fallback polling
- **Backend** : FastAPI + Motor (MongoDB async), JWT bcrypt, AES-256-GCM, **WS broadcast 1Hz**
- **Bot Engine** : asyncio task loop (2s tick) — simulateur de marché interne + connector MT5 pluggable
- **MT5 Real** : `services/mt5_broker.py` — utilise lib `MetaTrader5` (Windows) OU bridge HTTP (agent Windows + backend Linux). Auto-reconnexion 30s.
- **Marchés simulés** : EURUSD, GBPUSD, XAUUSD, US100, BTCUSD
- **VPS** : scripts d'installation Ubuntu/Debian + agent MT5 Windows dans `/app/scripts/`

## Endpoints v2 ajoutés
- `GET /api/mt5/status` — état connecteur + compte live
- `POST /api/mt5/connect` — tentative connexion réelle MT5
- `POST /api/mt5/disconnect` — déconnexion
- `GET /api/mt5/live` — snapshot live (account + positions)
- `WS /api/ws?token=JWT` — broadcast snapshot toutes les 1s : state + positions + prices + mt5_status

## UI refonte
- **Hero card sombre** (primary color) avec équity géante + bouton ON/OFF intégré (gros bouton power)
- **Header sticky** avec 3 pills (mode démo/réel, bot actif/arrêté, MT5 connecté/simulé) + indicateur LIVE WS
- **Sparkline équity** en miniature dans le hero
- **Stat tiles** avec icônes colorées (P&L jour, winrate, trades)
- **Positions card** avec barre verticale colorée (vert=BUY, rouge=SELL)
- **Metrics grid** sur 2 lignes (winrate, profit factor, sharpe, drawdown, expectancy, W/L)
- **Markets card** avec live dots
- **Toast notifications** pour événements (bot ON/OFF, MT5 connect, kill switch, etc.)
- **MT5 screen** redesigné : status card avec actions Connect/Disconnect + grid live (balance, equity, margin, profit) + guide bridge

## Sécurité (préservée)
- JWT signé HS256, expo-secure-store
- bcrypt passwords + AES-256-GCM credentials MT5
- WS auth via JWT en query param (à durcir avec header sur prod)
- Mode trade-only, jamais de retraits
- Kill Switch d'urgence + validation manuelle Demo→Réel

## Tests
- **Backend** : 34/34 passing (27 regression + 7 nouveaux MT5/WS)
- **Frontend** : DOM élements présents, lint OK, polling fallback fonctionnel

## Roadmap future
- Splitter `server.py` (792 lignes) en routers (auth, bot, trades, mt5, ws)
- Tests E2E Playwright pour l'UI mobile
- Notifications push (Emergent-managed) sur événements bot critiques
- IA d'optimisation génétique des paramètres
- Smart business : Marketplace de stratégies (revenus récurrents)
