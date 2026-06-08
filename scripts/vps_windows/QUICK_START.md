# 🚀 Installation ultra rapide — 3 étapes seulement

Pour Cloud VPS 30 Contabo (Windows Server 2022).

## ⏱️ Temps total : ~45 minutes (dont 30 min d'attente passive)

---

## 🔑 Étape 1 — Préparer ton GitHub (5 min)

1. Dans Emergent (sur ton PC) : clique **"Save to GitHub"** en haut à droite
2. Connecte ton compte GitHub si pas déjà fait
3. **Choisis "Public"** pour le repo (tu pourras le passer en privé après l'install)
4. Note l'URL du repo, ex: `https://github.com/ton-pseudo/trading-bot.git`

> Tu veux un repo **privé** dès le départ ? Génère un Personal Access Token sur GitHub (Settings → Developer settings → Personal access tokens → classic → cocher `repo` → Generate). Note le token (ghp_xxxx...). Ton URL devient `https://ton-pseudo:ghp_xxxx@github.com/ton-pseudo/trading-bot.git`

---

## 💻 Étape 2 — Commander le VPS Contabo (5-30 min)

1. Aller sur https://contabo.com/en/cloud-vps/
2. **Cloud VPS 30** → Get Started
3. Choisir :
   - **Region** : Germany (EU)
   - **Storage** : 200 GB NVMe
   - **Image** : ⚠️ **Windows Server 2022 Standard** (très important !)
   - **Period** : 1 month
4. Commander, payer (~16€/mois TTC avec licence Windows)
5. Attendre l'email Contabo (5-30 min) avec **IP + mot de passe Administrator**

---

## ⚡ Étape 3 — UNE seule commande pour tout installer

### 3a. Se connecter en RDP au VPS

- **Windows** : `Win + R` → `mstsc` → IP du VPS → `Administrator` + mot de passe Contabo
- **Mac** : App Microsoft Remote Desktop (App Store)
- **iOS/Android** : App Microsoft Remote Desktop

### 3b. Sur le VPS, ouvrir **PowerShell EN ADMINISTRATEUR**

Clic droit sur le menu Démarrer → **Windows PowerShell (Admin)** → Oui

### 3c. Copier-coller cette commande (UNE SEULE LIGNE) :

```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force; $env:REPO="https://github.com/TON_USER/TON_REPO.git"; iex (irm "https://raw.githubusercontent.com/TON_USER/TON_REPO/main/scripts/vps_windows/bootstrap.ps1")
```

⚠️ **Remplace `TON_USER/TON_REPO` par ton vrai username et nom de repo GitHub** (2 fois dans la ligne).

Si repo privé avec token, remplace par :
```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force; $env:REPO="https://TON_USER:ghp_TOKEN@github.com/TON_USER/TON_REPO.git"; iex (irm "https://TON_USER:ghp_TOKEN@raw.githubusercontent.com/TON_USER/TON_REPO/main/scripts/vps_windows/bootstrap.ps1")
```

Appuie sur Entrée.

### 3d. Pendant l'installation (~30 min)

Le script t'affichera ses étapes en couleur. À un moment il **te demandera de copier ton code backend** — c'est automatique via git clone, juste appuie sur Entrée quand demandé.

À la fin, **NOTE le mot de passe admin** affiché en vert :

```
============================================
 IDENTIFIANTS ADMIN GENERES
============================================
  Email :    admin@trading.bot
  Password : Xy7$pQ9!mNvB2k#3   <-- COPIE CECI
============================================
```

Sauvegarde-le dans Bitwarden / 1Password / un fichier texte hors VPS.

### 3e. Vérification finale

Toujours en PowerShell sur le VPS :
```powershell
Invoke-WebRequest http://localhost:8001/api/health
```

Tu dois voir `{"status":"ok"...}` ✅

---

## 🎯 Étape 4 — Installer MT5 (5 min)

1. Sur le VPS, ouvre Edge
2. Va sur le site de **ton broker** (IC Markets, XM, Exness, etc.)
3. Télécharge & installe MT5
4. Connecte-toi avec ton compte démo (ou crée-en un)
5. **Tools → Options → Expert Advisors** :
   - ☑️ Allow algorithmic trading
   - ☑️ Allow DLL imports
6. Mets MT5 dans le dossier de démarrage Windows pour qu'il se lance automatiquement :
   - `Win + R` → `shell:startup` → glisse-y un raccourci MT5

---

## 📱 Étape 5 — Connecter l'app au bot (3 min)

1. Sur ton téléphone : ouvre l'app mobile
2. Modifie le BACKEND_URL dans `/app/frontend/.env` pour pointer vers `http://IP_VPS:8001`
3. Login : `admin@trading.bot` + mot de passe noté à l'étape 3d
4. **Plus → Connexion MT5** → saisir login/password/serveur MT5 → Connecter
5. **Plus → Gestion du risque** → activer `live_mt5_trading_enabled`
6. **Bot → Mode RÉEL → ON**

🎉 **Tu vois les positions du bot live dans MT5 !**

---

## 🆘 Si ça plante

```powershell
# Status backend
Get-Service TradingBotBackend

# Logs en direct
Get-Content C:\trading-bot\logs\backend.err.log -Wait -Tail 30

# Restart backend
Restart-Service TradingBotBackend

# Relancer juste install.ps1
cd C:\trading-bot
.\scripts\vps_windows\install.ps1
```

Envoie-moi le message d'erreur ici, je débugue avec toi.

---

## 🔄 Auto-update

Une tâche planifiée Windows est créée automatiquement : chaque jour à 5h du matin, le VPS pulle les derniers changements depuis ton GitHub + redémarre + rollback auto si fail. Tu n'as rien à faire 🎉

Pour pousser une mise à jour : modifie le code dans Emergent → "Save to GitHub" → attends 5h ou force avec `Start-ScheduledTask -TaskName TradingBotAutoUpdate` sur le VPS.
