# ============================================================================
# Trading Bot - Installation automatisée sur VPS Windows Server 2022
# ============================================================================
# Ce script PowerShell installe tout ce qu'il faut pour faire tourner le
# bot de trading 24/7 sur un VPS Windows.
#
# USAGE (depuis une console PowerShell ADMINISTRATEUR sur le VPS) :
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\install.ps1
#
# CE QUE FAIT LE SCRIPT :
# - Installe Chocolatey (gestionnaire de paquets Windows)
# - Installe Python 3.11
# - Installe MongoDB Community 7
# - Installe Git
# - Crée le dossier C:\trading-bot et clone/copie le backend
# - Installe les deps Python (MetaTrader5, fastapi, etc.)
# - Configure un service Windows auto-restart "TradingBotBackend"
# - Ouvre les ports nécessaires dans le firewall
# - Génère un .env avec des clés aléatoires sécurisées
# ============================================================================

#Requires -RunAsAdministrator

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Trading Bot - Windows VPS Installer" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ---------- 1. Chocolatey ----------
if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
    Write-Host "[1/8] Installation Chocolatey..." -ForegroundColor Yellow
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    iex ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'))
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
} else {
    Write-Host "[1/8] Chocolatey deja installe, OK" -ForegroundColor Green
}

# ---------- 2. Python 3.11 ----------
Write-Host "[2/8] Installation Python 3.11..." -ForegroundColor Yellow
choco install -y python311 --params "/InstallDir:C:\Python311"
$env:Path += ";C:\Python311;C:\Python311\Scripts"
[System.Environment]::SetEnvironmentVariable("Path", $env:Path, [System.EnvironmentVariableTarget]::Machine)

# ---------- 3. MongoDB ----------
Write-Host "[3/8] Installation MongoDB 7..." -ForegroundColor Yellow
choco install -y mongodb --params "'/InstallDirectory:C:\MongoDB'"
# MongoDB est installe comme service automatiquement par Chocolatey
Start-Service -Name "MongoDB" -ErrorAction SilentlyContinue

# ---------- 4. Git ----------
Write-Host "[4/8] Installation Git..." -ForegroundColor Yellow
choco install -y git

# ---------- 5. Refresh path ----------
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

# ---------- 6. Dossier app ----------
$AppDir = "C:\trading-bot"
Write-Host "[5/8] Creation dossier $AppDir..." -ForegroundColor Yellow
if (-not (Test-Path $AppDir)) {
    New-Item -ItemType Directory -Path $AppDir | Out-Null
}
New-Item -ItemType Directory -Path "$AppDir\backend" -Force | Out-Null
New-Item -ItemType Directory -Path "$AppDir\logs" -Force | Out-Null

Write-Host ""
Write-Host "==> A FAIRE MAINTENANT : copier le dossier backend du projet dans :" -ForegroundColor Magenta
Write-Host "    $AppDir\backend\" -ForegroundColor Magenta
Write-Host ""
Write-Host "Tu peux soit :" -ForegroundColor Magenta
Write-Host "  - Drag-n-drop via RDP depuis ton PC local" -ForegroundColor Magenta
Write-Host "  - Cloner depuis ton Git : cd $AppDir && git clone <ton-repo> ." -ForegroundColor Magenta
Write-Host "  - Uploader via SFTP/SCP" -ForegroundColor Magenta
Write-Host ""
Read-Host "Appuie sur ENTREE quand le dossier backend\ est en place (avec server.py, requirements.txt, etc.)"

# ---------- 7. Python venv + deps ----------
Write-Host "[6/8] Creation venv Python + installation dependances..." -ForegroundColor Yellow
Set-Location $AppDir
python -m venv venv
& "$AppDir\venv\Scripts\python.exe" -m pip install --upgrade pip
& "$AppDir\venv\Scripts\pip.exe" install -r "$AppDir\backend\requirements.txt"
# IMPORTANT : installer la lib MetaTrader5 (ne fonctionne QUE sur Windows)
& "$AppDir\venv\Scripts\pip.exe" install MetaTrader5

# ---------- 8. Generation .env ----------
Write-Host "[7/8] Generation .env avec cles aleatoires securisees..." -ForegroundColor Yellow

function New-RandomKey {
    param([int]$Length = 48)
    $bytes = New-Object byte[] $Length
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    [Convert]::ToBase64String($bytes)
}

$jwtKey = New-RandomKey 48
$aesKey = New-RandomKey 32
$adminPwd = (-join ((33..126) | Get-Random -Count 16 | ForEach-Object {[char]$_})).Replace('"','x').Replace("'","y").Replace("``","z")

