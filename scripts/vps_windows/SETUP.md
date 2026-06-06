# 🪟 Déploiement VPS Windows — Option C (Backend tout-en-un)

Guide complet pour déployer le Trading Bot sur un VPS Windows Server 2022 avec MT5 natif. C'est l'option la plus simple et la plus performante.

## 🎯 Pourquoi cette option ?

- ✅ MT5 lib native Python (~0ms latence)
- ✅ Un seul serveur à gérer
- ✅ Architecture la plus stable
- ✅ Coût : ~9-15€/mois

---

## 📋 ÉTAPE 1 — Louer un VPS Windows

### Provider recommandé : Contabo VPS Windows S

1. Va sur **https://contabo.com/en/vps/windows-vps/**
2. Choisis le plan **VPS S Windows** (~9€/mois — vérifie les promos actuelles)
   - 4 GB RAM
   - 4 vCPU
   - 50 GB NVMe
   - Windows Server 2022 Standard
3. Région recommandée : **Allemagne (EU)** ou **USA East** selon ton broker
4. Compléter la commande, recevoir les credentials RDP par email (~10-30 min)

### Alternatives
- **Hetzner Cloud Windows** (~11€/mois) — meilleure UI, paiement à l'heure
- **OVH SoYouStart Windows** (~15€/mois)
- **AccuWeb Hosting Windows** (~10$/mois)

> ⚠️ **NE PAS** prendre de VPS Windows < 4 GB RAM. MT5 + Python + MongoDB c'est minimum 2-3 Go utilisés.

---

## 📋 ÉTAPE 2 — Première connexion RDP

### Depuis Windows (PC local)
1. Touche `Windows` + taper **"Connexion Bureau à distance"** (mstsc.exe)
2. Coller l'IP du VPS (reçue par email)
3. User : `Administrator`, Password : celui fourni par le provider

### Depuis macOS
1. Installer **Microsoft Remote Desktop** depuis l'App Store (gratuit)
2. Ajouter un PC, IP du VPS, user/password

### Depuis Linux
```bash
sudo apt install remmina remmina-plugin-rdp
remmina
# Nouveau profil RDP, IP, user/password
```

---

## 📋 ÉTAPE 3 — Sécurisation immédiate du VPS (10 min)

**Une fois connecté en RDP, AVANT TOUT le reste :**

### 3.1 Changer le mot de passe Administrator
```
Touche Windows + R → taper "lusrmgr.msc" → Entrée
Clic droit sur "Administrator" → "Set Password..."
Choisir un mot de passe FORT (16+ caractères, mélange majuscules/minuscules/chiffres/symboles)
```

### 3.2 Restreindre l'accès RDP à ton IP publique
Trouve ton IP publique : https://whatismyip.com/

Dans PowerShell **Administrateur** sur le VPS :
```powershell
# Remplace 1.2.3.4 par ton IP publique
New-NetFirewallRule -DisplayName "RDP Restricted to my IP" -Direction Inbound -Protocol TCP -LocalPort 3389 -RemoteAddress 1.2.3.4 -Action Allow
# Désactiver la règle RDP par défaut (qui autorise tout)
Disable-NetFirewallRule -DisplayName "Remote Desktop - User Mode (TCP-In)"
```

> ⚠️ Si ton IP publique change souvent (box internet), utilise un service de DDNS ou laisse RDP ouvert mais avec un mot de passe ULTRA fort + Fail2ban équivalent Windows.

### 3.3 Mises à jour Windows
```powershell
Install-Module PSWindowsUpdate -Force
Get-WindowsUpdate -Install -AcceptAll -AutoReboot
```
(Le VPS va reboot, reconnecter en RDP après ~5 min)

---

## 📋 ÉTAPE 4 — Installation automatisée

### 4.1 Télécharger le code du projet

Sur le VPS, ouvrir PowerShell **Administrateur** :
```powershell
# Créer le dossier
mkdir C:\trading-bot
cd C:\trading-bot
```

Puis copier le code (3 options) :

**Option a — Git** (si tu as un repo)
```powershell
# Installer git rapidement
iex ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'))
choco install -y git
git clone https://github.com/ton-user/ton-repo.git .
```

**Option b — Drag & drop via RDP**
- Sur ton PC local, sélectionner le dossier `/app/backend` du projet
- Copier (Ctrl+C) puis coller dans la session RDP dans `C:\trading-bot\backend`

