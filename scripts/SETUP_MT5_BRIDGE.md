# Guide de configuration - Agent Passerelle MT5

> **Objectif**: Permettre à un backend Linux d'accéder à MT5 via une passerelle HTTP sur Windows.

---

## Architecture

```
┌─────────────────────────┐
│  Backend (Linux)        │
│  FastAPI sur port 8001  │
│  MT5_BRIDGE_URL=...     │
└────────────┬────────────┘
             │ HTTPS
             ▼
┌─────────────────────────────────────────┐
│  Agent Passerelle MT5 (Windows)         │
│  Flask sur port 5555                    │
│  /health, /connect, /account, /order... │
└────────────┬────────────────────────────┘
             │
             ▼
      ┌──────────────┐
      │ MT5 Terminal │
      │ (IC Markets) │
      └──────────────┘
```

---

## Installation sur Windows (VPS ou PC)

### 1. Prérequis

- **Python 3.11+** installé
- **MetaTrader5** terminal en cours d'exécution (brokers: IC Markets, etc.)
- Droits d'administration sur le PC/VPS

### 2. Installation de la librairie MetaTrader5

```powershell
pip install MetaTrader5 flask flask-cors
```

### 3. Lancer l'Agent Passerelle

```powershell
cd C:\path\to\tradingbot
python scripts/mt5_agent.py
```

Vous devriez voir:
```
🚀 Agent Passerelle MT5 démarrage sur 0.0.0.0:5555
ℹ️  Assurez-vous que le terminal MT5 est lancé avant la connexion!
```

### 4. Configuration avec Ngrok ou tunnel personnalisé (optionnel)

Pour exposer le port 5555 sur internet :

```powershell
# Via Ngrok (gratuit)
npm install -g ngrok
ngrok http 5555

# Ou via Cloudflare Tunnel
cloudfared tunnel run mt5-bridge --url localhost:5555
```

Notez l'URL publique : `https://xxxx.ngrok.io` ou similaire.

---

## Configuration du Backend (Linux)

### Ajouter au `.env` du backend :

```env
# Option 1 : Passerelle locale (même réseau)
MT5_BRIDGE_URL=http://192.168.1.50:5555

# Option 2 : Passerelle via tunnel internet
MT5_BRIDGE_URL=https://xxxx.ngrok.io
```

### Redémarrer le backend :

```bash
cd backend
python -m uvicorn server:app --reload
```

---

## Test de la connexion

### Via l'API du Backend

```bash
# Connecter l'agent au MT5
curl -X POST http://localhost:8001/api/mt5/connect \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "login": "123456",
    "password": "YourPassword",
    "server": "ICMarkets-Demo"
  }'
```

### Vérifier la santé de la passerelle

```bash
curl http://192.168.1.50:5555/health
```

Réponse attendue :
```json
{
  "connected": true,
  "login": "123456",
  "server": "ICMarkets-Demo",
  "last_error": null,
  "last_heartbeat": "2026-06-16T14:30:00Z"
}
```

---

## Endpoints de la Passerelle

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/health` | GET | Vérifier l'état de connexion |
| `/connect` | POST | Établir la connexion MT5 |
| `/disconnect` | POST | Fermer la connexion |
| `/account` | GET | Récupérer infos du compte |
| `/positions` | GET | Lister les positions ouvertes |
| `/price/{symbol}` | GET | Récupérer bid/ask |
| `/history` | GET | Historique des deals |
| `/order` | POST | Placer un ordre |
| `/close` | POST | Fermer une position |
| `/candles/{symbol}` | GET | Récupérer les bougies OHLC |

---

## Déploiement en Production (Windows Service)

### Via NSSM (Non-Sucking Service Manager)

```powershell
# Télécharger NSSM: https://nssm.cc/download
# Ou via chocolatey:
choco install nssm

# Installer le service
nssm install MT5Agent "C:\Python311\python.exe" "C:\tradingbot\scripts\mt5_agent.py"
nssm set MT5Agent AppDirectory "C:\tradingbot"
nssm set MT5Agent AppEnvironmentExtra "MT5_AGENT_HOST=0.0.0.0^MT5_AGENT_PORT=5555"

# Démarrer
Start-Service MT5Agent

# Vérifier le statut
Get-Service MT5Agent
```

### Auto-démarrage avec Task Scheduler

Voir: `scripts/setup_mt5_autostart.ps1`

---

## Troubleshooting

### ❌ "MetaTrader5 lib not available"

```powershell
# Vérifier l'installation
python -c "import MetaTrader5; print('OK')"

# Réinstaller si nécessaire
pip uninstall MetaTrader5
pip install MetaTrader5
```

### ❌ "terminal not found"

- Vérifier que le terminal MT5 est **ouvert** (pas minimisé)
- Si sur un VPS en Session 0, configurer AutoLogon ou lancer le terminal en session interactive

### ❌ "IPC timeout"

- Vérifier que MT5 tourne dans **la même session Windows** que Python
- Sur VPS: utiliser `scripts/setup_autologon.ps1` pour AutoLogon

### ❌ Connexion refusée du backend vers la passerelle

```bash
# Tester depuis le backend
curl http://<BRIDGE_IP>:5555/health

# Vérifier le firewall Windows
netsh advfirewall firewall add rule name="MT5Agent" dir=in action=allow protocol=tcp localport=5555
```

---

## Fallback Mode (Simulateur)

Si la passerelle n'est pas disponible, le backend bascule automatiquement au **simulateur interne** :

- Mode: `paper_engine`
- Spread/slippage réalistes
- Parfait pour le développement/tests

```python
# Backend détecte automatiquement
if mt5_connector.connected:  # Via passerelle
    # Utiliser MT5 réel
else:
    # Fallback au simulateur
```

---

## Monitoring (UptimeRobot optionnel)

Ajouter un monitor HTTP sur l'endpoint `/health` :

```
URL: http://YOUR_PUBLIC_IP:5555/health
Interval: 5 min
Alert si status != 200
```