$envContent = @"
MONGO_URL=mongodb://localhost:27017
DB_NAME=trading_bot
JWT_SECRET_KEY=$jwtKey
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440
AES_SECRET_KEY_BASE64=$aesKey
ADMIN_EMAIL=admin@trading.bot
ADMIN_PASSWORD=$adminPwd
"@

Set-Content -Path "$AppDir\backend\.env" -Value $envContent -Encoding UTF8

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host " IDENTIFIANTS ADMIN GENERES" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Email :    admin@trading.bot"
Write-Host "  Password : $adminPwd"
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "==> COPIE CE MOT DE PASSE MAINTENANT ! Il est aussi dans $AppDir\backend\.env" -ForegroundColor Red
Read-Host "Appuie sur ENTREE quand c'est note en lieu sur"

# ---------- 9. Service Windows ----------
Write-Host "[8/8] Creation service Windows TradingBotBackend (auto-restart)..." -ForegroundColor Yellow

# Installer nssm (Non-Sucking Service Manager) pour wrapper uvicorn
choco install -y nssm

# Supprimer service existant si present
& nssm stop TradingBotBackend 2>$null
& nssm remove TradingBotBackend confirm 2>$null

# Creer le service
& nssm install TradingBotBackend "$AppDir\venv\Scripts\python.exe" "-m uvicorn server:app --host 0.0.0.0 --port 8001"
& nssm set TradingBotBackend AppDirectory "$AppDir\backend"
& nssm set TradingBotBackend DisplayName "Trading Bot Backend (FastAPI + Bot Loop)"
& nssm set TradingBotBackend Description "Trading bot 24/7 - FastAPI + MT5 connector"
& nssm set TradingBotBackend Start SERVICE_AUTO_START
& nssm set TradingBotBackend AppStdout "$AppDir\logs\backend.out.log"
& nssm set TradingBotBackend AppStderr "$AppDir\logs\backend.err.log"
& nssm set TradingBotBackend AppRotateFiles 1
& nssm set TradingBotBackend AppRotateBytes 10485760

Start-Service -Name TradingBotBackend

# ---------- Firewall ----------
Write-Host "Configuration pare-feu..." -ForegroundColor Yellow
New-NetFirewallRule -DisplayName "Trading Bot API (8001)" -Direction Inbound -Protocol TCP -LocalPort 8001 -Action Allow -ErrorAction SilentlyContinue | Out-Null

# Optionnel : Nginx (reverse proxy) pour HTTPS
Write-Host ""
Write-Host "Veux-tu installer Nginx pour faire un reverse proxy HTTPS ? (recommande pour prod) [y/N]"
$installNginx = Read-Host
if ($installNginx -eq "y" -or $installNginx -eq "Y") {
    choco install -y nginx
    New-NetFirewallRule -DisplayName "Nginx HTTP (80)" -Direction Inbound -Protocol TCP -LocalPort 80 -Action Allow -ErrorAction SilentlyContinue | Out-Null
    New-NetFirewallRule -DisplayName "Nginx HTTPS (443)" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow -ErrorAction SilentlyContinue | Out-Null
    Write-Host "Nginx installe. Configure C:\tools\nginx\conf\nginx.conf pour proxy /api -> localhost:8001"
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host " INSTALLATION TERMINEE !" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Backend tourne sur : http://localhost:8001/api/health" -ForegroundColor Cyan
Write-Host ""
Write-Host "Verification :"
Write-Host "  Get-Service TradingBotBackend"
Write-Host "  Invoke-WebRequest http://localhost:8001/api/health"
Write-Host ""
Write-Host "Logs :"
Write-Host "  $AppDir\logs\backend.out.log"
Write-Host "  $AppDir\logs\backend.err.log"
Write-Host ""
Write-Host "PROCHAINES ETAPES :"
Write-Host "  1. Installer MetaTrader 5 (telecharger depuis le site de ton broker)"
Write-Host "  2. Connecter MT5 a ton compte demo (login + password + server)"
Write-Host "  3. Ouvrir l'app mobile, aller dans MT5, saisir les memes identifiants"
Write-Host "  4. Cliquer 'Connecter a MT5' - la lib native sera detectee automatiquement"
Write-Host ""
Write-Host "SECURITE - A FAIRE :"
Write-Host "  - Changer le mot de passe RDP par defaut"
Write-Host "  - Restreindre l'acces RDP a ton IP (Pare-feu Windows)"
Write-Host "  - Installer un antivirus (Defender suffit)"
Write-Host "  - Mettre en place des sauvegardes MongoDB (mongodump quotidien)"
Write-Host ""
