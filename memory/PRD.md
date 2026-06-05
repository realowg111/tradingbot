# Trading Bot — PRD

## Vision
Console mobile professionnelle (Expo) + backend FastAPI 24/7 pour bot de trading automatisé multi-marchés (Forex/CFD via MT5 — initialement simulé), avec validation manuelle pour le passage en mode réel.

## Architecture
- **Frontend** : Expo Router (mobile + web), JWT in expo-secure-store, polling 3s pour temps réel
- **Backend** : FastAPI + Motor (MongoDB async), JWT bcrypt, AES-256-GCM pour credentials MT5
- **Bot Engine** : asyncio task loop (2s tick) — simulateur de marché interne (mock MT5) avec random walk + spikes
- **Marchés simulés** : EURUSD, GBPUSD, XAUUSD, US100, BTCUSD (Forex + CFD)
- **VPS** : scripts d'installation Ubuntu/Debian (systemd + nginx + UFW + fail2ban) dans `/app/scripts/vps/`

## Modules implémentés
1. **Auth** : register/login JWT, admin seedé, AES pour MT5 creds
2. **Bot Control** : ON/OFF, Kill Switch (ferme toutes positions), reset paper
3. **Mode Demo/Réel** : validation manuelle obligatoire (phrase + 7j paper + 10 trades + winrate ≥ 40%)
4. **Stratégies** : RSI, EMA/MACD, Bollinger, Multi-indicateurs (vote pondéré)
5. **Risk Manager** : SL/TP, position sizing, daily drawdown, max trades/jour, max positions, volatility pause
6. **Trades & Métriques** : winrate, profit factor, expectancy, Sharpe, max drawdown, equity curve
7. **Audit Logs** : SIGNAL/TRADE/RISK/SYSTEM/ERROR, export CSV/JSON
8. **Cost Tracker** : VPS/API/data/maintenance, calcul mensualisé, P&L net
9. **Backtesting** : sur ticks synthétiques, frais + slippage
10. **MT5** : credentials chiffrés AES-256, UI dédiée (réel activable après validation)

## Sécurité
- JWT signé HS256
- bcrypt pour passwords
- AES-256-GCM pour MT5 credentials (nonce + ciphertext base64 en BDD)
- Tokens en expo-secure-store côté client (Keychain iOS / EncryptedSharedPreferences Android)
- CORS configuré
- Kill Switch d'urgence + validation manuelle obligatoire pour le mode réel

## Roadmap (post-MVP)
- Connecteur MT5 réel (via bridge Windows ou Wine)
- WebSockets pour streaming temps réel (au lieu de polling)
- IA d'optimisation paramétrique (genetic algorithm)
- Détection de tendance via ML léger
- Multi-utilisateurs avec isolation des bots
- Notifications push (sur demande)
