# Trading Bot — PRD (v3)

## Itération v3 (current)
- **Bugfix critique** : `bot_runner._step()` re-fetchait l'état après mutations → daily_reset en boucle infinie. Fixed.
- **Validation paper trading 100% configurable** : `paper_validation_enabled` (bool), `paper_validation_days`, `paper_validation_min_trades`, `paper_validation_min_winrate`. Désactivable complètement.
- **Live MT5 trading toggle** : `live_mt5_trading_enabled`. Quand True + mode=real + MT5 connecté, le bot place les ordres directement via `mt5_connector.place_order()`. Les positions sont visibles en temps réel dans le terminal MT5 de l'utilisateur.
- **MT5 trading methods** : `place_order(symbol, side, volume, sl, tp)` et `close_position(ticket)` ajoutés (natif Windows + bridge).
- **Page Santé du serveur** : `/api/system/health` (CPU, RAM, disque, uptime, services MongoDB/bot/MT5/WS) + nouvelle screen `/system` avec gauges colorées.
- **Auto-update endpoint** : `/api/system/update` fait git pull + audit log (admin only). Script Windows `auto_update.ps1` pour Scheduled Task quotidien + rollback automatique si health check fail.
- **Sécurité** : credentials hardcodés retirés de l'écran login.

## Architecture
- Frontend : Expo Router, JWT secure storage, WebSocket live + polling fallback
- Backend : FastAPI + Motor MongoDB, JWT bcrypt, AES-256-GCM, asyncio bot loop
- Trading : interne (simulator) OU MT5 natif Windows OU MT5 bridge (agent Windows)
- VPS Linux : `/app/scripts/vps/install.sh`
- VPS Windows tout-en-un : `/app/scripts/vps_windows/install.ps1` + `auto_update.ps1`

## Tests
- **34/34 passing** (regression + nouveaux)

## Roadmap
- Splitter `server.py` en routers
- Notifications push (sur demande)
- IA optimisation paramétrique
- Marketplace stratégies
