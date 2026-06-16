# Trading Bot MT5 + Telegram Copy Trading — Context Transfer Document

> **Usage**: Paste this entire document at the start of a conversation with ChatGPT, Claude, Copilot, or any LLM to give it 100% of the project context needed to help you continue development.

> **Last updated**: June 16, 2026
> **Owner**: realowg111
> **GitHub repo**: https://github.com/realowg111/tradingbot

---

## 1. Project Overview

A fully automated 24/7 trading bot for Forex, indices, gold, and crypto via MetaTrader 5 (MT5).
Combines two independent trading sources running in parallel:

1. **Internal multi-factor decision engine** — scans markets, scores signals 0–100, executes trades on MT5
2. **Telegram signal copier** — auto-copies signals from the channel "RentaTrade Z VIP" using Claude Sonnet 4.5 for parsing, then executes on MT5 with risk management

Frontend: Expo React Native app (mobile + web).
Backend: FastAPI on a Windows VPS (because MT5 Python lib only runs on Windows).
DB: MongoDB on the VPS.

---

## 2. Architecture

```
┌────────────────────────────┐
│  Frontend (Expo / React)   │  ← Mobile + Web (currently served via Emergent preview)
│  - Dashboard, Bot, Risk    │  EXPO_PUBLIC_BACKEND_URL → user-configurable in /settings
│  - Telegram copy page      │
│  - Settings (backend URL)  │
└──────────────┬─────────────┘
               │ HTTPS via Cloudflare Tunnel (quick tunnel, URL changes on restart)
               ▼
┌────────────────────────────────────────────────┐
│  BACKEND — Windows VPS                          │
│  C:\trading-bot                                 │
│                                                 │
│  FastAPI + uvicorn (port 8001) ── /api/*       │
│   ├── decision_engine.py  (multi-factor scoring)│
│   ├── bot_runner.py       (main trading loop)   │
│   ├── mt5_broker.py       (MT5 connection)      │
│   ├── live_account.py     (MT5 state sync)      │
│   ├── telegram_listener.py (Telethon)           │
│   ├── signal_parser.py    (Claude Sonnet 4.5)   │
│   └── telegram_copy_trader.py (risk + exec)     │
│                                                 │
│  MongoDB (local) - users, trades, positions,    │
│       signals, telegram_signals, telegram_state │
│                                                 │
│  MetaTrader 5 terminal (interactive session)    │
│       Broker: IC Markets                        │
└─────────────────────────────────────────────────┘
```

### Key flows

- **Bot trading flow**: `bot_runner.py` loops every 5s → for each whitelisted symbol → `decision_engine.score()` → if score ≥ threshold + risk OK → `mt5_broker.place_order()`.
- **Telegram copy flow**: `telegram_listener.py` → new Telegram message → `telegram_copy_trader.process_message()` → `signal_parser.parse_signal()` (Claude) → risk validation → `mt5_broker.place_order()` (50/50 split for TP1 + runner).
- **MT5 reconnect flow**: heartbeat every 10s in `mt5_broker._reconnect_loop`. If `terminal_info()` or `account_info()` returns None → shutdown + reconnect with stored credentials.

---

## 3. Tech Stack

**Frontend**
- Expo SDK (managed)
- expo-router (file-based routing under `/app/frontend/app/`)
- React Native (TouchableOpacity, View, Text, StyleSheet)
- AsyncStorage / SecureStore for tokens + backend URL override
- WebSocket for live updates (1s broadcast)

**Backend**
- Python 3.11 + FastAPI + uvicorn (--reload)
- motor (async MongoDB)
- MetaTrader5 lib (Windows-only)
- Telethon 1.44 (Telegram MTProto)
- emergentintegrations (Claude Sonnet 4.5 via Emergent LLM Key)
- httpx, pydantic, cryptography (Fernet for credentials encryption)

**Infrastructure**
- Windows VPS (the user owns it, IC Markets MT5 broker)
- AutoLogon Windows + Scheduled Tasks for resilience
- Cloudflare Tunnel (quick tunnel mode, URL changes per restart)
- GitHub repo with auto-update PowerShell script (`auto_update.ps1`)

---

## 4. Repository Structure

