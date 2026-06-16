<#
.SYNOPSIS
    Script d'installation complet du Trading Bot sur Windows VPS
    
.DESCRIPTION
    - Installe Python 3.11, MongoDB
    - Clone/met à jour le repo
    - Configure .env
    - Installe les dépendances
    - Crée les services Windows
    
.PARAMETER VpsIp
    Adresse IP du VPS (pour Cloudflare Tunnel)
    
.EXAMPLE
    .\install_backend.ps1 -VpsIp "82.22.77.44"
#>

param(
    [string]$VpsIp = "82.22.77.44"
)

$ErrorActionPreference = "Stop"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "🚀 Installation Trading Bot - Windows VPS" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ===================== ÉTAPE 1: Vérifier les droits admin =====================
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "❌ Ce script doit être exécuté en tant qu'administrateur!" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Droits administrateur détectés" -ForegroundColor Green

# ===================== ÉTAPE 2: Installer Chocolatey =====================
Write-Host "
📦 Installation de Chocolatey..." -ForegroundColor Yellow
if (-NOT (Get-Command choco -ErrorAction SilentlyContinue)) {
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
    Write-Host "✅ Chocolatey installé" -ForegroundColor Green
} else {
    Write-Host "✅ Chocolatey déjà installé" -ForegroundColor Green
}

# ===================== ÉTAPE 3: Installer Python 3.11 =====================
Write-Host "
🐍 Installation de Python 3.11..." -ForegroundColor Yellow
if (-NOT (Get-Command python -ErrorAction SilentlyContinue)) {
    choco install python311 -y
    Write-Host "✅ Python 3.11 installé" -ForegroundColor Green
} else {
    $pythonVersion = python --version
    Write-Host "✅ Python déjà installé: $pythonVersion" -ForegroundColor Green
}

# Rafraîchir PATH
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# ===================== ÉTAPE 4: Installer Git =====================
Write-Host "
🔧 Installation de Git..." -ForegroundColor Yellow
if (-NOT (Get-Command git -ErrorAction SilentlyContinue)) {
    choco install git -y
    Write-Host "✅ Git installé" -ForegroundColor Green
} else {
    Write-Host "✅ Git déjà installé" -ForegroundColor Green
}

# ===================== ÉTAPE 5: Installer MongoDB =====================
Write-Host "
🗄️  Installation de MongoDB..." -ForegroundColor Yellow
if (-NOT (Get-Command mongod -ErrorAction SilentlyContinue)) {
    choco install mongodb -y
    Write-Host "✅ MongoDB installé" -ForegroundColor Green
} else {
    Write-Host "✅ MongoDB déjà installé" -ForegroundColor Green
}

# Créer répertoire de données MongoDB
$mongoDataPath = "C:\data\db"
if (-NOT (Test-Path $mongoDataPath)) {
    New-Item -ItemType Directory -Path $mongoDataPath -Force | Out-Null
    Write-Host "✅ Répertoire MongoDB créé: $mongoDataPath" -ForegroundColor Green
}

# ===================== ÉTAPE 6: Cloner/mettre à jour le repo =====================
Write-Host "
📥 Clone/mise à jour du repo GitHub..." -ForegroundColor Yellow
$repoPath = "C:\tradingbot"
if (-NOT (Test-Path $repoPath)) {
    git clone https://github.com/realowg111/tradingbot.git $repoPath
    Write-Host "✅ Repo cloné: $repoPath" -ForegroundColor Green
} else {
    Push-Location $repoPath
    git pull origin main
    Pop-Location
    Write-Host "✅ Repo mis à jour" -ForegroundColor Green
}

# ===================== ÉTAPE 7: Installer dépendances Python =====================
Write-Host "
📦 Installation des dépendances Python..." -ForegroundColor Yellow
$backendPath = Join-Path $repoPath "backend"
Push-Location $backendPath

pip install --upgrade pip
pip install -r requirements.txt
pip install MetaTrader5
pip install flask flask-cors  # pour l'agent MT5 si besoin

Write-Host "✅ Dépendances installées" -ForegroundColor Green
Pop-Location

# ===================== ÉTAPE 8: Générer les clés de sécurité =====================
Write-Host "
🔐 Génération des clés de sécurité..." -ForegroundColor Yellow

# Générer FERNET_KEY
$fernetKey = python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
Write-Host "FERNET_KEY généré (sauvegardez-le!)" -ForegroundColor Cyan

# JWT_SECRET aléatoire
$jwtSecret = [Convert]::ToBase64String((New-Object System.Random).GetBytes(32))

# ===================== ÉTAPE 9: Créer .env =====================
Write-Host "
⚙️  Création du fichier .env..." -ForegroundColor Yellow
$envPath = Join-Path $backendPath ".env"

$envContent = @"
MONGO_URL=mongodb://localhost:27017
DB_NAME=trading_bot

JWT_SECRET=$jwtSecret
JWT_ALGORITHM=HS256
JWT_EXPIRES_HOURS=168

FERNET_KEY=$fernetKey

ADMIN_EMAIL=admin@trading.bot
ADMIN_PASSWORD=Trading2025!

EMERGENT_LLM_KEY=sk-emergent-your-key-here

TELEGRAM_API_ID=30879528
TELEGRAM_API_HASH=5674826007957132ee773fa767e623f2
TELEGRAM_PHONE=+33769008392
TELEGRAM_CHANNEL=RentaTrade Z VIP
TELEGRAM_SESSION_PATH=C:\tradingbot\backend\data\telegram.session

MT5_TERMINAL_PATH=C:\Program Files\RoboForex - MetaTrader 5\terminal64.exe
"@