**Option c — SFTP via WinSCP**
- Installer WinSCP, se connecter en SFTP au VPS, glisser les fichiers

### 4.2 Lancer le script d'installation

Toujours dans PowerShell **Administrateur** sur le VPS :
```powershell
# Permettre l'exécution de scripts
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# Lancer le script
cd C:\trading-bot
.\scripts\vps_windows\install.ps1
```

Le script va installer automatiquement :
- ✅ Chocolatey
- ✅ Python 3.11
- ✅ MongoDB 7 (service auto-start)
- ✅ Git
- ✅ Dépendances Python (FastAPI, motor, pydantic, jose, passlib, **MetaTrader5**)
- ✅ Service Windows **TradingBotBackend** (auto-restart, démarrage auto au boot)
- ✅ Règles pare-feu pour le port 8001
- ✅ `.env` avec clés JWT/AES aléatoires et mot de passe admin random

⏱️ **Durée totale** : ~10-15 minutes.

À la fin, le script affiche :
```
============================================
 IDENTIFIANTS ADMIN GENERES
============================================
  Email :    admin@trading.bot
  Password : Xy7$pQ9!mNvB2k#3
============================================
```
**⚠️ COPIE CE MOT DE PASSE !** (il est aussi dans `C:\trading-bot\backend\.env`).

---

## 📋 ÉTAPE 5 — Installer MetaTrader 5

1. Télécharger MT5 depuis le site **de ton broker** (PAS le MT5 générique de MetaQuotes — celui de ton broker est pré-configuré pour leurs serveurs) :
   - **IC Markets** : https://www.icmarkets.com/global/en/trading-platforms/metatrader-5
   - **XM** : https://www.xm.com/mt5
   - **Exness** : https://www.exness.com/mt5
   - **Pepperstone** : https://pepperstone.com/en/trading-platforms/metatrader-5
   - **Admiral Markets** : https://admiralmarkets.com/start-trading/platforms/metatrader-5
2. Installer MT5
3. Au premier lancement, se connecter avec ton compte démo (ou créer un compte démo via le menu)
4. **IMPORTANT** : MT5 doit rester **lancé en permanence** sur le VPS pour que la lib Python `MetaTrader5` puisse communiquer avec lui. Cocher "Activate MT5 startup at Windows login" dans MT5 Options.

---

## 📋 ÉTAPE 6 — Tester la connexion MT5

Sur le VPS, ouvrir PowerShell et tester :
```powershell
C:\trading-bot\venv\Scripts\python.exe -c "import MetaTrader5 as mt5; print('mt5.initialize:', mt5.initialize(login=TON_LOGIN, password='TON_PASSWORD', server='TON_SERVEUR'))"
```

Si tu vois `mt5.initialize: True` → ça marche 🎉

Si `False` :
- Vérifier que MT5 est bien lancé
- Vérifier login/password/server (le serveur ressemble à `ICMarketsSC-Demo`, `XM-Demo`, etc.)
- Désactiver l'antivirus Windows Defender temporairement pour tester

---

## 📋 ÉTAPE 7 — Vérifier que le backend tourne

Toujours sur le VPS :
```powershell
# Status du service
Get-Service TradingBotBackend

# Test API
Invoke-WebRequest -Uri http://localhost:8001/api/health
# Devrait répondre : {"status":"ok",...}
```

Si le service ne tourne pas :
```powershell
Get-Content C:\trading-bot\logs\backend.err.log -Tail 50
Start-Service TradingBotBackend
```

---

## 📋 ÉTAPE 8 — Exposer le backend pour l'app mobile

Tu as 2 options :

### Option simple — HTTP direct (test/démo)
Le backend écoute sur `http://IP_DU_VPS:8001`. Tu peux configurer l'app mobile pour pointer vers cette URL.

Dans `/app/frontend/.env` (sur ton dev local) :
```
EXPO_PUBLIC_BACKEND_URL=http://IP_DU_VPS_PUBLIC:8001
```

⚠️ Pas de HTTPS, donc traffic en clair. Acceptable en dev pas en prod.

### Option pro — HTTPS via Nginx + Let's Encrypt
1. Acheter un nom de domaine (ex: `tonbot.com`) et pointer vers l'IP du VPS (DNS A record)
2. Installer Nginx via Chocolatey : `choco install -y nginx`
3. Configurer `C:\tools\nginx\conf\nginx.conf` :
```nginx
server {
    listen 80;
    server_name tonbot.com;
    location /api/ {
        proxy_pass http://localhost:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```