```
/app
├── backend/
│   ├── server.py                # main FastAPI app (~1450 lines - REFACTOR INTO ROUTERS PENDING)
│   ├── database.py              # MongoDB collections + indexes
│   ├── models.py                # Pydantic models
│   ├── security.py              # JWT + bcrypt + Fernet
│   ├── requirements.txt
│   ├── .env                     # MONGO_URL, JWT_SECRET, EMERGENT_LLM_KEY, TELEGRAM_*
│   └── services/
│       ├── decision_engine.py   # multi-factor scoring (trend, momentum, vol, regime)
│       ├── bot_runner.py        # async trading loop
│       ├── mt5_broker.py        # MT5 native + bridge connector
│       ├── live_account.py      # source-of-truth for MT5 account state
│       ├── market_data.py       # OHLC fetch
│       ├── market_regime.py     # ADX-based regime classification
│       ├── strategies.py        # signal generators
│       ├── paper_engine.py      # simulator fallback
│       ├── metrics.py           # winrate, profit factor, etc.
│       ├── ai_journal.py        # Claude-powered trade journal
│       ├── ws_hub.py            # WebSocket broadcast
│       ├── telegram_listener.py # Telethon manager (SMS login flow)
│       ├── signal_parser.py     # Claude Sonnet 4.5 + regex fallback
│       └── telegram_copy_trader.py  # validation, sizing, multi-TP exec
│
├── frontend/
│   ├── app/                     # expo-router screens
│   │   ├── (tabs)/
│   │   │   ├── dashboard.tsx    # equity, P&L, positions, MT5 reconnect banner
│   │   │   ├── bot.tsx          # bot ON/OFF, strategy toggle
│   │   │   ├── history.tsx
│   │   │   ├── stats.tsx
│   │   │   └── more.tsx         # menu to all extra screens
│   │   ├── settings.tsx         # backend URL override (NEW)
│   │   ├── telegram.tsx         # Telegram copy config + signals feed (NEW)
│   │   ├── markets.tsx          # whitelist symbols
│   │   ├── signals.tsx          # bot's scored signals
│   │   ├── risk.tsx             # risk config (DD, sizing)
│   │   ├── mt5.tsx              # MT5 connection settings
│   │   ├── login.tsx
│   │   └── _layout.tsx
│   └── src/
│       ├── api/client.ts        # apiGet/apiPost with dynamic baseUrl (NEW)
│       ├── hooks/useLiveData.ts # WebSocket + polling fallback
│       ├── components/ui.tsx    # Card, Button, Sparkline, etc.
│       ├── theme.ts             # colors, spacing, radius
│       └── utils/storage/       # AsyncStorage wrapper
│
└── scripts/vps_windows/         # PowerShell automation
    ├── install.ps1              # initial bot install
    ├── auto_update.ps1          # git pull + pip install + restart
    ├── setup_autologon.ps1      # Windows AutoLogon
    ├── setup_cloudflare_tunnel.ps1
    ├── setup_telegram.ps1       # adds Telegram env vars
    ├── setup_mt5_autostart.ps1  # MT5 at boot + watchdog (NEW)
    └── get_tunnel_url.ps1       # prints current Cloudflare URL (NEW)
```

---

## 5. Features Built (timeline)

✅ **Authentication** (JWT, bcrypt, admin user seeded as `admin@trading.bot` / `Trading2025!`)
✅ **Paper trading simulator** (5 symbols, realistic spread/slippage)
✅ **MT5 native connector** with auto-reconnect (heartbeat 10s, force reconnect endpoint)
✅ **Risk management** (max DD, daily loss, per-trade % risk, kill switch)
✅ **Multi-factor decision engine** (0-100 scoring across trend/momentum/vol/regime)
✅ **Market regime detection** (ADX-based: trending/ranging/volatile)
✅ **Manual market whitelist** (per-symbol toggle + "single market" mode)
✅ **Signal history page** with scoring breakdown + reasons
✅ **AI Journal** (Claude Sonnet 4.5 critiques recent trades)
✅ **Live MT5 state sync** (equity, balance, margin, positions, P&L — single source of truth)
✅ **Windows AutoLogon + Scheduled Task** for full VPS autonomy
✅ **MT5 auto-start at boot** with watchdog (NEW)
✅ **Cloudflare Tunnel** for HTTPS access to the VPS backend
✅ **Telegram copy trading** (RentaTrade Z VIP):
  - Telethon listener with SMS login
  - Claude Sonnet 4.5 parser handles all formats including "TP OUVERT" (runner)
  - Shadow mode (default ON) → parses + displays without executing
  - 50/50 multi-TP split (TP1 close + runner with trailing logic)
  - Anti-duplicate, drift guard (max 0.5%), spread guard
  - All trades tagged `source: telegram_rentatrade`
