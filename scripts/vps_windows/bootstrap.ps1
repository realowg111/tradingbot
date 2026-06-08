# ============================================================================
# Trading Bot - Bootstrap one-liner pour VPS Windows
# ============================================================================
# Lance l'installation complete du bot en une seule commande PowerShell.
#
# USAGE (PowerShell ADMIN sur le VPS Windows) :
#
#   $env:REPO="https://github.com/TON_USER/TON_REPO.git"; iex (irm https://raw.githubusercontent.com/TON_USER/TON_REPO/main/scripts/vps_windows/bootstrap.ps1)
#
# Ou pour repo prive avec token :
#   $env:REPO="https://USER:TOKEN@github.com/TON_USER/TON_REPO.git"; iex (irm ...)
#
# Le script va :
#   1. Verifier qu'on est admin
#   2. Installer Chocolatey + Git
#   3. Cloner ton repo dans C:\trading-bot
#   4. Lancer install.ps1 (tout le reste)
# ============================================================================

$ErrorActionPreference = "Stop"

function Step($msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function OK($msg)   { Write-Host "    [OK] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "    [!]  $msg" -ForegroundColor Yellow }
function Die($msg)  { Write-Host "    [X]  $msg" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "+---------------------------------------------+" -ForegroundColor Cyan
Write-Host "|     Trading Bot - Bootstrap Installer       |" -ForegroundColor Cyan
Write-Host "|     One-liner pour VPS Windows Server       |" -ForegroundColor Cyan
Write-Host "+---------------------------------------------+" -ForegroundColor Cyan

# --- Admin check ---
$current = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = (New-Object Security.Principal.WindowsPrincipal $current).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Die "Lance PowerShell EN ADMINISTRATEUR (clic droit -> Run as Administrator)"
}
OK "Mode administrateur OK"

# --- Repo URL ---
if (-not $env:REPO) {
    Write-Host ""
    Write-Host "URL du repository GitHub (ex: https://github.com/user/repo.git) :" -ForegroundColor Yellow
    Write-Host "  Pour repo prive, utilise: https://USER:TOKEN@github.com/user/repo.git" -ForegroundColor Gray
    $env:REPO = Read-Host "REPO"
}
if (-not $env:REPO) { Die "Pas d'URL de repo. Abandon." }
OK "Repo : $env:REPO"

# --- Chocolatey ---
Step "Verification de Chocolatey..."
if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
    Step "Installation de Chocolatey..."
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    iex ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1')) | Out-Null
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    OK "Chocolatey installe"
} else {
    OK "Chocolatey deja installe"
}

# --- Git ---
Step "Verification de Git..."
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Step "Installation de Git..."
    choco install -y git --no-progress | Out-Null
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    OK "Git installe"
} else {
    OK "Git deja installe"
}

# --- Clone repo ---
$AppDir = "C:\trading-bot"
Step "Clonage du repo dans $AppDir..."
if (Test-Path "$AppDir\.git") {
    Warn "Repo deja clone, pull des dernieres modifications..."
    Set-Location $AppDir
    git pull --ff-only
} else {
    if (Test-Path $AppDir) {
        Warn "Dossier $AppDir existe deja, suppression de son contenu..."
        Remove-Item "$AppDir\*" -Recurse -Force -ErrorAction SilentlyContinue
    } else {
        New-Item -ItemType Directory -Path $AppDir -Force | Out-Null
    }
    git clone $env:REPO $AppDir
    if ($LASTEXITCODE -ne 0) { Die "Echec du clonage. Verifie l'URL et tes credentials." }
}
OK "Repo clone"

# --- Verifier que install.ps1 existe ---
$InstallScript = "$AppDir\scripts\vps_windows\install.ps1"
if (-not (Test-Path $InstallScript)) {
    Die "Le fichier $InstallScript n'existe pas. Verifie la structure de ton repo."
}

# --- Lancer install.ps1 ---
Step "Lancement de l'installateur principal..."
Write-Host ""
Write-Host "Le script principal va installer :" -ForegroundColor Yellow
Write-Host "  - Python 3.11 + MongoDB 7" -ForegroundColor Gray
Write-Host "  - Lib MetaTrader5 (Python)" -ForegroundColor Gray
Write-Host "  - Service Windows TradingBotBackend (auto-restart)" -ForegroundColor Gray
Write-Host "  - Firewall + Nginx (optionnel)" -ForegroundColor Gray
Write-Host "  - .env avec cles aleatoires + mot de passe admin random" -ForegroundColor Gray
Write-Host ""

Set-Location $AppDir
& $InstallScript

# --- Configurer auto-update quotidien ---
Step "Configuration de l'auto-update quotidien (5h du matin)..."
try {
    $action = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument "-ExecutionPolicy Bypass -File C:\trading-bot\scripts\vps_windows\auto_update.ps1"
    $trigger = New-ScheduledTaskTrigger -Daily -At 5:00am
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
    Register-ScheduledTask -TaskName "TradingBotAutoUpdate" -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null
    OK "Auto-update programme tous les jours a 5h"
} catch {
    Warn "Impossible de creer la tache auto-update : $($_.Exception.Message)"
}

Write-Host ""
Write-Host "+---------------------------------------------+" -ForegroundColor Green
Write-Host "|       INSTALLATION TERMINEE !               |" -ForegroundColor Green
Write-Host "+---------------------------------------------+" -ForegroundColor Green
Write-Host ""
Write-Host "PROCHAINES ETAPES :" -ForegroundColor Cyan
Write-Host "  1. Verifier le service : Get-Service TradingBotBackend" -ForegroundColor Gray
Write-Host "  2. Tester l'API : Invoke-WebRequest http://localhost:8001/api/health" -ForegroundColor Gray
Write-Host "  3. Installer MetaTrader 5 (depuis le site de ton broker)" -ForegroundColor Gray
Write-Host "  4. Ouvrir l'app mobile et configurer la connexion MT5" -ForegroundColor Gray
Write-Host ""
Write-Host "Les identifiants admin generes sont au-dessus dans la sortie du script." -ForegroundColor Yellow
Write-Host "Le mot de passe est aussi dans C:\trading-bot\backend\.env" -ForegroundColor Yellow
Write-Host ""