4. Obtenir certificat SSL : installer **win-acme** (équivalent certbot pour Windows) depuis https://www.win-acme.com/
5. `wacs.exe` → suivre wizard → certificat HTTPS auto-renouvelé

---

## 📋 ÉTAPE 9 — Activer MT5 dans l'app

1. Ouvre l'app mobile (sur ton téléphone via Expo Go ou un build)
2. Connecte-toi avec `admin@trading.bot` + le password généré
3. Va dans **Plus → Connexion MT5**
4. Saisis :
   - Login : ton numéro de compte MT5
   - Password : le mot de passe MT5 (différent du password de l'app !)
   - Serveur : ex. `ICMarketsSC-Demo`
   - Broker : optionnel
5. **Chiffrer & sauvegarder** (AES-256)
6. Clique **Connecter à MT5**
7. Si tout est OK → tu verras le status passer à **vert "MT5 connecté en live"** avec balance/equity/margin/profit live ✅

---

## 🔧 Commandes utiles (PowerShell admin sur le VPS)

```powershell
# Statut du backend
Get-Service TradingBotBackend

# Redémarrer le backend
Restart-Service TradingBotBackend

# Voir les logs en direct
Get-Content C:\trading-bot\logs\backend.out.log -Wait -Tail 50
Get-Content C:\trading-bot\logs\backend.err.log -Wait -Tail 50

# Statut MongoDB
Get-Service MongoDB

# Backup MongoDB
& "C:\MongoDB\bin\mongodump.exe" --out "C:\backups\$(Get-Date -Format yyyy-MM-dd)"

# Vérifier mémoire/CPU
Get-Counter '\Processor(_Total)\% Processor Time','\Memory\Available MBytes'
```

---

## 💰 Coûts totaux estimés

| Poste | Coût/mois |
|---|---|
| VPS Contabo Windows S | 9-11 € |
| Domaine .com (optionnel) | 1 € |
| Antivirus (Defender suffit) | 0 € |
| **TOTAL** | **~10-12 €/mois** |

À ajouter dans le module **Coûts** de l'app pour suivi automatique.

---

## ⚠️ Sécurité — Checklist finale

- [ ] Mot de passe RDP Administrator changé et fort (16+ caractères)
- [ ] Pare-feu RDP restreint à ton IP publique
- [ ] Windows Updates appliquées
- [ ] Mot de passe admin de l'app (généré par le script) noté en lieu sûr
- [ ] MongoDB n'écoute QUE sur localhost (par défaut, OK)
- [ ] Port 8001 ouvert UNIQUEMENT si tu n'as pas Nginx, sinon ne laisser que 443
- [ ] Backups MongoDB quotidiens (planifier via Task Scheduler Windows)
- [ ] Antivirus actif (Windows Defender suffit)
- [ ] **Trade-only API key chez MT5** : le compte MT5 doit autoriser le trading mais PAS le retrait

---

## 🆘 Troubleshooting

### MT5 ne se connecte pas (`mt5.initialize()` retourne False)
- Vérifier que MT5 terminal est lancé sur le VPS
- Login/password/server corrects (le serveur est exact, ex: `ICMarketsSC-Demo`)
- Le compte est valide (pas expiré)
- Désactiver temporairement Windows Defender pour exclure une interférence

### Le service TradingBotBackend ne démarre pas
- `Get-Content C:\trading-bot\logs\backend.err.log -Tail 50`
- Vérifier que MongoDB tourne : `Get-Service MongoDB`
- Vérifier le `.env` : `Get-Content C:\trading-bot\backend\.env`
- Tester manuellement : `cd C:\trading-bot\backend && C:\trading-bot\venv\Scripts\python.exe -m uvicorn server:app --host 0.0.0.0 --port 8001`

### "Address already in use" sur port 8001
- `Get-Process | Where-Object {$_.Name -like "*python*"}`
- Tuer le process: `Stop-Process -Id <PID>`

### Le VPS rame
- Vérifier RAM : `Get-Counter '\Memory\Available MBytes'`
- Si <500 MB libres → upgrade VPS ou réduire le bot_runner tick interval
- Désactiver les services Windows inutiles (Print Spooler, etc.)

---

## 📞 Support

- Logs structurés : `/api/audit/export?format=json` depuis l'app
- Métriques temps réel : `/api/bot/state`
- Statut MT5 : `/api/mt5/status`