✅ **Dashboard MT5 reconnect banner** (big orange clickable banner when disconnected)
✅ **Settings page** to override backend URL (so the app can point to user's VPS vs Emergent sandbox)

---

## 6. Database Schema (MongoDB)

| Collection | Key fields |
|---|---|
| `users` | email, password_hash, is_admin, mt5_credentials (Fernet encrypted) |
| `bot_state` | is_active, mode (demo/real), real_unlocked, live_mt5_trading_enabled, kill_switch, paused_reason, balance, equity, daily_pnl |
| `bot_config` | risk.risk_per_trade_pct, risk.max_spread_pct, risk.daily_loss_limit_pct, strategies enabled, symbols whitelist |
| `positions` | symbol, side, entry_price, sl, tp, mode, mt5_ticket, source (sim/mt5/telegram_rentatrade), telegram_runner |
| `trades` | closed positions with pnl, opened_at, closed_at |
| `signals` | bot signals with score, reasons, executed |
| `telegram_signals` | raw_text, parsed, status (received/parsed/shadow/executed/rejected), mt5_orders |
| `telegram_state` | enabled, shadow_mode, channels, symbols_whitelist, split_legs, max_entry_drift_pct |
| `audit_log` | level, event, details, ts |

---

## 7. Key API Endpoints

```
POST /api/auth/login                     → JWT login
GET  /api/health                         → status + platform info

# Bot
GET  /api/bot/state                      → full state snapshot
POST /api/bot/toggle                     → ON/OFF
POST /api/bot/kill-switch                → emergency close all
GET  /api/bot/signals                    → recent scored signals

# Positions & trades
GET  /api/positions/open
GET  /api/trades/metrics
GET  /api/trades/equity-curve

# MT5
GET  /api/mt5/status
POST /api/mt5/connect                    → save creds + connect
POST /api/mt5/reconnect                  → force reconnect (NEW)
POST /api/mt5/test-trade                 → 0.01 lot test

# Markets
GET  /api/market/symbols
POST /api/market/symbols/toggle

# Risk
GET  /api/risk/config
POST /api/risk/config

# Telegram (all admin-only)
GET  /api/telegram/status                → Telethon status + config
POST /api/telegram/start-login           → request SMS code
POST /api/telegram/submit-code           → submit code received
POST /api/telegram/submit-password       → 2FA password
GET  /api/telegram/config
POST /api/telegram/config                → enable, shadow_mode, channels, whitelist
GET  /api/telegram/signals               → paginated signals history
POST /api/telegram/test-parse            → test the Claude parser

# System
POST /api/system/update                  → trigger auto_update.ps1 on VPS
POST /api/system/restart                 → restart backend

# WebSocket
GET  /api/ws?token=...                   → 1s snapshot broadcast
```

---

## 8. Environment Variables

### Backend `.env` (VPS)
```env
MONGO_URL=mongodb://localhost:27017
DB_NAME=trading_bot

JWT_SECRET=<long random>
JWT_ALGORITHM=HS256
JWT_EXPIRES_HOURS=168

FERNET_KEY=<base64 32 bytes>            # for MT5 credentials encryption

ADMIN_EMAIL=admin@trading.bot
ADMIN_PASSWORD=Trading2025!

EMERGENT_LLM_KEY=sk-emergent-XXXX       # Claude Sonnet 4.5 (Emergent universal key)

# Telegram (RentaTrade copy trading)
TELEGRAM_API_ID=30879528
TELEGRAM_API_HASH=5674826007957132ee773fa767e623f2
TELEGRAM_PHONE=+33769008392
TELEGRAM_CHANNEL=RentaTrade Z VIP
TELEGRAM_SESSION_PATH=C:\trading-bot\backend\data\telegram.session
```

### Frontend `.env`
```env
EXPO_PUBLIC_BACKEND_URL=https://autotrader-hub-28.preview.emergentagent.com
# (User can override at runtime via Settings page to point to their VPS Cloudflare URL)
```

---

## 9. Important Behaviors / Quirks

- **Local dev (Linux sandbox) cannot run MT5** — falls back to paper simulator. Real trading only on VPS.
- **Telegram session file** (`telegram.session`) is persisted on disk. Login flow is SMS-based, done ONCE.
- **Cloudflare quick tunnel** URL changes on each restart. Two solutions:
  1. Run `scripts/vps_windows/get_tunnel_url.ps1` → paste in Settings page
  2. Migrate to Named Tunnel (requires domain ~€2/year)
- **mt5_broker reconnect loop** runs every 10s, force-shutdowns the lib before reconnect to clear stale handles.
- **Shadow mode** for Telegram is enabled by default — flip it OFF in the app to start executing real Telegram trades.
- **Split 50/50 multi-TP** means each Telegram signal opens 2 MT5 positions (one with TP1, one runner with TP2 or 3x distance if "OUVERT").
- **The bot also takes the user's manual MT5 trades into account** in the dashboard stats (comments not starting with "Bot" are tagged as manual).
- **Backend uses single global MT5 connection** — currently NOT multi-tenant. Future work needed if exposing to other users.

---

## 10. Pending / Future Tasks

🟡 **In progress / pending**
- [ ] Refactor `server.py` (1450 lines) into routers: `auth.py`, `mt5.py`, `bot.py`, `telegram.py`, `journal.py`
- [ ] Migrate from Cloudflare quick tunnel to Named Tunnel (requires domain)
- [ ] (Optional) UptimeRobot monitoring for VPS uptime alerts
- [ ] (Optional) Multi-tenant refactor if opening to other users

🟢 **Future ideas**
- "Daily AI Report" in AI Journal (summarize trades + best/worst signals)
- Push notifications when Telegram signal arrives
- Per-channel stats (winrate, profit factor) in Telegram page
- Backtest module with historical replay
- Sharpe ratio + monthly equity heatmap

🔴 **Known caveats**
- If MT5 terminal is closed (not just minimized), the bot cannot trade. The new watchdog (`scripts/vps_windows/setup_mt5_autostart.ps1`) restarts it within 5min.
- If the user closes their Windows RDP session improperly, MT5 may close. They MUST "disconnect" (not "log off").

---

## 11. Test Credentials

```
Email:    admin@trading.bot
Password: Trading2025!
```

(stored in `/app/memory/test_credentials.md`)

---

## 12. How to Continue Development with Another AI

1. **Clone the repo locally**:
   ```bash
   git clone https://github.com/realowg111/tradingbot
   cd tradingbot
   ```

2. **Open in VS Code** (or Cursor / Copilot).

3. **Paste this entire document at the start** of your chat with ChatGPT/Claude/Copilot.

4. **Add this prompt**:
   > "Here's the full context of my trading bot project. I want to continue development. The repo is at https://github.com/realowg111/tradingbot. Read the project structure and help me with X."

5. The AI now has full context to:
   - Suggest improvements
   - Debug issues
   - Add new features
   - Refactor code

---

## 13. Useful Commands Cheat-Sheet

### On the VPS (Windows PowerShell)
```powershell
cd C:\trading-bot
git pull                                                              # get latest code
.\scripts\vps_windows\get_tunnel_url.ps1                              # get current Cloudflare URL
.\scripts\vps_windows\setup_mt5_autostart.ps1                         # MT5 autostart + watchdog
Restart-Service TradingBotBackend                                     # restart backend
Restart-Service TradingBotTunnel                                      # restart Cloudflare tunnel
Get-Content C:\trading-bot\logs\cloudflared.log -Tail 50 -Wait        # tail tunnel logs
Get-Process terminal64                                                # check MT5 running
```

### On the user's machine (frontend dev)
```bash
cd frontend
yarn install
yarn expo start
```

### Backend tests
```bash
cd backend
pytest tests/                # currently 91/91 passing
```

---

## 14. Contact / Repo

- **GitHub**: https://github.com/realowg111/tradingbot
- **Broker**: IC Markets (MT5)
- **VPS**: Windows Server (user-managed)
- **Telegram channel monitored**: RentaTrade Z VIP

---

> 📌 **End of context transfer document. Paste this entire file at the start of a new AI chat to continue development seamlessly.**