Set-Content -Path $envPath -Value $envContent -Encoding UTF8
Write-Host "✅ Fichier .env créé: $envPath" -ForegroundColor Green
Write-Host "⚠️  Rappel: Éditez .env avec vos vraies clés!" -ForegroundColor Yellow

# ===================== ÉTAPE 10: Créer dossiers requis =====================
Write-Host "
📁 Création des répertoires requis..." -ForegroundColor Yellow

$dirs = @(
    "$backendPath\data\telegram.session",
    "$repoPath\logs",
    "C:\data\db"
)

foreach ($dir in $dirs) {
    $parent = Split-Path $dir -Parent
    if (-NOT (Test-Path $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
}

Write-Host "✅ Répertoires créés" -ForegroundColor Green

# ===================== ÉTAPE 11: Installer NSSM (service manager) =====================
Write-Host "
🔧 Installation de NSSM (service manager)..." -ForegroundColor Yellow
if (-NOT (Get-Command nssm -ErrorAction SilentlyContinue)) {
    choco install nssm -y
    Write-Host "✅ NSSM installé" -ForegroundColor Green
} else {
    Write-Host "✅ NSSM déjà installé" -ForegroundColor Green
}

# ===================== ÉTAPE 12: Créer service MongoDB =====================
Write-Host "
🗄️  Configuration du service MongoDB..." -ForegroundColor Yellow

$mongoService = Get-Service MongoDB -ErrorAction SilentlyContinue
if ($mongoService) {
    Write-Host "✅ Service MongoDB existant détecté" -ForegroundColor Green
    Start-Service MongoDB -ErrorAction SilentlyContinue
} else {
    Write-Host "Création du service MongoDB..." -ForegroundColor Cyan
    nssm install MongoDB mongod --dbpath "C:\data\db"
    nssm start MongoDB
    Write-Host "✅ Service MongoDB créé et démarré" -ForegroundColor Green
}

# ===================== ÉTAPE 13: Créer service Backend =====================
Write-Host "
⚡ Configuration du service Backend FastAPI..." -ForegroundColor Yellow

$backendService = Get-Service TradingBotBackend -ErrorAction SilentlyContinue
if ($backendService) {
    Write-Host "Service existant détecté, suppression..." -ForegroundColor Cyan
    nssm stop TradingBotBackend
    nssm remove TradingBotBackend confirm
}

$pythonExe = "C:\Python311\python.exe"
$startScript = Join-Path $backendPath "server.py"

nssm install TradingBotBackend $pythonExe "-m uvicorn server:app --host 0.0.0.0 --port 8001"
nssm set TradingBotBackend AppDirectory $backendPath
nssm set TradingBotBackend AppEnvironmentExtra "PYTHONPATH=$backendPath"
nssm set TradingBotBackend AppStdout "$repoPath\logs\backend_stdout.log"
nssm set TradingBotBackend AppStderr "$repoPath\logs\backend_stderr.log"
nssm set TradingBotBackend Start SERVICE_AUTO_START

nssm start TradingBotBackend
Write-Host "✅ Service Backend créé et démarré" -ForegroundColor Green

# ===================== ÉTAPE 14: Vérifier les services =====================
Write-Host "
✅ Vérification des services..." -ForegroundColor Yellow

Start-Sleep -Seconds 3

Write-Host "
📊 État des services:" -ForegroundColor Cyan
$services = @("MongoDB", "TradingBotBackend")
foreach ($service in $services) {
    $status = Get-Service $service -ErrorAction SilentlyContinue
    if ($status) {
        $state = $status.Status
        $color = if ($state -eq "Running") { "Green" } else { "Red" }
        Write-Host "  $service: $state" -ForegroundColor $color
    }
}

# ===================== ÉTAPE 15: Test rapide =====================
Write-Host "
🧪 Test de l'API Backend (5s d'attente)..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

try {
    $response = Invoke-WebRequest -Uri "http://localhost:8001/api/health" -UseBasicParsing
    Write-Host "✅ API Backend répond: " -ForegroundColor Green -NoNewline
    Write-Host $response.StatusCode
} catch {
    Write-Host "⚠️  API pas encore prête (attendez quelques secondes)" -ForegroundColor Yellow
}

# ===================== RÉSUMÉ FINAL =====================
Write-Host "
" -ForegroundColor White
Write-Host "============================================" -ForegroundColor Green
Write-Host "✅ INSTALLATION TERMINÉE!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host "
📋 Résumé:" -ForegroundColor Cyan
Write-Host "  ✓ Python 3.11 installé"
Write-Host "  ✓ MongoDB configuré"
Write-Host "  ✓ Backend FastAPI service créé"
Write-Host "  ✓ Dépendances installées"
Write-Host "  ✓ .env généré (à configurer!)"
Write-Host "
⚠️  ÉTAPES MANUELLES REQUISES:" -ForegroundColor Yellow
Write-Host "  1. Éditer $envPath"
Write-Host "     - EMERGENT_LLM_KEY=votre-clé"
Write-Host "     - TELEGRAM_* si copie trading"
Write-Host "     - MT5_TERMINAL_PATH (adapter chemin broker)"
Write-Host "
  2. Ouvrir MT5 Terminal (ne pas fermer)"
Write-Host "
  3. Configurer MT5 Connection dans l'app Expo"
Write-Host "
🌐 API disponible sur:" -ForegroundColor Cyan
Write-Host "  http://localhost:8001/api/health"
Write-Host "  http://$VpsIp:8001/api/health (externe)"
Write-Host "
📖 Documentation: scripts/SETUP_MT5_BRIDGE.md" -ForegroundColor Green
Write-Host "
"
